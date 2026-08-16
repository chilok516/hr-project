#!/usr/bin/env python3
"""Run the async odds poller for a single race.

Usage:
  python3 scripts/run_odds_poller.py --date 2026/09/06 --venue ST --race 1 --start-min 30
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.signals.odds_poller import OddsPoller


def make_alerter(verbose: bool = False):
    def on_change(race_key, movements, drift):
        for m in movements:
            if m.signal != "stable" or verbose:
                print(
                    f"[{race_key}] horse {m.horse_no}: "
                    f"{m.odds_t1} -> {m.odds_t2} ({m.change_pct:+.1f}%) {m.signal}"
                )
    return on_change


async def main():
    ap = argparse.ArgumentParser(description="Async odds poller for one race")
    ap.add_argument("--date", required=True, help="race date YYYY/MM/DD")
    ap.add_argument("--venue", default="ST", help="ST or HV")
    ap.add_argument("--race", type=int, default=1, help="race number")
    ap.add_argument("--start-min", type=int, default=30, help="minutes before start to begin")
    ap.add_argument("--verbose", action="store_true", help="log stable movements too")
    args = ap.parse_args()

    poller = OddsPoller(
        args.date,
        args.venue,
        args.race,
        on_change=make_alerter(args.verbose),
        on_snapshot=lambda s: print(
            f"[{s.race_date} R{s.race_no} T-{s.minutes_before}min] {len(s.horses)} horses"
        ),
    )
    try:
        await poller.run(start_minutes=args.start_min)
    finally:
        await poller.close()


if __name__ == "__main__":
    asyncio.run(main())
