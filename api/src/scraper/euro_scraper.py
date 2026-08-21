"""UK/IRE flat racing scraper — RacingPost full result pages (plain HTTP, no browser).

Flow:
  1. GET /results/{date}             -> meetings (course, going) + races (title,
                                         distance, class, prize, time, Ex dividend,
                                         full-result URL)
  2. GET /results/{course_id}/{slug}/{date}/{race_id}  -> full per-horse data
                                         (pos/draw/name/SP/jockey/trainer/age/
                                         weight/OR) + window.horseData JSON
                                         (raceTypeCode for flat filter, weight lbs)
  3. Keep flat races only (raceTypeCode == "F").

Output schema matches HK race_results.csv so feature_engine processes it
identically. Ex (Exacta, 1st+2nd any order) maps to quinella_div == 連贏.
"""

import re
import time
import json
import random
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
from loguru import logger
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_RAW

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

BASE = "https://www.racingpost.com"

# Output columns = HK RACE_CARD_COLUMNS + UK extras
OUTPUT_COLUMNS = [
    "race_date", "venue", "race_no", "race_class", "distance", "going",
    "course", "rating_band", "horse_name", "horse_id", "horse_no", "draw",
    "jockey", "trainer", "weight", "declared_weight", "finish_pos", "margin",
    "running_position", "finish_time", "win_odds", "prize", "sectional_time",
    "incident_remark", "quinella_div", "quinella_place_div",
    "age", "or", "country", "race_name", "race_type",
]

# Flat race type codes (F = flat, NHF = national hunt flat/bumper)
FLAT_TYPES = {"F", "NHF"}


_session = requests.Session()
_session.headers.update(HEADERS)


def _get(url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    for attempt in range(retries):
        try:
            resp = _session.get(url, timeout=30)
            if resp.status_code == 200:
                return BeautifulSoup(resp.content, "lxml")
            logger.debug(f"{resp.status_code} for {url} (attempt {attempt + 1})")
        except Exception as e:
            logger.debug(f"Fetch error {url}: {e}")
        # 406 = rate limited; back off progressively (3s, 9s, 27s)
        time.sleep(3 * (3 ** attempt))
    logger.warning(f"Failed after {retries} attempts (rate-limited?): {url}")
    return None


def _furlongs_to_meters(dist: str) -> int:
    """'6f' -> 1207, '1m' -> 1609, '1m 2f' -> 2012."""
    if not dist:
        return 0
    miles = re.search(r"(\d+)\s*m", dist)
    furlongs = re.search(r"(\d+)\s*f", dist)
    m = int(miles.group(1)) if miles else 0
    f = int(furlongs.group(1)) if furlongs else 0
    return round((m * 8 + f) * 201.168)


def _frac_to_dec(odds: str) -> float:
    if not odds:
        return 0.0
    odds = re.sub(r"[FJC]$", "", odds.strip())
    if odds.lower() in ("evens",):
        return 2.0
    m = re.match(r"^(\d+)/(\d+)$", odds)
    if m:
        return round(int(m.group(1)) / int(m.group(2)) + 1.0, 2)
    return 0.0


def _parse_going(raw: str) -> tuple:
    """Return (going_code, course). Normalize UK going to HK-style code."""
    if not raw:
        return "", ""
    g = raw.upper().split("(")[0].strip()
    if "POLYTRACK" in g or "TAPETA" in g or "ALL WEATHER" in g or "FIBRESAND" in g:
        course = "AWT"
        going = "STANDARD"
    else:
        course = "TURF"
        if "HEAVY" in g:
            going = "HEAVY"
        elif "SOFT" in g and "GOOD" in g:
            going = "GOOD TO SOFT"
        elif "SOFT" in g:
            going = "SOFT"
        elif "FIRM" in g and "GOOD" in g:
            going = "GOOD TO FIRM"
        elif "FIRM" in g:
            going = "FIRM"
        elif "YIELDING" in g:
            going = "YIELDING"
        else:
            going = "GOOD"
    return going, course


def _extract_json(html: str, prefix: str) -> Optional[dict]:
    """Extract a JS object literal following `prefix = {...};`."""
    i = html.find(prefix)
    if i < 0:
        return None
    start = html.find("{", i)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start:j + 1])
                    except Exception:
                        return None
    return None


def _parse_div(text: str) -> float:
    """Extract Ex/Exacta dividend from postRaceInfo text like 'Ex: £76.70'."""
    m = re.search(r"Ex:\s*[£€]?\s*([\d,]+\.?\d*)", text)
    return float(m.group(1).replace(",", "")) if m else 0.0


def scrape_list(date_str: str) -> List[dict]:
    """Parse /results/{date} -> list of race dicts (meta + detail url + ex div)."""
    soup = _get(f"{BASE}/results/{date_str}")
    if not soup:
        return []

    races = []
    current_course = ""
    current_going_raw = ""
    current_country = "UK"
    course_race_no = 0

    # Iterate the page in document order, tracking course + going + races.
    for block in soup.select(".rp-raceCourse__row, .rp-raceCourse__panel__race, dt"):
        classes = " ".join(block.get("class", []))
        if "rp-raceCourse__row" in classes:
            name_el = block.select_one(".rp-raceCourse__row__name")
            if name_el:
                name = name_el.get_text(" ", strip=True)
                if name and name not in ("WORLD POOL RACES", "WORLDWIDE STAKES"):
                    clean = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
                    current_course = clean.title()
                    if "(IRE)" in name:
                        current_country = "IRE"
                    elif "(FR)" in name or "(USA)" in name or "(GER)" in name:
                        current_country = "FR"
                    else:
                        current_country = "UK"
                    course_race_no = 0
            continue

        if block.name == "dt":
            dt_text = block.get_text(strip=True)
            if dt_text.startswith("Going"):
                dd = block.find_next_sibling("dd")
                if dd:
                    current_going_raw = dd.get_text(" ", strip=True)
            continue

        # race block
        title_el = block.select_one(".rp-raceCourse__panel__race__info__title")
        dist_el = block.select_one(".rp-raceCourse__panel__race__info__distance")
        time_el = block.select_one(".rp-raceCourse__panel__race__time")
        link_el = block.select_one("a[href*='/results/']")
        if not (title_el and link_el):
            continue

        href = link_el.get("href", "")
        m = re.search(r"/results/\d+/([^/]+)/([\d-]+)/(\d+)", href)
        if not m:
            continue

        course_race_no += 1
        small = block.select_one(".rp-raceCourse__panel__race__info__smallDetails")
        small_text = small.get_text(" ", strip=True) if small else ""
        cls_match = re.search(r"Class\s*(\d+)", small_text)
        prize_match = re.search(r"[£€]([\d,]+\.?\d*)", small_text)
        prize = ""
        if prize_match:
            prize = "£" + prize_match.group(1)

        post = block.select_one(".rp-raceCourse__panel__race__info__postRaceInfo")
        post_text = post.get_text(" ", strip=True) if post else ""
        ex_div = _parse_div(post_text)

        going, course = _parse_going(current_going_raw)

        races.append({
            "race_date": date_str,
            "venue": current_course,
            "country": current_country,
            "race_no": course_race_no,
            "race_name": title_el.get_text(strip=True),
            "distance_str": dist_el.get_text(strip=True) if dist_el else "",
            "distance": _furlongs_to_meters(dist_el.get_text(strip=True) if dist_el else ""),
            "race_class": f"Class {cls_match.group(1)}" if cls_match else "",
            "going": going,
            "course": course,
            "prize": prize,
            "race_time": time_el.get_text(strip=True) if time_el else "",
            "detail_url": BASE + href,
            "ex_dividend": ex_div,
        })

    return races


def scrape_detail(race: dict) -> List[dict]:
    """Parse a full-result page -> per-horse rows."""
    soup = _get(race["detail_url"])
    if not soup:
        return []

    html = str(soup)
    horse_data = _extract_json(html, "window.horseData")
    race_type = ""
    wgt_by_pos: Dict[int, int] = {}
    horse_id_by_pos: Dict[int, str] = {}
    if horse_data:
        race_type = str(horse_data.get("raceTypeCode", ""))
        for item in horse_data.get("items", []):
            try:
                pos = int(item.get("outcomeCode", "0"))
            except (ValueError, TypeError):
                continue
            wgt_by_pos[pos] = int(item.get("wgtStNative", 0) or 0)
            ri = item.get("runnerInfo") or {}
            horse_id_by_pos[pos] = str(ri.get("horseId", ""))

    rows = []
    for row in soup.select(".rp-horseTable__mainRow"):
        pos_num = row.select_one(".rp-horseTable__pos__number")
        pos_text = pos_num.get_text(strip=True) if pos_num else ""
        pm = re.match(r"(\d+)\s*\((\d+)\)", pos_text)
        if not pm:
            continue
        finish_pos = int(pm.group(1))
        draw = int(pm.group(2))

        saddle = row.select_one(".rp-horseTable__saddleClothNo")
        horse_no = int(re.findall(r"\d+", saddle.get_text(strip=True))[0]) if saddle else 0

        name_el = row.select_one(".rp-horseTable__horse__name")
        price_el = row.select_one(".rp-horseTable__horse__price")
        age_el = row.select_one(".rp-horseTable__spanNarrow_age")

        humans = row.select(".rp-horseTable__human__wrapper")
        jockey, trainer = "", ""
        for h in humans:
            prefix = h.get("data-prefix", "")
            txt = h.get_text(" ", strip=True)
            if prefix == "J:":
                jockey = txt
            elif prefix == "T:":
                trainer = txt

        # OR = the spanNarrow cell after age + weight (skip those two)
        or_rating = None
        for span in row.select(".rp-horseTable__spanNarrow"):
            cls = " ".join(span.get("class", []))
            if "age" in cls or "wgt" in cls:
                continue
            txt = span.get_text(strip=True)
            or_rating = float(txt) if re.match(r"^\d+$", txt) else None
            break

        rows.append({
            "finish_pos": finish_pos,
            "draw": draw,
            "horse_no": horse_no,
            "horse_name": name_el.get_text(strip=True) if name_el else "",
            "win_odds_frac": price_el.get_text(strip=True) if price_el else "",
            "win_odds": _frac_to_dec(price_el.get_text(strip=True) if price_el else ""),
            "jockey": jockey,
            "trainer": trainer,
            "age": int(age_el.get_text(strip=True)) if age_el and age_el.get_text(strip=True).isdigit() else 0,
            "weight": wgt_by_pos.get(finish_pos, 0),
            "or": or_rating,
            "horse_id": horse_id_by_pos.get(finish_pos, ""),
        })

    # skip if race type is not flat
    if race_type and race_type not in FLAT_TYPES:
        return []

    # mark quinella_div (= Ex) for the 1st/2nd horses
    ex = race["ex_dividend"]
    for r in rows:
        r["quinella_div"] = ex if r["finish_pos"] in (1, 2) else 0.0

    out = []
    for r in rows:
        rec = {c: "" for c in OUTPUT_COLUMNS}
        rec.update({
            "race_date": race["race_date"],
            "venue": race["venue"],
            "race_no": race["race_no"],
            "race_class": race["race_class"],
            "distance": race["distance"],
            "going": race["going"],
            "course": race["course"],
            "rating_band": "",
            "horse_name": r["horse_name"],
            "horse_id": r["horse_id"],
            "horse_no": r["horse_no"],
            "draw": r["draw"],
            "jockey": r["jockey"],
            "trainer": r["trainer"],
            "weight": r["weight"],
            "declared_weight": r["weight"],
            "finish_pos": r["finish_pos"],
            "margin": "",
            "running_position": "",
            "finish_time": "",
            "win_odds": r["win_odds"],
            "prize": race["prize"],
            "sectional_time": "",
            "incident_remark": "",
            "quinella_div": r["quinella_div"],
            "quinella_place_div": 0.0,
            "age": r["age"],
            "or": r["or"],
            "country": race["country"],
            "race_name": race["race_name"],
            "race_type": race_type or "F",
        })
        out.append(rec)
    return out


def probe() -> bool:
    """Return True if full-result detail pages are currently accessible."""
    return _get(f"{BASE}/results/107/york/2026-08-20/910568") is not None


def scrape_date(date_str: str) -> List[dict]:
    """Full scrape of one date: list -> details -> flat rows."""
    races = scrape_list(date_str)
    if not races:
        logger.info(f"{date_str}: no races found")
        return []

    rows = []
    flat_races = 0
    for i, race in enumerate(races):
        if race["country"] not in ("UK", "IRE"):
            continue
        detail_rows = scrape_detail(race)
        if detail_rows:
            rows.extend(detail_rows)
            flat_races += 1
        # slow + jittered delay to stay under RacingPost's rate limit
        time.sleep(3.0 + random.random() * 2.0)

    logger.info(f"{date_str}: {len(races)} races, {flat_races} flat, {len(rows)} horses")
    return rows


def batch_scrape(start: str, end: str) -> "pd.DataFrame":
    import pandas as pd
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    all_rows = []
    current = start_dt
    while current <= end_dt:
        d = current.strftime("%Y-%m-%d")
        rows = scrape_date(d)
        all_rows.extend(rows)
        current += timedelta(days=1)
        time.sleep(0.5)

    df = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS) if all_rows else pd.DataFrame(columns=OUTPUT_COLUMNS)
    if not df.empty:
        path = DATA_RAW / "uk_race_results.csv"
        df.to_csv(path, index=False)
        logger.info(f"Saved {len(df)} UK rows to {path}")
    return df


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-08-20"
    for r in scrape_date(date)[:6]:
        print(f"{r['race_date']} {r['venue']:18s} R{r['race_no']} {r['race_name'][:30]:30s} "
              f"{r['distance']}m {r['going']:12s} #{r['finish_pos']} {r['horse_name']:20s} "
              f"J:{r['jockey']:18s} T:{r['trainer']:18s} w{r['weight']} or={r['or']} odds={r['win_odds']}")
