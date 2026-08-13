"""ADR-018: Model monitoring + concept drift detection.

Rolling 30-day metrics computed after each race day.
Thresholds:
  🟢 Green: Normal operation
  🟡 Yellow: 50% stake reduction
  🔴 Red: Paper trade only / trigger retrain
"""

import numpy as np
import pandas as pd
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger
from scipy.stats import spearmanr


class HealthLevel(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    CRITICAL = "critical"


@dataclass
class MonitorMetrics:
    rolling_sharpe: float = 0.0
    rolling_roi: float = 0.0
    rolling_win_rate: float = 0.0
    partial_ic: float = 0.0
    calibration_error: float = 0.0
    n_bets: int = 0
    n_days: int = 0

    overall_level: HealthLevel = HealthLevel.GREEN
    level_details: dict = field(default_factory=dict)


class ModelMonitor:
    def __init__(self, window_days: int = 30):
        self.window_days = window_days
        self.history = []

    def evaluate(
        self,
        recent_results: pd.DataFrame,
        model_probs: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> MonitorMetrics:
        """Compute rolling metrics and return health assessment."""

        metrics = MonitorMetrics()

        pnl = recent_results.get("pnl", pd.Series([0])).values
        stakes = recent_results.get("stake", pd.Series([1])).values
        n_bets = len(pnl)

        if n_bets > 0:
            # Sharpe (annualized, assuming daily returns)
            daily_returns = np.array(pnl) / np.where(stakes > 0, stakes, 1)
            if len(daily_returns) > 1 and daily_returns.std() > 0:
                metrics.rolling_sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252)

            metrics.rolling_roi = np.sum(pnl) / max(np.sum(stakes), 1)
            metrics.rolling_win_rate = np.mean(np.array(pnl) > 0)
            metrics.n_bets = n_bets

        # Partial IC: correlation between model probs and actual outcomes
        if len(model_probs) > 10 and len(actual_outcomes) > 10:
            ic, _ = spearmanr(model_probs, actual_outcomes)
            metrics.partial_ic = abs(ic) if not np.isnan(ic) else 0.0

        # Calibration error (Brier score)
        if len(model_probs) > 0 and len(actual_outcomes) > 0:
            metrics.calibration_error = np.mean((model_probs - actual_outcomes) ** 2)

        # Determine health level
        self._assess(metrics)

        return metrics

    def _assess(self, m: MonitorMetrics):
        levels = {}

        # Sharpe
        if m.rolling_sharpe > 0.3:
            levels["sharpe"] = HealthLevel.GREEN
        elif m.rolling_sharpe > 0:
            levels["sharpe"] = HealthLevel.YELLOW
        elif m.rolling_sharpe > -1.0:
            levels["sharpe"] = HealthLevel.RED
        else:
            levels["sharpe"] = HealthLevel.CRITICAL

        # ROI
        if m.rolling_roi > 0.0:
            levels["roi"] = HealthLevel.GREEN
        elif m.rolling_roi > -0.05:
            levels["roi"] = HealthLevel.YELLOW
        else:
            levels["roi"] = HealthLevel.RED

        # Partial IC
        if m.partial_ic > 0.02:
            levels["ic"] = HealthLevel.GREEN
        elif m.partial_ic > 0.01:
            levels["ic"] = HealthLevel.YELLOW
        else:
            levels["ic"] = HealthLevel.RED

        # Calibration
        if m.calibration_error < 0.15:
            levels["calibration"] = HealthLevel.GREEN
        elif m.calibration_error < 0.25:
            levels["calibration"] = HealthLevel.YELLOW
        else:
            levels["calibration"] = HealthLevel.RED

        m.level_details = {k: v.value for k, v in levels.items()}

        # Overall: worst of all metrics
        if HealthLevel.CRITICAL in levels.values():
            m.overall_level = HealthLevel.CRITICAL
        elif HealthLevel.RED in levels.values():
            m.overall_level = HealthLevel.RED
        elif HealthLevel.YELLOW in levels.values():
            m.overall_level = HealthLevel.YELLOW
        else:
            m.overall_level = HealthLevel.GREEN

    def get_action(self, metrics: MonitorMetrics) -> dict:
        """Return recommended action based on health level."""

        if metrics.overall_level == HealthLevel.CRITICAL:
            return {
                "action": "full_stop",
                "stake_multiplier": 0.0,
                "message": "CRITICAL: System paused. Manual review required. Sharpe < -1.0",
                "retrain": True,
            }

        if metrics.overall_level == HealthLevel.RED:
            action = {
                "action": "paper_only",
                "stake_multiplier": 0.0,
                "message": "RED: Paper trade only. Real money paused.",
                "retrain": False,
            }
            if metrics.partial_ic < 0.01:
                action["retrain"] = True
                action["message"] += " Model retrain triggered (low IC)."
            return action

        if metrics.overall_level == HealthLevel.YELLOW:
            return {
                "action": "reduce_stake",
                "stake_multiplier": 0.5,
                "message": "YELLOW: Reduced stakes (50%). Monitor closely.",
                "retrain": False,
            }

        return {
            "action": "normal",
            "stake_multiplier": 1.0,
            "message": "GREEN: Normal operation.",
            "retrain": False,
        }

    def log_report(self, metrics: MonitorMetrics):
        action = self.get_action(metrics)

        logger.info(f"Model Health [{metrics.overall_level.value.upper()}]: "
                     f"Sharpe={metrics.rolling_sharpe:.2f} "
                     f"ROI={metrics.rolling_roi:.1%} "
                     f"WR={metrics.rolling_win_rate:.1%} "
                     f"IC={metrics.partial_ic:.3f} "
                     f"Brier={metrics.calibration_error:.3f} "
                     f"N={metrics.n_bets}")

        for metric, level in metrics.level_details.items():
            icon = {"green": "🟢", "yellow": "🟡", "red": "🔴", "critical": "⛔"}.get(level, "?")
            logger.info(f"  {icon} {metric}: {level}")

        logger.info(f"  → Action: {action['action']} (stake ×{action['stake_multiplier']})")
        if action["retrain"]:
            logger.info("  → Retrain triggered")
