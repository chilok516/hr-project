"""
HKJC Horse Racing Prediction Pipeline
Usage:
    python main.py scrape --start 2024-01-01 --end 2024-07-31
    python main.py train
    python main.py backtest
    python main.py predict --race-date 2024-07-01 --venue ST --race-no 1
    python main.py pipeline --start 2024-01-01 --end 2024-07-31
"""

import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from loguru import logger

from config import DATA_RAW, DATA_PROCESSED, DATA_MODELS, STARTING_BANKROLL
from src.scraper.hkjc_scraper import HKJCScraper
from src.features.feature_engine import FeatureEngineer
from src.models.train import RacePredictor, EXCLUDE_COLS
from src.backtest.engine import BacktestEngine


def cmd_scrape(args):
    scraper = HKJCScraper()
    df = scraper.scrape_date_range(args.start, args.end)
    logger.info(f"Scraped {len(df)} race results")
    path = DATA_RAW / "race_results.csv"
    df.to_csv(path, index=False)
    logger.info(f"Saved to {path}")


def cmd_train(args):
    path = args.data or (DATA_PROCESSED / "features.csv")
    if not Path(path).exists():
        logger.error(f"Features not found: {path}")
        return

    df = pd.read_csv(path)
    logger.info(f"Loaded {len(df)} records")

    predictor = RacePredictor()
    predictor.train_all(df)
    predictor.save_all()

    for name, model in [("Fundamental", predictor.fundamental),
                         ("Top2", predictor.top2),
                         ("Market", predictor.market)]:
        imp = model.get_feature_importance()
        logger.info(f"\n{name} Model Top 10:")
        for _, row in imp.head(10).iterrows():
            logger.info(f"  {row['feature']:<30s} {row['importance']:.0f}")


def cmd_backtest(args):
    features_path = args.data or (DATA_PROCESSED / "features.csv")
    if not Path(features_path).exists():
        logger.error(f"Features not found: {features_path}")
        return

    df = pd.read_csv(features_path)
    logger.info(f"Loaded {len(df)} records for backtest")

    from src.models.train import HorseRaceModel

    engine = BacktestEngine(bankroll=args.bankroll)

    if args.walk_forward:
        logger.info("Running walk-forward backtest (fundamental model, no odds)...")
        feature_cols = [c for c in df.columns if c not in EXCLUDE_COLS | {"win_odds", "odds", "odds_log", "odds_inv", "odds_rank"}]
        result = engine.walk_forward(
            df, HorseRaceModel, feature_cols,
            bet_strategy=args.strategy,
            max_bets_per_race=args.max_bets,
            min_train_dates=args.min_train,
            exclude_odds=True,
        )
    else:
        logger.info("Running standard backtest...")
        if "fund_prob" not in df.columns:
            predictor = RacePredictor()
            try:
                predictor.load_all()
            except FileNotFoundError:
                logger.error("No trained model found. Run 'train' first.")
                return

            feats = [f for f in predictor.fundamental.feature_names if f in df.columns]
            X = df[feats].fillna(df[feats].median()).values
            df["win_prob"] = predictor.fundamental.predict(X)

        if "win_odds" in df.columns and "odds" not in df.columns:
            df["odds"] = df["win_odds"]

        result = engine.run(df, bet_strategy=args.strategy,
                            max_bets_per_race=args.max_bets, min_prob=args.min_prob)

    engine.print_report(result)

    bets_df = pd.DataFrame([{
        "date": b.date, "venue": b.venue, "race_no": b.race_no,
        "horse": b.horse_name, "stake": b.stake, "odds": b.odds,
        "prob": b.win_prob, "result": b.result, "profit": b.profit,
    } for b in result.bets])

    path = DATA_PROCESSED / "backtest_results.csv"
    bets_df.to_csv(path, index=False)
    logger.info(f"Backtest results saved to {path}")


def cmd_predict(args):
    scraper = HKJCScraper()
    results = scraper.get_race_results_detailed(args.race_date, args.race_no)
    if not results:
        logger.error("Failed to fetch race card")
        return

    predictor = RacePredictor()
    try:
        predictor.load_all()
    except FileNotFoundError:
        logger.error("No trained model found")
        return

    from dataclasses import asdict
    race_df = pd.DataFrame([asdict(r) for r in results])

    fe = FeatureEngineer(race_df)
    features_df = fe.build_all_features()

    result = predictor.predict_race(features_df)

    first = results[0]
    print(f"\n{'='*60}")
    print(f"  RACE PREDICTION: {first.race_date} | {first.venue} | Race {first.race_no}")
    print(f"  Distance: {first.distance}m | Class: {first.race_class}")
    print(f"{'='*60}")

    display = result[["horse_no", "horse_name", "jockey", "win_odds",
                       "fund_prob", "top2_prob", "market_prob"]].head(8)
    for _, row in display.iterrows():
        print(f"  #{int(row['horse_no'])} {row['horse_name']:<20s} "
              f"J:{row['jockey']:<12s} "
              f"Fund:{row['fund_prob']:.1%} Top2:{row['top2_prob']:.1%} "
              f"Mkt:{row['market_prob']:.1%}")

    print(f"\n  Top Pick (Fund): {display.iloc[0]['horse_name']} ({display.iloc[0]['fund_prob']:.1%})")
    print()


def cmd_pipeline(args):
    logger.info("=== Phase 1: Scraping ===")
    scraper = HKJCScraper()
    df = scraper.scrape_date_range(args.start, args.end)

    if len(df) < 100:
        logger.error(f"Not enough data: {len(df)} records")
        return
    logger.info(f"Scraped {len(df)} race results")

    logger.info("=== Phase 2: Feature Engineering ===")
    fe = FeatureEngineer(df)
    features_df = fe.build_all_features()
    fe.save()
    logger.info(f"Generated {len(features_df.columns)} features")

    logger.info("=== Phase 3: Model Training ===")
    predictor = RacePredictor()
    predictor.train_all(features_df)
    predictor.save_all()

    for name, model in [("Fundamental", predictor.fundamental),
                         ("Top2", predictor.top2)]:
        imp = model.get_feature_importance()
        logger.info(f"{name} top 5: {', '.join(imp['feature'].head(5))}")

    logger.info("=== Phase 4: Walk-Forward Backtest ===")
    if "win_odds" in features_df.columns and "odds" not in features_df.columns:
        features_df["odds"] = features_df["win_odds"]

    from src.models.train import HorseRaceModel
    feature_cols = [c for c in features_df.columns if c not in
                    EXCLUDE_COLS | {"win_odds", "odds", "odds_log", "odds_inv", "odds_rank",
                                    "target_top2", "fund_raw", "top2_raw", "market_raw", "place_raw",
                                    "fund_prob", "top2_prob", "market_prob", "place_prob"}]

    engine = BacktestEngine(bankroll=STARTING_BANKROLL)
    result = engine.walk_forward(
        features_df, HorseRaceModel, feature_cols,
        bet_strategy=args.strategy, exclude_odds=True,
    )
    engine.print_report(result)
    logger.info("=== Pipeline Complete ===")


def main():
    parser = argparse.ArgumentParser(description="HKJC Horse Racing Prediction")
    sub = parser.add_subparsers(dest="command")

    p_scrape = sub.add_parser("scrape")
    p_scrape.add_argument("--start", required=True)
    p_scrape.add_argument("--end", required=True)

    p_train = sub.add_parser("train")
    p_train.add_argument("--data", default=None)

    p_backtest = sub.add_parser("backtest")
    p_backtest.add_argument("--data", default=None)
    p_backtest.add_argument("--strategy", default="kelly_fraction",
                            choices=["kelly_fraction", "flat", "proportional", "expected_value"])
    p_backtest.add_argument("--max-bets", type=int, default=3)
    p_backtest.add_argument("--min-prob", type=float, default=0.10)
    p_backtest.add_argument("--bankroll", type=float, default=STARTING_BANKROLL)
    p_backtest.add_argument("--walk-forward", action="store_true", default=False)
    p_backtest.add_argument("--min-train", type=int, default=5)

    p_predict = sub.add_parser("predict")
    p_predict.add_argument("--race-date", required=True)
    p_predict.add_argument("--venue", default="ST")
    p_predict.add_argument("--race-no", type=int, default=1)

    p_pipeline = sub.add_parser("pipeline")
    p_pipeline.add_argument("--start", required=True)
    p_pipeline.add_argument("--end", required=True)
    p_pipeline.add_argument("--strategy", default="kelly_fraction")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    commands = {
        "scrape": cmd_scrape,
        "train": cmd_train,
        "backtest": cmd_backtest,
        "predict": cmd_predict,
        "pipeline": cmd_pipeline,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
