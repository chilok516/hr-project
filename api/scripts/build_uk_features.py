"""Build UK/IRE features from the scraped flat results (new schema).

Input:  data/raw/uk_race_results.csv  (distance in meters, decimal odds, normalized going,
        full jockey/trainer/draw/weight/OR/age, Ex dividend in quinella_div)
Output: data/processed/uk_features.csv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger

from config import DATA_RAW, DATA_PROCESSED
from src.features.feature_engine import FeatureEngineer


def main():
    path = DATA_RAW / "uk_race_results.csv"
    if not path.exists():
        logger.error(f"{path} not found — run batch_scrape_uk.py first")
        return

    raw = pd.read_csv(path, low_memory=False)
    logger.info(f"Raw UK rows: {len(raw)}, dates: {raw['race_date'].nunique()}")

    fe = FeatureEngineer(raw)
    df = fe.build_all_features()
    df.to_csv(DATA_PROCESSED / "uk_features.csv", index=False)
    logger.info(f"Saved {len(df)} rows, {len(df.columns)} cols -> uk_features.csv")

    # quality report
    for c in ["horse_avg_pos", "horse_win_rate", "jockey_win_rate", "trainer_win_rate",
              "target_win", "target_top2", "target_place"]:
        if c in df.columns:
            logger.info(f"  {c}: non-null {df[c].notna().sum()}/{len(df)}")


if __name__ == "__main__":
    main()
