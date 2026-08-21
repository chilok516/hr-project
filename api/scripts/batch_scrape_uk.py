"""Batch scrape UK/IRE flat racing results (RacingPost full-result pages).

Usage:
  python3 scripts/batch_scrape_uk.py --start 2025-01-01 --end 2026-08-20
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_RAW
from src.scraper.euro_scraper import scrape_date, OUTPUT_COLUMNS
import pandas as pd


def gen_race_dates(start: str, end: str) -> list:
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    dates = []
    d = start_dt
    while d <= end_dt:
        if d.weekday() in [2, 3, 4, 5, 6]:  # Wed-Sun (main UK/IRE racing days)
            dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return dates


def main():
    ap = argparse.ArgumentParser(description="Batch scrape UK/IRE flat results")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-08-20")
    args = ap.parse_args()

    out_path = DATA_RAW / "uk_race_results.csv"
    done_dates = set()
    if out_path.exists():
        try:
            existing = pd.read_csv(out_path, low_memory=False)
            done_dates = set(existing["race_date"].unique())
            logger.info(f"Already scraped: {len(done_dates)} dates")
        except Exception:
            pass

    dates = [d for d in gen_race_dates(args.start, args.end) if d not in done_dates]
    logger.info(f"Remaining: {len(dates)} dates ({args.start} -> {args.end})")

    all_rows = []
    for i, d in enumerate(dates):
        rows = scrape_date(d)
        all_rows.extend(rows)

        if (i + 1) % 5 == 0 and all_rows:
            df_new = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS)
            if out_path.exists():
                try:
                    old = pd.read_csv(out_path, low_memory=False)
                    df_new = pd.concat([old, df_new], ignore_index=True)
                except Exception:
                    pass
            df_new.to_csv(out_path, index=False)
            logger.info(f"[{i+1}/{len(dates)}] saved {len(df_new)} total")
            all_rows = []

    if all_rows:
        df_new = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS)
        if out_path.exists():
            try:
                old = pd.read_csv(out_path, low_memory=False)
                df_new = pd.concat([old, df_new], ignore_index=True)
            except Exception:
                pass
        df_new.to_csv(out_path, index=False)

    final = pd.read_csv(out_path, low_memory=False)
    logger.info(f"=== DONE: {len(final)} records, {final['race_date'].nunique()} dates ===")


if __name__ == "__main__":
    main()
