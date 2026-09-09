"""Race card scraper + synthetic fallback for live (upcoming) races.

HKJC RaceCard.aspx shows declared runners for upcoming races. During
off-season there are no declarations, so a synthetic generator builds
race cards from historical data for testing the live pipeline.
"""

import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from config import DATA_RAW

RACE_CARD_COLUMNS = [
    "race_date", "venue", "race_no", "race_class", "distance", "going",
    "course", "rating_band", "horse_name", "horse_id", "horse_no", "draw",
    "jockey", "trainer", "weight", "declared_weight", "finish_pos", "margin",
    "running_position", "finish_time", "win_odds", "prize", "sectional_time",
    "incident_remark", "quinella_div", "quinella_place_div",
]


@dataclass
class RaceCardRunner:
    horse_no: int
    horse_name: str
    jockey: str
    trainer: str
    weight: int
    draw: int
    declared_weight: int = 0


def runners_to_dataframe(runners: List[RaceCardRunner], race_info: Dict) -> pd.DataFrame:
    """Convert race card runners + race info into the raw-results schema,
    with result fields left as NaN (live races have no results yet)."""
    rows = []
    for r in runners:
        row = {col: np.nan for col in RACE_CARD_COLUMNS}
        row.update({
            "race_date": race_info["race_date"],
            "venue": race_info["venue"],
            "race_no": race_info["race_no"],
            "race_class": race_info.get("race_class", ""),
            "distance": race_info.get("distance", 0),
            "going": race_info.get("going", ""),
            "course": race_info.get("course", ""),
            "rating_band": race_info.get("rating_band", ""),
            "horse_name": r.horse_name,
            "horse_id": "",
            "horse_no": r.horse_no,
            "draw": r.draw,
            "jockey": r.jockey,
            "trainer": r.trainer,
            "weight": r.weight,
            "declared_weight": r.declared_weight,
            "finish_pos": np.nan,
            "margin": "",
            "running_position": "",
            "finish_time": "",
            "win_odds": np.nan,
            "prize": "",
            "sectional_time": "",
            "incident_remark": "",
            "quinella_div": 0.0,
            "quinella_place_div": 0.0,
        })
        rows.append(row)
    return pd.DataFrame(rows)


class RaceCardScraper:
    """Scrape upcoming race declarations from HKJC RaceCard.aspx."""

    BASE = "https://racing.hkjc.com/racing/information/English/Racing"

    def get_race_card(self, race_date: str, venue: str, race_no: int) -> Dict:
        """Return {race_info, runners} for an upcoming race.

        Best-effort HTML scrape. Returns empty runners if no declarations
        (off-season) or parse fails — caller should fall back to synthetic.
        """
        import requests
        from bs4 import BeautifulSoup

        url = f"{self.BASE}/RaceCard.aspx"
        params = {"RaceDate": race_date, "RaceNo": race_no, "Venue": venue}
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            soup = BeautifulSoup(resp.content, "lxml")
        except Exception:
            return {"race_info": {}, "runners": []}

        race_info = self._parse_race_header(soup, race_no)
        runners = self._parse_runners(soup)
        return {"race_info": race_info, "runners": runners}

    def _parse_race_header(self, soup, race_no: int) -> Dict:
        """Parse 'Race 1 - NAME ... 1200M, Good ... Rating: 40-0, Class 5' header."""
        import re
        text = soup.get_text(" ", strip=True)

        header = {}
        # Header spans from 'Race {n}' to the next 'Race ' or 'SETUP'
        m = re.search(rf"Race\s*{race_no}\s*[-–].*?(?=Race\s*{race_no + 1}\b|SETUP)", text, re.DOTALL)
        seg = m.group(0) if m else ""

        dist_m = re.search(r"(\d{3,4})M", seg)
        if dist_m:
            header["distance"] = int(dist_m.group(1))

        class_m = re.search(r"Class\s*(\d)", seg)
        if class_m:
            header["race_class"] = f"Class{class_m.group(1)}"
        elif re.search(r"Gr\.?\s*\d|Group\s*\d", seg, re.IGNORECASE):
            gm = re.search(r"(?:Gr\.?\s*|Group\s*)(\d)", seg, re.IGNORECASE)
            header["race_class"] = f"G{gm.group(1)}" if gm else ""

        going_m = re.search(r",\s*(Good|Good to Firm|Good to Yielding|Yielding|Soft|Heavy|Wet Fast|Slow|Standard)\s*(?:Prize|,|$)", seg, re.IGNORECASE)
        if going_m:
            header["going"] = going_m.group(1).upper()

        rating_m = re.search(r"Rating\s*:\s*(\d+\s*-\s*\d+)", seg)
        if rating_m:
            header["rating_band"] = rating_m.group(1)

        course_m = re.search(r'(TURF|AWT|Dirt)\s*,\s*"([^"]+)"', seg, re.IGNORECASE)
        if course_m:
            header["course"] = f'{course_m.group(1).upper()} - "{course_m.group(2)}"'

        prize_m = re.search(r"Prize\s*Money\s*:\s*\$?([\d,]+)", seg)
        if prize_m:
            header["prize"] = prize_m.group(1)

        return header

    def _parse_runners(self, soup) -> list:
        """Parse declared runners via header-name → index mapping (layout-agnostic)."""
        runners = []

        for table in soup.find_all("table"):
            header_map = None
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                texts = [c.get_text(strip=True) for c in cells]

                # Detect header row and map column names to indices.
                if header_map is None and "Horse No." in texts and "Jockey" in texts and "Trainer" in texts:
                    header_map = {
                        name: i for i, name in enumerate(texts)
                        if name in ("Horse No.", "Horse", "Brand No.", "Wt.", "Jockey", "Draw",
                                    "Trainer", "Horse Wt. (Declaration)")
                    }
                    continue

                if not header_map or "Horse No." not in header_map:
                    continue

                try:
                    horse_no = int(texts[header_map["Horse No."]]) if texts[header_map["Horse No."]].isdigit() else 0
                    if not horse_no:
                        continue
                    runners.append(RaceCardRunner(
                        horse_no=horse_no,
                        horse_name=texts[header_map.get("Horse", -1)] if "Horse" in header_map else "",
                        jockey=texts[header_map.get("Jockey", -1)] if "Jockey" in header_map else "",
                        trainer=texts[header_map.get("Trainer", -1)] if "Trainer" in header_map else "",
                        weight=_safe_int(texts[header_map["Wt."]]) if "Wt." in header_map else 0,
                        draw=_safe_int(texts[header_map["Draw"]]) if "Draw" in header_map else 0,
                        declared_weight=_safe_int(texts[header_map["Horse Wt. (Declaration)"]])
                        if "Horse Wt. (Declaration)" in header_map else 0,
                    ))
                except (ValueError, IndexError):
                    continue

            if runners:
                break

        return runners


def _safe_int(text: str) -> int:
    nums = re.findall(r"\d+", str(text))
    return int(nums[0]) if nums else 0


def synthetic_race_card(source_date: str, race_no: int, target_date: str,
                        venue: Optional[str] = None) -> Dict:
    """Build a race card from a historical race (for off-season testing).

    Takes a historical race's declared runners and race info, maps it to a
    future target date. Result fields are dropped (live race, no results).
    """
    raw = pd.read_csv(DATA_RAW / "race_results.csv", low_memory=False)
    mask = (raw["race_date"] == source_date) & (raw["race_no"] == race_no)
    race = raw[mask].copy()

    if race.empty:
        return {"race_info": {}, "runners": []}

    if venue:
        race = race[race["venue"] == venue]
    if race.empty:
        return {"race_info": {}, "runners": []}

    first = race.iloc[0]
    race_info = {
        "race_date": target_date,
        "venue": first.get("venue", "ST"),
        "race_no": race_no,
        "race_class": first.get("race_class", ""),
        "distance": int(first.get("distance", 0)),
        "going": first.get("going", ""),
        "course": first.get("course", ""),
        "rating_band": first.get("rating_band", ""),
    }

    runners = []
    for _, r in race.iterrows():
        runners.append(RaceCardRunner(
            horse_no=int(r.get("horse_no", 0)),
            horse_name=str(r.get("horse_name", "")),
            jockey=str(r.get("jockey", "")),
            trainer=str(r.get("trainer", "")),
            weight=int(r.get("weight", 0)),
            draw=int(r.get("draw", 0)),
            declared_weight=int(r.get("declared_weight", 0)),
        ))

    return {"race_info": race_info, "runners": runners}
