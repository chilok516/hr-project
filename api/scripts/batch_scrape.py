#!/usr/bin/env python3
"""Batch scrape HKJC race results for full seasons."""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_RAW
from src.scraper.hkjc_scraper import HKJCScraper
from dataclasses import asdict


def generate_race_dates(start: str, end: str) -> list[str]:
    """Generate all potential race dates (Wed + Sun) in range."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    dates = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() in [2, 6]:
            dates.append(current.strftime("%Y/%m/%d"))
        current += timedelta(days=1)
    return dates


def get_already_scraped() -> set:
    """Get set of already-scraped race dates from saved file."""
    path = DATA_RAW / "race_results.csv"
    if not path.exists():
        return set()

    try:
        df = pd.read_csv(path)
        if "race_date" in df.columns:
            return set(df["race_date"].unique())
    except Exception:
        pass
    return set()


def main():
    parser = argparse.ArgumentParser(description="Batch scrape HKJC race results")
    parser.add_argument("--start", default="2023-09-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-07-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--resume", action="store_true", default=True, help="Skip already scraped dates")
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    args = parser.parse_args()

    all_dates = generate_race_dates(args.start, args.end)
    logger.info(f"Total potential race dates: {len(all_dates)} ({args.start} to {args.end})")

    if args.resume:
        already = get_already_scraped()
        dates = [d for d in all_dates if d not in already]
        logger.info(f"Already scraped: {len(already)}, Remaining: {len(dates)}")
    else:
        dates = all_dates

    if not dates:
        logger.info("All dates already scraped!")
        return

    scraper = HKJCScraper()
    scraper.min_interval = 1.0  # Faster rate limiting

    all_results = []

    for i, d in enumerate(dates):
        logger.info(f"[{i+1}/{len(dates)}] {d}")

        has_races = False
        for rn in range(1, 12):
            results = scraper.get_race_results_detailed(d, rn)
            if results:
                all_results.extend(results)
                has_races = True
            elif rn >= 2 and not has_races:
                break

        if has_races:
            logger.info(f"  -> {len([r for r in all_results if r.race_date == d])} horses")

        # Save incrementally every 5 dates
        if (i + 1) % 5 == 0 and all_results:
            df = pd.DataFrame([asdict(r) for r in all_results])
            path = DATA_RAW / "race_results.csv"
            if path.exists() and path.stat().st_size > 0:
                try:
                    existing = pd.read_csv(path)
                    df = pd.concat([existing, df], ignore_index=True)
                except Exception:
                    pass
            df.to_csv(path, index=False)
            logger.info(f"  Saved {len(df)} total records")
            all_results = []

    # Final save
    if all_results:
        df = pd.DataFrame([asdict(r) for r in all_results])
        path = DATA_RAW / "race_results.csv"
        if path.exists() and path.stat().st_size > 0:
            try:
                existing = pd.read_csv(path)
                df = pd.concat([existing, df], ignore_index=True)
            except Exception:
                pass
        df.to_csv(path, index=False)

    # Report
    final = pd.read_csv(DATA_RAW / "race_results.csv")
    logger.info(f"\n=== SCRAPE COMPLETE ===")
    logger.info(f"Total records: {len(final)}")
    logger.info(f"Total dates: {final['race_date'].nunique()}")
    logger.info(f"Venues: {final['venue'].value_counts().to_dict()}")
    logger.info(f"Date range: {final['race_date'].min()} to {final['race_date'].max()}")


if __name__ == "__main__":
    main()
