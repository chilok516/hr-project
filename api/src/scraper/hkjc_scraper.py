import re
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from dataclasses import dataclass, field, asdict
from loguru import logger
from tqdm import tqdm
import pandas as pd

from config import HKJC_BASE, DATA_RAW

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-HK;q=0.8,zh;q=0.7",
}


@dataclass
class HorseResult:
    race_date: str
    venue: str
    race_no: int
    race_class: str
    distance: int
    going: str
    course: str
    rating_band: str
    horse_name: str
    horse_id: str = ""
    horse_no: int = 0
    draw: int = 0
    jockey: str = ""
    trainer: str = ""
    weight: int = 0
    declared_weight: int = 0
    finish_pos: int = 0
    margin: str = ""
    running_position: str = ""
    finish_time: str = ""
    win_odds: float = 0.0
    prize: str = ""
    sectional_time: str = ""
    incident_remark: str = ""
    quinella_div: float = 0.0
    quinella_place_div: float = 0.0


class HKJCScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.last_request = 0.0
        self.min_interval = 0.5

    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request = time.time()

    def _get(self, url: str, params: dict = None) -> Optional[BeautifulSoup]:
        self._rate_limit()
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.content, "lxml")
        except Exception as e:
            logger.error(f"Fetch failed {url}: {e}")
            return None

    def get_race_dates(self) -> list[str]:
        """Get all available race dates from ResultsAll page dropdown."""
        soup = self._get(
            f"{HKJC_BASE}/racing/information/English/Racing/ResultsAll.aspx"
        )
        if not soup:
            return []

        dates = []
        for select in soup.find_all("select"):
            for option in select.find_all("option"):
                val = option.get("value", "")
                if val and re.match(r"\d{4}/\d{2}/\d{2}", val):
                    dates.append(val)
        return sorted(dates)

    def get_race_numbers_for_date(self, race_date: str) -> list[int]:
        """Get race numbers for a given date from ResultsAll page."""
        soup = self._get(
            f"{HKJC_BASE}/racing/information/English/Racing/ResultsAll.aspx",
            {"RaceDate": race_date},
        )
        if not soup:
            return []

        race_nos = set()
        race_div = soup.find("div", class_="race_result")
        if not race_div:
            return []

        for div in race_div.find_all("div"):
            text = div.get_text(strip=True)
            m = re.search(r"Race\s*(\d+)", text)
            if m:
                race_nos.add(int(m.group(1)))

        return sorted(race_nos)

    def _parse_dividend_table(self, soup: BeautifulSoup) -> dict:
        """Parse QUINELLA and QUINELLA PLACE dividends from the dividend table.
        Returns dict with keys 'quinella' and 'quinella_place', each mapping
        horse_no -> dividend_amount for horses in winning combos.
        """
        result = {"quinella": {}, "quinella_place": {}}

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 5:
                continue

            first_row_texts = [c.get_text(strip=True) for c in rows[0].find_all(["td", "th"])]
            if "Dividend" not in str(first_row_texts) and "Pool" not in str(first_row_texts):
                continue

            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                texts = [c.get_text(strip=True) for c in cols]
                pool = texts[0] if len(texts) > 0 else ""
                combo = texts[1] if len(texts) > 1 else ""
                dividend = self._safe_float(texts[2]) if len(texts) > 2 else 0.0

                if dividend <= 0:
                    continue

                if pool == "QUINELLA":
                    horses = [int(x.strip()) for x in combo.split(",")]
                    for h in horses:
                        result["quinella"][h] = dividend

                elif pool == "QUINELLA PLACE":
                    horses = [int(x.strip()) for x in combo.split(",")]
                    for h in horses:
                        result["quinella_place"][h] = dividend

            return result

        return result

    def get_race_results_detailed(self, race_date: str, race_no: int) -> list[HorseResult]:
        """Get full race results from LocalResults page."""
        soup = self._get(
            f"{HKJC_BASE}/racing/information/English/Racing/LocalResults.aspx",
            {"RaceDate": race_date, "RaceNo": race_no},
        )
        if not soup:
            return []

        venue = self._detect_venue_from_page(soup)
        race_header = self._parse_detailed_race_header(soup, race_no)
        results_table = self._find_results_table(soup)
        incidents = self._parse_incident_table(soup)
        dividends = self._parse_dividend_table(soup)

        if not results_table:
            return []

        results = []
        rows = results_table.find_all("tr")

        for row in rows[1:]:
            cols = row.find_all("td")
            if len(cols) < 11:
                continue

            texts = [c.get_text(strip=True) for c in cols]

            finish_pos = self._safe_int(texts[0])
            if finish_pos == 0:
                # Could be scratched horse
                continue

            horse_no = self._safe_int(texts[1])
            horse_name_raw = texts[2] if len(texts) > 2 else ""
            horse_name, horse_id = self._parse_horse_name(horse_name_raw)

            horse_link = cols[2].find("a") if len(cols) > 2 else None
            if horse_link and not horse_id:
                href = horse_link.get("href", "")
                id_match = re.search(r"HorseId=([^&]+)", href)
                if id_match:
                    horse_id = id_match.group(1)

            results.append(HorseResult(
                race_date=race_date,
                venue=venue,
                race_no=race_no,
                race_class=race_header.get("race_class", ""),
                distance=race_header.get("distance", 0),
                going=race_header.get("going", ""),
                course=race_header.get("course", ""),
                rating_band=race_header.get("rating_band", ""),
                horse_name=horse_name,
                horse_id=horse_id,
                horse_no=horse_no,
                draw=self._safe_int(texts[7]) if len(texts) > 7 else 0,
                jockey=texts[3] if len(texts) > 3 else "",
                trainer=texts[4] if len(texts) > 4 else "",
                weight=self._safe_int(texts[5]) if len(texts) > 5 else 0,
                declared_weight=self._safe_int(texts[6]) if len(texts) > 6 else 0,
                finish_pos=finish_pos,
                margin=texts[8] if len(texts) > 8 else "",
                running_position=texts[9] if len(texts) > 9 else "",
                finish_time=texts[10] if len(texts) > 10 else "",
                win_odds=self._safe_float(texts[11]) if len(texts) > 11 else 0.0,
                prize=race_header.get("prize", ""),
                sectional_time=race_header.get("sectional_time", ""),
                incident_remark=incidents.get(horse_no, ""),
                quinella_div=dividends["quinella"].get(horse_no, 0.0),
                quinella_place_div=dividends["quinella_place"].get(horse_no, 0.0),
            ))

        return results

    def _detect_venue_from_page(self, soup: BeautifulSoup) -> str:
        text = soup.get_text()
        if "Happy Valley" in text:
            return "HV"
        return "ST"

    def _find_results_table(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        for table in soup.find_all("table"):
            first_row = table.find("tr")
            if not first_row:
                continue
            cells = first_row.find_all(["th", "td"])
            texts = [c.get_text(strip=True) for c in cells]
            if "Pla." in texts and len(cells) >= 11:
                return table
        return None

    def _parse_incident_table(self, soup: BeautifulSoup) -> dict:
        incidents = {}

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue

            first_row = rows[0]
            cells = first_row.find_all(["th", "td"])
            if not cells:
                continue

            header_texts = [c.get_text(strip=True) for c in cells]

            # Incident table: exactly 4 cols [Pla., Horse No., Horse, Incident]
            if len(cells) == 4 and "Pla." in header_texts and "Incident" in header_texts:
                for row in rows[1:]:
                    cols = row.find_all("td")
                    if len(cols) < 4:
                        continue
                    texts = [c.get_text(strip=True) for c in cols]
                    horse_no = self._safe_int(texts[1])
                    remark = texts[3] if len(texts) > 3 else ""
                    if horse_no > 0 and remark:
                        incidents[horse_no] = remark
                return incidents

        return incidents

    def _parse_detailed_race_header(self, soup: BeautifulSoup, race_no: int) -> dict:
        """Parse header like:
        'RACE 1 (782) Class 4 - 1000M - (60-40)
         Going : GOOD
         RACING GOES ON 1000M HANDICAP
         Course : TURF - "B" Course
         HK$ 1,170,000
         Time : (12.70)(33.34)(56.22)
         Sectional Time : 12.70 20.64 10.11  10.53 22.88 11.09'
        """
        header = {}
        full_text = soup.get_text()

        # Find race tab div
        race_tab = soup.find("div", class_="race_tab")
        if race_tab:
            text = race_tab.get_text(" ", strip=True)
        else:
            text = full_text

        # Race number
        m = re.search(rf"RACE\s*{race_no}\s*\(\d+\)", text)
        if not m:
            m = re.search(rf"Race\s*{race_no}", text)

        # Class
        class_match = re.search(r"(Gr\.?\s*\d|Class\s*\d)", text, re.IGNORECASE)
        if class_match:
            cls = class_match.group(1)
            cls = cls.replace("Gr.", "G").replace(" ", "")
            header["race_class"] = cls

        # Distance
        dist_match = re.search(r"(\d+)M", text)
        if dist_match:
            header["distance"] = int(dist_match.group(1))

        # Rating band
        rating_match = re.search(r"\((\d+-\d+)\)", text)
        if rating_match:
            header["rating_band"] = rating_match.group(1)

        # Going
        going_match = re.search(r"Going\s*:\s*(\w+)", text, re.IGNORECASE)
        if going_match:
            header["going"] = going_match.group(1).upper()

        # Course
        course_match = re.search(r'Course\s*:\s*(\w+)\s*-\s*"([^"]+)"', text)
        if course_match:
            header["course"] = f'{course_match.group(1)} - "{course_match.group(2)}"'
        else:
            if "TURF" in text:
                header["course"] = "TURF"
            elif "AWT" in text:
                header["course"] = "AWT"

        # Prize
        prize_match = re.search(r'HK\$\s*([\d,]+)', text)
        if prize_match:
            header["prize"] = prize_match.group(1)

        # Sectional time
        sec_match = re.search(r'Sectional Time\s*:\s*(.+?)(?:\n|$)', text)
        if sec_match:
            header["sectional_time"] = sec_match.group(1).strip()

        return header

    def _parse_horse_name(self, raw: str) -> Tuple[str, str]:
        """Parse 'AMAZING FUN(H442)' -> ('AMAZING FUN', 'H442')."""
        m = re.match(r"(.+?)\((\w+\d+)\)$", raw)
        if m:
            return m.group(1).strip(), m.group(2)
        return raw.strip(), ""

    def _safe_int(self, text: str) -> int:
        nums = re.findall(r"-?\d+", text)
        return int(nums[0]) if nums else 0

    def _safe_float(self, text: str) -> float:
        nums = re.findall(r"\d+\.?\d*", text)
        return float(nums[0]) if nums else 0.0

    def scrape_date_range(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Scrape all race results between two dates."""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        dates = []
        current = start
        while current <= end:
            if current.weekday() in [2, 6]:  # Wed + Sun
                dates.append(current.strftime("%Y/%m/%d"))
            current += timedelta(days=1)

        return self._scrape_dates(dates)

    def scrape_all_available(self, max_dates: int = None) -> pd.DataFrame:
        """Scrape all available race dates from HKJC."""
        dates = self.get_race_dates()
        logger.info(f"Found {len(dates)} available race dates")
        if max_dates:
            dates = dates[:max_dates]
        return self._scrape_dates(dates)

    def _scrape_dates(self, dates: list[str]) -> pd.DataFrame:
        all_results = []

        for d in tqdm(dates, desc="Scraping race dates"):
            has_races = False
            for rn in range(1, 12):
                results = self.get_race_results_detailed(d, rn)
                if results:
                    all_results.extend(results)
                    has_races = True
                elif rn >= 2 and not has_races:
                    break

            # Rate limit already handled per-request

        df = pd.DataFrame([asdict(r) for r in all_results])
        path = DATA_RAW / "race_results.csv"
        df.to_csv(path, index=False)
        logger.info(f"Saved {len(df)} race results ({len(dates)} dates) to {path}")
        return df
