"""Async odds poller — tiered polling with dual source + drift detection.

Two sources (fastest first):
  1. bet.hkjc.com  — authenticated JSON API (near real-time, ~1s updates).
  2. racing.hkjc.com — public CurrentOdds page (15-30s cadence) as fallback.

Endpoints are discovered on a live race day via browser DevTools (XHR capture).
Plug them into fetch_bet_odds() / fetch_public_odds() below.

Tiered cadence (configurable via poll_tiers):
  [10, 30) min before start -> every 30s
  [ 5, 10) min before start -> every 5s
  [ 0,  5) min before start -> every 1s   (near-live window)
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Callable

import httpx
from loguru import logger

from src.signals.odds_scraper import (
    OddsSnapshot,
    OddsMovement,
    LiveOddsScraper,
)

# (minutes_before_lower, minutes_before_upper, interval_seconds)
DEFAULT_TIERS = [
    (10.0, 30.0, 30.0),
    (5.0, 10.0, 5.0),
    (0.0, 5.0, 1.0),
]


class OddsPoller:
    def __init__(
        self,
        race_date: str,
        venue: str,
        race_no: int,
        bet_base: str = "https://bet.hkjc.com",
        public_base: str = "https://racing.hkjc.com",
        cookies: Optional[Dict[str, str]] = None,
        poll_tiers: Optional[List[tuple]] = None,
        on_change: Optional[Callable[[str, List[OddsMovement], Dict[int, float]], None]] = None,
        on_snapshot: Optional[Callable[[OddsSnapshot], None]] = None,
    ):
        self.race_date = race_date
        self.venue = venue
        self.race_no = race_no
        self.race_key = f"{race_date}:{venue}:{race_no}"
        self.bet_base = bet_base.rstrip("/")
        self.public_base = public_base.rstrip("/")
        self.client = httpx.AsyncClient(cookies=cookies, timeout=5.0, follow_redirects=True)
        self.poll_tiers = poll_tiers or DEFAULT_TIERS
        self.on_change = on_change
        self.on_snapshot = on_snapshot
        self.prev: Optional[OddsSnapshot] = None
        # Reuse the drift-detection logic (methods don't use instance state).
        self._detector = LiveOddsScraper()

    # ---- Sources (fill in on race day) ----

    async def fetch_bet_odds(self) -> Dict[int, float]:
        """TODO: bet.hkjc.com authenticated JSON endpoint.

        Discover via DevTools -> Network -> XHR on the live odds page, then
        map the JSON to {horse_no: win_odds}.
        """
        resp = await self.client.get(
            f"{self.bet_base}/racing/odds.json",
            params={"date": self.race_date, "race": self.race_no},
        )
        resp.raise_for_status()
        return self._parse_bet(resp.json())

    async def fetch_public_odds(self) -> Dict[int, float]:
        """TODO: public racing.hkjc.com CurrentOdds (15-30s cadence) fallback."""
        return {}

    @staticmethod
    def _parse_bet(data) -> Dict[int, float]:
        return {}

    # ---- Poll loop ----

    def _interval_for(self, minutes_before: float) -> float:
        for lo, hi, interval in self.poll_tiers:
            if lo < minutes_before <= hi:
                return interval
        return 1.0

    async def poll_once(self, minutes_before: int) -> Optional[OddsSnapshot]:
        horses: Dict[int, float] = {}
        try:
            horses = await self.fetch_bet_odds()
        except Exception as e:
            logger.debug(f"bet API failed ({e}); falling back to public page")
            try:
                horses = await self.fetch_public_odds()
            except Exception as e2:
                logger.warning(f"public odds failed: {e2}")

        snap = OddsSnapshot(
            race_date=self.race_date,
            venue=self.venue,
            race_no=self.race_no,
            timestamp=datetime.now().isoformat(),
            minutes_before=minutes_before,
            horses=horses,
        )

        if self.prev is not None and self.prev.horses and horses:
            movements = self._detector.detect_movement(self.prev, snap)
            if movements and self.on_change:
                drift = self._detector.get_odds_drift_factor(movements)
                self.on_change(self.race_key, movements, drift)

        self.prev = snap
        if self.on_snapshot:
            self.on_snapshot(snap)
        return snap

    async def run(self, start_minutes: int = 30):
        """Poll from start_minutes before start down to 0."""
        remaining = float(start_minutes * 60)
        while remaining > 0:
            minutes_before = remaining / 60.0
            await self.poll_once(int(minutes_before))
            interval = self._interval_for(minutes_before)
            await asyncio.sleep(interval)
            remaining -= interval

    async def close(self):
        await self.client.aclose()
