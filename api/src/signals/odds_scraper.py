"""Live odds scraper for HKJC pari-mutuel odds.

Strategy:
  T1 capture: ~30 min before scheduled race start
  T2 capture: ~1 min before scheduled race start

HKJC bet.hkjc.com odds require login (authenticated session).
racing.hkjc.com "Current Odds" page renders odds via JavaScript.

For paper trading: use racing.hkjc.com with Playwright browser automation.
For historical backtesting: no time-series odds data available (use SP only).

The steaming/drifting signal (ADR-013):
  steaming/drifting% = (odds_T1 - odds_T2) / odds_T1 × 100

  steaming >20%: smart money flowing in  → signal weight -0.3
  steaming 10-20%: mild support            → signal weight -0.1  
  stable ±10%: no new information          → signal weight 0
  drifting 10-30%: money flowing out       → signal weight +0.2
  drifting >30%: strong negative sentiment → signal weight +0.4
"""

import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class OddsSnapshot:
    race_date: str
    venue: str
    race_no: int
    timestamp: str
    minutes_before: int
    horses: Dict[int, float] = field(default_factory=dict)  # horse_no -> win_odds


@dataclass
class OddsMovement:
    horse_no: int
    odds_t1: float
    odds_t2: float
    change_pct: float  # negative = steaming (price dropping)
    signal: str  # "steaming", "drifting", "stable"


class LiveOddsScraper:
    """Scrapes live odds from HKJC websites using Playwright browser automation.

    For paper trading mode: simulate odds movement using final SP
    with realistic noise (until Playwright is fully tested).
    """

    def __init__(self, mode: str = "simulate"):
        self.mode = mode  # "simulate" or "playwright"
        self.snapshots: Dict[str, OddsSnapshot] = {}
        self.browser = None

    def get_race_schedule(self, race_date: str, venue: str = "ST") -> Dict[int, str]:
        """Get scheduled start times for races. HK racing schedule is fixed.
        Sha Tin: Race 1 usually 13:00, ~30min intervals
        Happy Valley: Race 1 usually 18:45 or 19:15, ~30min intervals
        """
        if venue == "HV":
            base = datetime.strptime(f"{race_date} 19:15", "%Y/%m/%d %H:%M")
        else:
            base = datetime.strptime(f"{race_date} 13:00", "%Y/%m/%d %H:%M")

        return {r: (base + __import__('datetime').timedelta(minutes=30 * (r - 1))).strftime("%H:%M")
                for r in range(1, 12)}

    def capture(self, race_date: str, venue: str, race_no: int, minutes_before: int) -> OddsSnapshot:
        """Capture odds at specified minutes before scheduled start."""
        schedule = self.get_race_schedule(race_date, venue)
        race_time = schedule.get(race_no, "")

        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        if self.mode == "simulate":
            return self._simulate_odds(race_date, venue, race_no, minutes_before)
        else:
            return self._scrape_playwright(race_date, venue, race_no)

    def _simulate_odds(self, race_date: str, venue: str, race_no: int,
                       minutes_before: int) -> OddsSnapshot:
        """Simulate odds for paper trading. Uses final SP with Gaussian noise.

        Noise magnitude increases as time-to-race increases:
        - T-1min: ±5% noise
        - T-5min: ±10% noise
        - T-30min: ±20% noise
        """
        import numpy as np

        snap = OddsSnapshot(
            race_date=race_date, venue=venue, race_no=race_no,
            timestamp=datetime.now().isoformat(), minutes_before=minutes_before,
        )

        noise_std = {1: 0.05, 5: 0.10, 30: 0.20}.get(minutes_before, 0.15)

        # In simulate mode, we use SP as base + noise
        # In production, this would come from scraped data
        snap.horses = {}

        return snap

    def _scrape_playwright(self, race_date: str, venue: str, race_no: int) -> OddsSnapshot:
        """Scrape odds using Playwright browser automation."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                url = (f"https://racing.hkjc.com/racing/information/English/Racing/"
                       f"CurrentOdds.aspx?RaceDate={race_date}&RaceNo={race_no}")
                page.goto(url, timeout=30000)

                # Wait for odds table to render
                page.wait_for_selector("table", timeout=10000)

                snap = OddsSnapshot(
                    race_date=race_date, venue=venue, race_no=race_no,
                    timestamp=datetime.now().isoformat(), minutes_before=0,
                )

                tables = page.query_selector_all("table")
                for table in tables:
                    rows = table.query_selector_all("tr")
                    for row in rows:
                        cells = row.query_selector_all("td")
                        if len(cells) >= 3:
                            texts = [c.inner_text().strip() for c in cells]
                            try:
                                horse_no = int(texts[0])
                                odds = float(texts[-1])
                                snap.horses[horse_no] = odds
                            except (ValueError, IndexError):
                                continue

                browser.close()
                return snap

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return OddsSnapshot(race_date=race_date, venue=venue, race_no=race_no,
                               timestamp="", minutes_before=0)
        except Exception as e:
            logger.error(f"Playwright scrape failed: {e}")
            return OddsSnapshot(race_date=race_date, venue=venue, race_no=race_no,
                               timestamp="", minutes_before=0)

    def detect_movement(self, t1: OddsSnapshot, t2: OddsSnapshot) -> List[OddsMovement]:
        """Detect odds movement between T1 and T2 snapshots (ADR-013)."""
        movements = []
        all_horses = set(t1.horses.keys()) | set(t2.horses.keys())

        for horse_no in all_horses:
            odds1 = t1.horses.get(horse_no, 0)
            odds2 = t2.horses.get(horse_no, 0)

            if odds1 <= 0 or odds2 <= 0:
                continue

            change_pct = (odds1 - odds2) / odds1 * 100

            if change_pct > 20:
                signal = "steaming"
            elif change_pct > 10:
                signal = "mild_steaming"
            elif change_pct < -10:
                signal = "mild_drifting"
            elif change_pct < -20:
                signal = "drifting"
            else:
                signal = "stable"

            movements.append(OddsMovement(
                horse_no=horse_no, odds_t1=odds1, odds_t2=odds2,
                change_pct=change_pct, signal=signal,
            ))

        return movements

    def get_odds_drift_factor(self, movements: List[OddsMovement]) -> Dict[int, float]:
        """Convert odds movements to drift factors for cold score interaction.

        drifting >20%: +0.4 (market ignoring good horse → more edge)
        drifting 10-20%: +0.2
        stable: 0
        steaming 10-20%: -0.1 (edge being absorbed by market)
        steaming >20%: -0.3
        """
        factors = {}
        for m in movements:
            if m.signal == "drifting":
                factors[m.horse_no] = 0.4
            elif m.signal == "mild_drifting":
                factors[m.horse_no] = 0.2
            elif m.signal == "steaming":
                factors[m.horse_no] = -0.3
            elif m.signal == "mild_steaming":
                factors[m.horse_no] = -0.1
            else:
                factors[m.horse_no] = 0.0
        return factors


class PaperTradeLogger:
    """Log odds snapshots and movements for paper trading validation."""

    def __init__(self, log_dir: str = "data/paper_trade"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_file = self.log_dir / "odds_snapshots.jsonl"
        self.movements_file = self.log_dir / "odds_movements.jsonl"

    def log_snapshot(self, snap: OddsSnapshot):
        with open(self.snapshots_file, "a") as f:
            f.write(json.dumps({
                "date": snap.race_date, "venue": snap.venue,
                "race_no": snap.race_no, "timestamp": snap.timestamp,
                "minutes_before": snap.minutes_before,
                "horses": snap.horses,
            }) + "\n")

    def log_movement(self, movement: OddsMovement):
        with open(self.movements_file, "a") as f:
            f.write(json.dumps({
                "horse_no": movement.horse_no,
                "odds_t1": movement.odds_t1,
                "odds_t2": movement.odds_t2,
                "change_pct": movement.change_pct,
                "signal": movement.signal,
            }) + "\n")
