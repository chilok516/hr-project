"""Import the Raceform SQLite DB (Kaggle: deltaromeo/horse-racing-results-ukireland-2015-2025)
into our uk_race_results.csv schema (flat, UK/IRE only).

Usage:
  1. Download raceform.db from Kaggle (one-time, free)
  2. python3 scripts/import_raceform.py /path/to/raceform.db
  3. -> data/raw/uk_race_results.csv
"""

import re
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger

from config import DATA_RAW
from src.scraper.euro_scraper import OUTPUT_COLUMNS, _furlongs_to_meters, _frac_to_dec


def _weight_to_lbs(wgt: str) -> int:
    """'10-1' -> 141 lbs; '9-4' -> 130 lbs."""
    if not wgt:
        return 0
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", str(wgt).strip())
    if m:
        return int(m.group(1)) * 14 + int(m.group(2))
    return 0


def _parse_course_country(course: str) -> tuple:
    """'Auteuil (FR)' -> ('Auteuil', 'FR'); 'Fairyhouse (IRE)' -> ('Fairyhouse', 'IRE'); 'York' -> ('York', 'UK')."""
    m = re.match(r"^(.*?)\s*\(([A-Z]{2,3})\)\s*$", str(course).strip())
    if m:
        return m.group(1).strip(), m.group(2)
    return str(course).strip(), "UK"


def _parse_going(g: str) -> tuple:
    """Normalize Raceform going -> (going_code, course)."""
    if not g:
        return "", ""
    s = str(g).strip()
    up = s.upper()
    if "STANDARD" in up or "SLOW" in up or "POLYTRACK" in up or "TAPETA" in up or "FIBRESAND" in up:
        return "STANDARD", "AWT"
    if "HEAVY" in up:
        return "HEAVY", "TURF"
    if "SOFT" in up and "GOOD" in up:
        return "GOOD TO SOFT", "TURF"
    if "SOFT" in up:
        return "SOFT", "TURF"
    if "FIRM" in up and "GOOD" in up:
        return "GOOD TO FIRM", "TURF"
    if "FIRM" in up:
        return "FIRM", "TURF"
    if "YIELDING" in up:
        return "YIELDING", "TURF"
    return "GOOD", "TURF"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import_raceform.py /path/to/raceform.db")
        return

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found")
        return

    con = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM data WHERE type = 'Flat'", con)
    con.close()
    logger.info(f"Flat rows: {len(df)}")

    # filter UK/IRE
    parsed = df["course"].apply(_parse_course_country)
    df["venue"] = parsed.apply(lambda x: x[0])
    df["country"] = parsed.apply(lambda x: x[1])
    df = df[df["country"].isin(["UK", "IRE"])]
    logger.info(f"UK/IRE flat rows: {len(df)}")

    # map to OUTPUT_COLUMNS schema
    df["race_date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["race_no"] = df.groupby(["race_date", "venue"])["off"].rank(method="dense").astype(int)
    df["race_class"] = df["class"].fillna("").astype(str)
    # Group/Listed races have empty class but have pattern; map pattern to class
    df.loc[df["race_class"] == "", "race_class"] = df["pattern"].fillna("")
    df["distance"] = df["dist"].apply(_furlongs_to_meters)
    df["going"], df["course"] = zip(*df["going"].apply(_parse_going))
    df["horse_name"] = df["horse"].apply(lambda h: re.sub(r"\s*\([^)]*\)\s*$", "", str(h)).strip())
    df["horse_id"] = ""
    df["horse_no"] = df["num"].fillna(0).astype(int)
    df["draw"] = df["draw"].fillna(0).astype(int)
    df["jockey"] = df["jockey"].fillna("").astype(str)
    df["trainer"] = df["trainer"].fillna("").astype(str)
    df["weight"] = df["wgt"].apply(_weight_to_lbs)
    df["declared_weight"] = df["weight"]
    df["finish_pos"] = df["pos"].fillna(0).astype(int)
    df["margin"] = df["btn"].fillna("").astype(str)
    df["win_odds"] = df["sp"].apply(_frac_to_dec)
    df["prize"] = df["prize"].fillna("").astype(str)
    df["age"] = df["age"].fillna(0).astype(int)
    df["or"] = pd.to_numeric(df["or"], errors="coerce")
    df["race_name"] = df["race_name"].fillna("").astype(str)
    df["race_type"] = "F"
    df["country"] = df["country"].astype(str)
    # fill remaining schema columns with defaults
    for c in ["rating_band", "running_position", "finish_time", "sectional_time",
              "incident_remark", "quinella_div", "quinella_place_div"]:
        df[c] = ""

    out = df[OUTPUT_COLUMNS]
    out = out.drop_duplicates()
    out.to_csv(DATA_RAW / "uk_race_results.csv", index=False)
    logger.info(f"Saved {len(out)} rows -> uk_race_results.csv "
                f"({out['race_date'].nunique()} dates, {out['venue'].nunique()} venues)")


if __name__ == "__main__":
    main()
