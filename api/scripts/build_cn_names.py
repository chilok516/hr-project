"""Build English→Chinese name mappings (horse/jockey/trainer) from Chinese HKJC pages.

Aligns Chinese LocalResults pages with the existing English race_results.csv
to build 1:1 name mappings. Saves to data/processed/names_cn.json.
"""

import json
import re
import time
import sys
from pathlib import Path
from collections import defaultdict

import requests
import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_RAW, DATA_PROCESSED

CHINESE_RESULTS = "https://racing.hkjc.com/racing/information/chinese/Racing/LocalResults.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}


def parse_horse_name_cn(raw: str):
    """'最好玩(H442)' -> ('最好玩', 'H442')"""
    m = re.match(r"(.+?)\((\w+\d+)\)$", raw)
    if m:
        return m.group(1).strip(), m.group(2)
    return raw.strip(), ""


def find_results_table(soup):
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        cells = first_row.find_all(["th", "td"])
        texts = [c.get_text(strip=True) for c in cells]
        if "馬名" in texts and "騎師" in texts and len(cells) >= 11:
            return table
    return None


def scrape_cn_race(session, race_date: str, race_no: int) -> list:
    """Return list of {horse_id, horse_no, name_cn, jockey_cn, trainer_cn} for one race."""
    params = {"RaceDate": race_date, "RaceNo": race_no}
    try:
        resp = session.get(CHINESE_RESULTS, params=params, timeout=60)
        soup = BeautifulSoup(resp.content, "lxml")
    except Exception:
        return []

    table = find_results_table(soup)
    if not table:
        return []

    results = []
    for row in table.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        texts = [c.get_text(strip=True) for c in cols]

        horse_no = int(re.findall(r"\d+", texts[1])[0]) if texts[1].strip().isdigit() else 0
        if horse_no == 0:
            continue

        name_cn, horse_id = parse_horse_name_cn(texts[2])
        jockey_cn = texts[3] if len(texts) > 3 else ""
        trainer_cn = texts[4] if len(texts) > 4 else ""

        if horse_id and name_cn:
            results.append({
                "horse_id": horse_id,
                "horse_no": horse_no,
                "name_cn": name_cn,
                "jockey_cn": jockey_cn,
                "trainer_cn": trainer_cn,
            })

    return results


def main():
    en = pd.read_csv(DATA_RAW / "race_results.csv", low_memory=False)
    dates = sorted(en["race_date"].unique())
    logger.info(f"English data: {len(en)} records, {len(dates)} dates")

    # Build English horse_id → name/jockey/trainer lookup (from English data)
    en_by_race = {}
    for _, row in en.iterrows():
        key = (row["race_date"], int(row["race_no"]), str(row["horse_id"]))
        en_by_race[key] = {
            "name_en": str(row["horse_name"]),
            "jockey_en": str(row["jockey"]),
            "trainer_en": str(row["trainer"]),
        }

    # Resume support: load partial progress
    progress_file = DATA_PROCESSED / "names_cn_progress.json"
    horse_map, jockey_map, trainer_map, done_dates = {}, {}, {}, set()
    if progress_file.exists():
        with open(progress_file) as f:
            prev = json.load(f)
        horse_map = prev.get("horses", {})
        jockey_map = prev.get("jockeys", {})
        trainer_map = prev.get("trainers", {})
        done_dates = set(prev.get("done_dates", []))
        logger.info(f"Resumed: {len(horse_map)} horses, {len(done_dates)} dates done")

    remaining = [d for d in dates if d not in done_dates]
    logger.info(f"Remaining: {len(remaining)} dates")

    session = requests.Session()
    session.headers.update(HEADERS)

    def save_progress():
        with open(progress_file, "w") as f:
            json.dump({
                "horses": horse_map, "jockeys": jockey_map, "trainers": trainer_map,
                "done_dates": sorted(done_dates),
            }, f, ensure_ascii=False)

    for i, d in enumerate(tqdm(remaining, desc="Scraping Chinese")):
        for race_no in range(1, 12):
            cn_results = scrape_cn_race(session, d, race_no)
            if not cn_results and race_no == 1:
                break  # no races today
            if not cn_results:
                continue

            for cr in cn_results:
                key = (d, race_no, cr["horse_id"])
                en_row = en_by_race.get(key)
                if not en_row:
                    continue
                horse_map[en_row["name_en"]] = cr["name_cn"]
                if en_row["jockey_en"]:
                    jockey_map[en_row["jockey_en"]] = cr["jockey_cn"]
                if en_row["trainer_en"]:
                    trainer_map[en_row["trainer_en"]] = cr["trainer_cn"]

            time.sleep(1.0)  # gentler rate limit (avoid HKJC throttle)

        done_dates.add(d)
        time.sleep(0.5)

        # Incremental save every 20 dates
        if (i + 1) % 20 == 0:
            save_progress()
            logger.info(f"Progress saved: {len(horse_map)} horses, {len(done_dates)} dates")

    save_progress()

    payload = {
        "horses": horse_map,
        "jockeys": jockey_map,
        "trainers": trainer_map,
    }
    out = DATA_PROCESSED / "names_cn.json"
    with open(out, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    logger.info(f"Saved {len(horse_map)} horses, {len(jockey_map)} jockeys, "
                f"{len(trainer_map)} trainers to {out}")


if __name__ == "__main__":
    main()
