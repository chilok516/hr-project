"""Deep validation of the imported UK/IRE flat data (uk_race_results.csv)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from loguru import logger

from config import DATA_RAW


def main():
    df = pd.read_csv(DATA_RAW / "uk_race_results.csv", low_memory=False)
    n = len(df)
    logger.info(f"=== UK data validation ({n} rows) ===")

    # 1. Schema
    expected = ["race_date", "venue", "race_no", "race_class", "distance", "going",
                "course", "horse_name", "horse_id", "horse_no", "draw", "jockey",
                "trainer", "weight", "finish_pos", "win_odds", "age", "or",
                "country", "race_name", "race_type", "quinella_div"]
    missing = [c for c in expected if c not in df.columns]
    logger.info(f"1. Schema: {'OK' if not missing else f'MISSING {missing}'}")

    # 2. Coverage
    logger.info(f"2. Dates: {df['race_date'].nunique()}, range {df['race_date'].min()}..{df['race_date'].max()}")
    logger.info(f"   Venues: {df['venue'].nunique()}, Countries: {df['country'].value_counts().to_dict()}")
    logger.info(f"   race_type: {df['race_type'].value_counts().to_dict()}")

    # 3. Fill rates
    for c in ["jockey", "trainer", "weight", "draw", "win_odds", "or", "age", "horse_name"]:
        filled = df[c].notna().sum() and (df[c].astype(str) != "").sum() and (df[c].astype(str) != "nan").sum()
        logger.info(f"3. {c}: filled {(df[c].astype(str).str.strip() != '').sum()}/{n}")

    # 4. Numeric ranges + outliers
    checks = {
        "finish_pos": (1, 40),
        "draw": (0, 30),
        "weight": (90, 160),
        "win_odds": (1.0, 200.0),
        "distance": (900, 3600),
        "age": (2, 12),
        "or": (0, 140),
    }
    for col, (lo, hi) in checks.items():
        s = pd.to_numeric(df[col], errors="coerce")
        n_out = ((s < lo) | (s > hi)).sum()
        logger.info(f"4. {col}: min={s.min():.1f} max={s.max():.1f} mean={s.mean():.1f} outliers(<{lo} or >{hi})={n_out}")

    # 5. finish_pos sanity: winner pos=1, no pos 0
    pos = pd.to_numeric(df["finish_pos"], errors="coerce")
    logger.info(f"5. finish_pos: pos=1 count {df[pos==1].shape[0]}, pos<=0 count {(pos<=0).sum()}, NaN {pos.isna().sum()}")

    # 6. Per-race consistency: distance/class/going/going should be uniform within a race
    race_key = ["race_date", "venue", "race_no"]
    races = df.groupby(race_key).agg(
        n=("horse_name", "count"),
        dist_unique=("distance", "nunique"),
        class_unique=("race_class", "nunique"),
        going_unique=("going", "nunique"),
    )
    logger.info(f"6. Races: {len(races)}, avg field {races['n'].mean():.1f}, max {races['n'].max()}")
    logger.info(f"   races with >1 distance value: {(races['dist_unique']>1).sum()}")
    logger.info(f"   races with >1 class value: {(races['class_unique']>1).sum()}")
    logger.info(f"   races with >1 going value: {(races['going_unique']>1).sum()}")

    # 7. Distance distribution (top values) — confirm furlong->meter conversion
    logger.info(f"7. Distance dist: {df['distance'].value_counts().head(12).to_dict()}")

    # 8. Weight distribution — confirm stone->lb conversion sane
    logger.info(f"8. Weight: min {df['weight'].min()} max {df['weight'].max()} mean {df['weight'].mean():.0f}")

    # 9. Going / course distribution
    logger.info(f"9. Going: {df['going'].value_counts().to_dict()}")
    logger.info(f"   Course: {df['course'].value_counts().to_dict()}")

    # 10. Duplicates
    dup = df.duplicated().sum()
    logger.info(f"10. Duplicate rows: {dup}")

    # 11. Cross-check a known race within coverage (2025 Derby winner City Of Troy)
    derby = df[(df["horse_name"] == "City Of Troy") & (df["finish_pos"] == 1)]
    if not derby.empty:
        r = derby.iloc[0]
        logger.info(f"11. City Of Troy: {r['race_date']} {r['venue']} R{r['race_no']} "
                    f"{r['race_name'][:40]!r} w{r['weight']} jockey={r['jockey']!r} "
                    f"dist={r['distance']}m going={r['going']} odds={r['win_odds']}")
    else:
        logger.warning("11. City Of Troy (2024 Derby winner) NOT FOUND")

    # 12. Ex dividend gap (raceform.db has no Ex/quinella dividend)
    qd_empty = df["quinella_div"].isna().sum() + (df["quinella_div"].astype(str).str.strip() == "").sum()
    logger.info(f"12. quinella_div (Ex): empty/NaN {qd_empty}/{n}  <-- expect all (raceform has no Ex)")

    # 13. Country suffix leakage in horse_name
    suf = df["horse_name"].str.contains(r"\(", regex=True).sum()
    logger.info(f"13. horse_name with '(' suffix: {suf}")

    # 14. Sample recent rows for eyeball check
    recent = df[df["race_date"] == df["race_date"].max()].head(6)
    logger.info(f"14. Sample ({df['race_date'].max()}):")
    for _, r in recent.iterrows():
        logger.info(f"    {r['venue']:16s} R{r['race_no']} #{r['finish_pos']} {r['horse_name']:18s} "
                    f"w{r['weight']} d{r['draw']} or={r['or']} odds={r['win_odds']} {r['distance']}m")


if __name__ == "__main__":
    main()
