"""Regenerate bets_detail.json from the latest features.csv.

Runs the full walk-forward quinella backtest with validated parameters:
  n_anchors=3, beta=0.855, EV>0.4, cold score ON, gamma=1.0
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_PROCESSED
from src.backtest.quinella_backtest import QuinellaBacktest


def main():
    df = pd.read_csv(DATA_PROCESSED / "features.csv", low_memory=False)
    df["race_date"] = pd.to_datetime(df["race_date"])
    print(f"Loaded {len(df)} records, {df['race_date'].nunique()} dates")

    bt = QuinellaBacktest(
        base_stake=100, gamma=1.0, beta=0.855,
        ev_threshold=0.4, use_cold_score=True,
    )
    result = bt.run(df, n_anchors=3, min_train_dates=10, bet_type="quinella")

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
            "est_div": round(b.est_dividend, 0),
            "ev": round(b.ev, 3),
            "stake": b.stake,
            "result": b.result,
            "actual_div": round(b.actual_dividend, 0) if b.actual_dividend else 0,
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
            "equity_curve": equity[-500:] if len(equity) > 500 else equity,
        },
        "bets": bets_data,
    }

    out = DATA_PROCESSED / "bets_detail.json"
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"Saved {len(bets_data)} bets to {out}")
    print(f"ROI={result.roi:.1%} WR={result.win_rate:.1%} "
          f"bankroll=${result.final_bankroll:,.0f}")


if __name__ == "__main__":
    main()
