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

        runners = []
        # HKJC race card table: [HorseNo, Horse, Wt, Jockey, Trainer, Draw, Rating, ...]
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 7:
                    continue
                texts = [c.get_text(strip=True) for c in cols]
                try:
                    horse_no = int(texts[0]) if texts[0].isdigit() else 0
                    if not horse_no:
                        continue
                    runners.append(RaceCardRunner(
                        horse_no=horse_no,
                        horse_name=texts[1] if len(texts) > 1 else "",
                        jockey=texts[3] if len(texts) > 3 else "",
                        trainer=texts[4] if len(texts) > 4 else "",
                        weight=_safe_int(texts[2]) if len(texts) > 2 else 0,
                        draw=_safe_int(texts[5]) if len(texts) > 5 else 0,
                    ))
                except (ValueError, IndexError):
                    continue

        return {"race_info": {}, "runners": runners}


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
