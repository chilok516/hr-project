"""UK walk-forward backtest — Exacta/Ex (any-order 1st+2nd) as quinella-equivalent.

NOTE: raceform.db has NO actual Ex dividend, so P&L uses a market-implied proxy
(market win odds -> Harville quinella prob -> fair dividend). The hit rate
(win_rate) is exact and does NOT depend on the dividend proxy.

Usage:
  python3 scripts/backtest_uk.py --start 2025-01-01 --ev 0.0
"""

import sys
import json
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
    ap.add_argument("--refit", type=int, default=1, help="refit models every N test dates")
    ap.add_argument("--max-train", type=int, default=None, help="cap training window to last N dates (bounds memory)")
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
        refit_interval=args.refit, max_train_dates=args.max_train,
    )

    logger.info("=== UK Exacta backtest ===")
    logger.info(f"races {result.total_races} | bets {result.total_bets} | wins {result.total_wins}")
    logger.info(f"hit rate {result.win_rate:.1%} | ROI {result.roi:+.1f}%")
    logger.info(f"staked ${result.total_staked:,.0f} | profit ${result.total_profit:,.0f}")
    logger.info(f"final bankroll ${result.final_bankroll:,.0f} | max drawdown {result.max_drawdown_pct:.1f}%")
    logger.info(f"breaker state {result.breaker_state} | skipped races {result.skipped_races}")
    logger.info("NOTE: P&L uses market-implied Ex dividend (win odds -> Harville); raceform.db has no actual Ex.")

    bets_data = []
    for b in result.bets:
        bets_data.append({
            "date": str(b.date)[:10],
            "venue": b.venue,
            "race_no": b.race_no,
            "horse_i_no": b.horse_i_no,
            "horse_j_no": b.horse_j_no,
            "horse_i": b.horse_i,
            "horse_j": b.horse_j,
            "combo": f"{b.horse_i_no}.{b.horse_i} + {b.horse_j_no}.{b.horse_j}",
            "prob": round(b.prob, 4),
            "est_div": round(b.est_dividend, 1),
            "ev": round(b.ev, 3),
            "stake": b.stake,
            "result": b.result,
            "actual_div": round(b.actual_dividend, 1) if b.actual_dividend else 0,
            "profit": round(b.profit, 2),
            "bet_type": b.bet_type,
        })

    equity = result.equity_curve
    payload = {
        "summary": {
            "total_races": result.total_races,
            "total_bets": result.total_bets,
            "total_wins": result.total_wins,
            "win_rate": round(result.win_rate, 4),
            "roi": round(result.roi, 4),
            "total_staked": round(result.total_staked, 2),
            "total_profit": round(result.total_profit, 2),
            "final_bankroll": round(result.final_bankroll, 2),
            "max_drawdown_pct": round(result.max_drawdown_pct, 4),
            "breaker_state": result.breaker_state,
            "skipped_races": result.skipped_races,
            "equity_curve": equity[-500:] if len(equity) > 500 else equity,
        },
        "bets": bets_data,
    }

    out = DATA_PROCESSED / "uk_bets_detail.json"
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Saved {len(bets_data)} bets to {out}")


if __name__ == "__main__":
    main()
