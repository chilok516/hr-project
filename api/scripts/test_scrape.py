"""Test script to verify HKJC scraping works with real data."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.scraper.hkjc_scraper import HKJCScraper


def test_scrape_single_date():
    scraper = HKJCScraper()

    # Try scraping a known race date
    date = "2024/07/01"
    logger.info(f"Testing scrape for {date}...")

    results = scraper.get_race_results(date)

    logger.info(f"Got {len(results)} results from {date}")

    if results:
        for r in results[:5]:
            logger.info(f"  R{r.race_no} | Pos {r.finish_pos} | {r.horse_name} | "
                       f"J: {r.jockey} | T: {r.trainer} | Odds: {r.odds}"
                       f" | Dist: {r.distance}m | Class: {r.race_class}")

    # Try a recent date
    import datetime
    today = datetime.date.today()
    # Get last Wednesday or Sunday
    for days_back in range(0, 30):
        d = today - datetime.timedelta(days=days_back)
        if d.weekday() in [2, 6]:
            test_date = d.strftime("%Y/%m/%d")
            logger.info(f"\nTesting recent date: {test_date}")
            recent = scraper.get_race_results(test_date)
            logger.info(f"Got {len(recent)} results from {test_date}")
            if recent:
                for r in recent[:3]:
                    logger.info(f"  R{r.race_no} | #{r.finish_pos} {r.horse_name} | "
                               f"J:{r.jockey} T:{r.trainer} | Odds:{r.odds}")
                break


if __name__ == "__main__":
    test_scrape_single_date()
