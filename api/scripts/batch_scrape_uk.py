"""Fast batch scrape UK — only Wed/Sat/Sun (main racing days)."""

import asyncio, sys
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.scraper.euro_scraper import scrape_uk_date
from config import DATA_RAW
import pandas as pd
from dataclasses import asdict


def gen_race_dates(start: str, end: str) -> list:
    """Generate Wed+Thu+Fri+Sat+Sun dates (main UK racing days)."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    dates = []
    d = start_dt
    while d <= end_dt:
        if d.weekday() in [2, 3, 4, 5, 6]:  # Wed through Sun
            dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return dates


async def main():
    all_dates = gen_race_dates("2022-01-01", "2024-12-31") + \
                gen_race_dates("2025-01-01", "2025-12-31") + \
                gen_race_dates("2026-01-01", "2026-08-08")
    logger.info(f"Target: {len(all_dates)} dates")

    # Skip already scraped dates
    existing_path = DATA_RAW / "uk_race_results.csv"
    done_dates = set()
    if existing_path.exists():
        try:
            existing = pd.read_csv(existing_path)
            done_dates = set(existing["race_date"].unique())
            logger.info(f"Already scraped: {len(done_dates)} dates")
        except Exception:
            pass

    dates = [d for d in all_dates if d not in done_dates]
    logger.info(f"Remaining: {len(dates)} dates")

    all_results = []
    for i, d in enumerate(dates):
        results = await scrape_uk_date(d)
        if results:
            all_results.extend(results)
            logger.info(f"[{i+1}/{len(dates)}] {d}: {len(results)} horses, total={len(all_results)}")
        else:
            logger.debug(f"[{i+1}/{len(dates)}] {d}: no racing")

        # Save every 10 dates
        if (i + 1) % 10 == 0 and all_results:
            df_new = pd.DataFrame([asdict(r) for r in all_results])
            if existing_path.exists():
                try:
                    old = pd.read_csv(existing_path)
                    df_new = pd.concat([old, df_new], ignore_index=True)
                except Exception:
                    pass
            df_new.to_csv(existing_path, index=False)
            logger.info(f"  Saved {len(df_new)} total")
            all_results = []

    # Final save
    if all_results:
        df_new = pd.DataFrame([asdict(r) for r in all_results])
        if existing_path.exists():
            try:
                old = pd.read_csv(existing_path)
                df_new = pd.concat([old, df_new], ignore_index=True)
            except Exception:
                pass
        df_new.to_csv(existing_path, index=False)

    final = pd.read_csv(existing_path)
    logger.info(f"=== DONE: {len(final)} records, {final['race_date'].nunique()} dates ===")


if __name__ == "__main__":
    asyncio.run(main())
