"""UK walk-forward backtest — Exacta/Ex (any-order 1st+2nd) as quinella-equivalent.

NOTE: raceform.db has NO actual Ex dividend, so P&L uses an SP proxy
(odds_i * odds_j / 3). The hit rate (win_rate) is exact and does NOT depend
on the dividend proxy.

Usage:
  python3 scripts/backtest_uk.py --start 2025-01-01 --ev 0.0
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger

from config import DATA_PROCESSED
from src.backtest.quinella_backtest import QuinellaBacktest


def main():
    ap = argparse.ArgumentParser(description="UK Exacta walk-forward backtest")
    ap.add_argument("--start", default=None, help="only backtest dates >= YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="only backtest dates <= YYYY-MM-DD")
    ap.add_argument("--ev", type=float, default=0.0, help="EV filter threshold")
    ap.add_argument("--min-train", type=int, default=150, help="warmup dates before first test")
    ap.add_argument("--anchors", type=int, default=3, help="number of anchor horses")
    args = ap.parse_args()

    path = DATA_PROCESSED / "uk_features.csv"
    if not path.exists():
        logger.error(f"{path} not found — run build_uk_features.py first")
        return

    df = pd.read_csv(path, low_memory=False)
    df["race_date"] = pd.to_datetime(df["race_date"], errors="coerce")
    df = df.dropna(subset=["race_date"])
    if args.start:
        df = df[df["race_date"] >= pd.to_datetime(args.start)]
    if args.end:
        df = df[df["race_date"] <= pd.to_datetime(args.end)]
    logger.info(f"Backtest data: {len(df)} rows, {df['race_date'].nunique()} dates")

    bt = QuinellaBacktest(bankroll=100_000, base_stake=100, ev_threshold=args.ev)
    result = bt.run(
        df, n_anchors=args.anchors, ev_threshold=args.ev,
        min_train_dates=args.min_train, bet_type="quinella",
    )

    logger.info("=== UK Exacta backtest ===")
    logger.info(f"races {result.total_races} | bets {result.total_bets} | wins {result.total_wins}")
    logger.info(f"hit rate {result.win_rate:.1%} | ROI {result.roi:+.1f}%")
    logger.info(f"staked ${result.total_staked:,.0f} | profit ${result.total_profit:,.0f}")
    logger.info(f"final bankroll ${result.final_bankroll:,.0f} | max drawdown {result.max_drawdown_pct:.1f}%")
    logger.info("NOTE: P&L uses SP-proxy Ex dividend (odds_i*odds_j/3); raceform.db has no actual Ex.")


if __name__ == "__main__":
    main()
