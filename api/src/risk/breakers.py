"""ADR-017: Circuit breaker state machine with priority hierarchy.

Priority: Drawdown(20%) > Weekly($5K) > Daily($2K) > Consecutive(8 losses)

Reset rules:
- Daily: Calendar day (HK midnight)
- Weekly: Calendar week (Monday 00:00)
- Drawdown: Manual reset only
- Consecutive: Auto-reset on next win
"""

from enum import Enum
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from loguru import logger

import pytz

HKT = pytz.timezone("Asia/Hong_Kong")


class BreakerState(Enum):
    NORMAL = "normal"
    RACE_PAUSE = "race_pause"      # 8 consecutive losses
    DAILY_STOP = "daily_stop"       # $2K daily loss
    WEEKLY_STOP = "weekly_stop"     # $5K weekly loss
    FULL_STOP = "full_stop"         # 20% drawdown


@dataclass
class CircuitBreaker:
    daily_loss_limit: float = 2000.0
    weekly_loss_limit: float = 5000.0
    drawdown_pct_limit: float = 0.20
    consecutive_loss_limit: int = 8

    state: BreakerState = BreakerState.NORMAL
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    peak_bankroll: float = 100_000.0
    current_bankroll: float = 100_000.0
    consecutive_losses: int = 0
    last_reset_daily: datetime = None
    last_reset_weekly: datetime = None

    def __post_init__(self):
        self.peak_bankroll = self.current_bankroll
        self.last_reset_daily = datetime.now(HKT)
        self.last_reset_weekly = datetime.now(HKT)

    def _check_reset(self):
        now = datetime.now(HKT)

        # Daily reset at midnight HKT
        if now.date() > self.last_reset_daily.date():
            self.daily_pnl = 0.0
            self.last_reset_daily = now
            if self.state == BreakerState.DAILY_STOP:
                self.state = BreakerState.NORMAL
                logger.info("Daily breaker reset")

        # Weekly reset on Monday
        if now.weekday() == 0 and now.date() > self.last_reset_weekly.date():
            self.weekly_pnl = 0.0
            self.last_reset_weekly = now
            if self.state == BreakerState.WEEKLY_STOP:
                self.state = BreakerState.NORMAL
                logger.info("Weekly breaker reset")

    def record_bet(self, profit: float):
        self._check_reset()

        self.current_bankroll += profit
        self.daily_pnl += profit
        self.weekly_pnl += profit

        if self.current_bankroll > self.peak_bankroll:
            self.peak_bankroll = self.current_bankroll

        if profit >= 0:
            self.consecutive_losses = 0
            if self.state == BreakerState.RACE_PAUSE:
                self.state = BreakerState.NORMAL
                logger.info("Consecutive loss streak broken — resuming")
        else:
            self.consecutive_losses += 1

        # Check breakers in priority order
        self._check_breakers()

    def _check_breakers(self):
        drawdown = (self.peak_bankroll - self.current_bankroll) / self.peak_bankroll

        # Priority 1: Drawdown (FULL STOP)
        if drawdown >= self.drawdown_pct_limit:
            if self.state != BreakerState.FULL_STOP:
                self.state = BreakerState.FULL_STOP
                logger.critical(
                    f"🔴 FULL STOP: Drawdown {drawdown:.1%} >= {self.drawdown_pct_limit:.0%}. "
                    f"Manual reset required."
                )

        # Priority 2: Weekly loss
        elif self.weekly_pnl <= -self.weekly_loss_limit:
            if self.state != BreakerState.WEEKLY_STOP:
                self.state = BreakerState.WEEKLY_STOP
                logger.error(
                    f"🔴 WEEKLY STOP: Week P&L ${self.weekly_pnl:,.0f} <= -${self.weekly_loss_limit:,.0f}. "
                    f"Resumes Monday."
                )

        # Priority 3: Daily loss
        elif self.daily_pnl <= -self.daily_loss_limit:
            if self.state != BreakerState.DAILY_STOP:
                self.state = BreakerState.DAILY_STOP
                logger.error(
                    f"🟡 DAILY STOP: Day P&L ${self.daily_pnl:,.0f} <= -${self.daily_loss_limit:,.0f}. "
                    f"Resumes tomorrow."
                )

        # Priority 4: Consecutive losses
        elif self.consecutive_losses >= self.consecutive_loss_limit:
            if self.state == BreakerState.NORMAL:
                self.state = BreakerState.RACE_PAUSE
                logger.warning(
                    f"⚠️ RACE PAUSE: {self.consecutive_losses} consecutive losses. "
                    f"Pausing for 1 race."
                )

    def can_trade(self) -> bool:
        self._check_reset()
        if self.state == BreakerState.FULL_STOP:
            return False
        if self.state in [BreakerState.DAILY_STOP, BreakerState.WEEKLY_STOP]:
            return False
        return True

    def can_trade_race(self) -> bool:
        return self.can_trade() and self.state != BreakerState.RACE_PAUSE

    def get_status(self) -> dict:
        self._check_reset()
        drawdown = (self.peak_bankroll - self.current_bankroll) / self.peak_bankroll
        return {
            "state": self.state.value,
            "bankroll": self.current_bankroll,
            "peak": self.peak_bankroll,
            "drawdown_pct": drawdown,
            "daily_pnl": self.daily_pnl,
            "weekly_pnl": self.weekly_pnl,
            "consecutive_losses": self.consecutive_losses,
            "can_trade": self.can_trade(),
        }

    def manual_reset(self):
        self.state = BreakerState.NORMAL
        self.consecutive_losses = 0
        self.peak_bankroll = self.current_bankroll
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        logger.info("Manual reset — all breakers cleared")
