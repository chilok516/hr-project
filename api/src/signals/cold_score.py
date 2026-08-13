"""ADR-012: 9 binary cold score signals + LogReg calibration.

Target: horse wins AND SP >= 8 (genuine longshot).
Weights calibrated via logistic regression, buckets by percentile.
"""

import numpy as np
import pandas as pd
import re
from dataclasses import dataclass
from typing import Optional, Dict, List
from loguru import logger
from sklearn.linear_model import LogisticRegression


SIGNAL_NAMES = [
    "weight_advantage",
    "jockey_upgrade",
    "trainer_in_form",
    "fresh_horse",
]


@dataclass
class ColdScoreConfig:
    weights: Dict[str, float]
    bucket_thresholds: List[float]  # [50th, 80th, 95th] percentile
    bucket_multipliers: List[float]  # [1.0, 1.5, 2.0, 3.0] for [normal, value, strong, max]


class ColdScoreCalibrator:
    def __init__(self):
        self.config: Optional[ColdScoreConfig] = None
        self.model: Optional[LogisticRegression] = None
        self.signal_cols: List[str] = []

    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute 9 binary signals from feature dataframe."""
        result = df.copy()

        # Signal 1: Class drop (last race was higher class)
        result["class_drop"] = 0
        if "prev_class" in result.columns and "race_class" in result.columns:
            # Extract numeric class: 'Class4' -> 4, 'G1' -> 0
            def class_num(c):
                if isinstance(c, str):
                    if c.startswith('G'): return 0
                    m = re.search(r'\d+', c)
                    return int(m.group()) if m else 5
                return 5

            result["_cls_curr"] = result["race_class"].apply(class_num)
            result["_cls_prev"] = result["prev_class"].apply(class_num)
            # Lower number = higher class. Class drop = prev class higher (smaller number) than current
            result["class_drop"] = (result["_cls_prev"] < result["_cls_curr"]).astype(int)

        # Signal 2: Distance specialist
        result["dist_specialist"] = 0
        if "horse_dist_avg_pos" in result.columns and "horse_avg_pos" in result.columns:
            # This distance performs better than overall average
            result["dist_specialist"] = (
                (result["horse_dist_avg_pos"] < result["horse_avg_pos"] - 1.5) &
                (result["horse_dist_runs"] >= 2)
            ).astype(int)

        # Signal 3: Track switch (venue preference)
        result["track_switch"] = 0
        if "horse_venue_avg_pos" in result.columns and "horse_avg_pos" in result.columns:
            result["track_switch"] = (
                (result["horse_venue_avg_pos"] < result["horse_avg_pos"] - 1.5) &
                (result["horse_venue_runs"] >= 2)
            ).astype(int)

        # Signal 4: Weight advantage (< field avg - 5)
        result["weight_advantage"] = 0
        if "weight_burden" in result.columns:
            result["weight_advantage"] = (result["weight_burden"] < -5).astype(int)

        # Signal 5: Jockey upgrade
        result["jockey_upgrade"] = 0
        if "jockey_win_rate" in result.columns and "prev_jockey" in result.columns:
            # Current jockey has >10% win rate AND different from previous jockey
            result["jockey_upgrade"] = (
                (result["jockey_win_rate"] > 0.10) &
                (result["prev_jockey"] != "") &
                (result["prev_jockey"] != result["jockey"])
            ).astype(int)

        # Signal 6: Trainer in form (exponential-decay weighted momentum)
        result["trainer_in_form"] = 0
        if "trainer_momentum" in result.columns:
            # Momentum > 2.0 means multiple recent wins (not just one)
            result["trainer_in_form"] = (result["trainer_momentum"] > 2.0).astype(int)

        # Signal 7: Fresh horse (>45 days since last run)
        result["fresh_horse"] = 0
        if "days_since_last_run" in result.columns:
            result["fresh_horse"] = (
                (result["days_since_last_run"] > 45) |
                (result["days_since_last_run"] == 0)  # first run ever
            ).astype(int)

        # Signal 8: Gear change
        result["gear_change"] = 0
        # NOTE: needs gear_change feature from scraper (not yet implemented)
        # Always 0 for now

        # Signal 9: Excuse last run
        result["excuse_last_run"] = 0
        if "prev_had_excuse" in result.columns:
            result["excuse_last_run"] = result["prev_had_excuse"]

        self.signal_cols = [c for c in SIGNAL_NAMES if c in result.columns]
        return result

    def calibrate(self, df: pd.DataFrame) -> ColdScoreConfig:
        """Calibrate weights using LogReg on longshot wins."""
        df = self.compute_signals(df)

        if len(self.signal_cols) < 3:
            logger.warning("Too few cold signals available, using default weights")
            self.config = ColdScoreConfig(
                weights={s: 1.0 for s in self.signal_cols},
                bucket_thresholds=[50, 80, 95],
                bucket_multipliers=[1.0, 1.5, 2.0, 3.0],
            )
            return self.config

        # Target: horse won AND odds >= 8
        if "target_win" not in df.columns or "win_odds" not in df.columns:
            logger.warning("No target or odds column for calibration")
            return self._default_config()

        y = ((df["target_win"] == 1) & (df["win_odds"] >= 8)).astype(int)
        n_pos = y.sum()

        if n_pos < 20:
            logger.warning(f"Only {n_pos} longshot wins — insufficient for calibration")
            return self._default_config()

        X = df[self.signal_cols].fillna(0).values

        self.model = LogisticRegression(penalty=None, max_iter=1000)
        self.model.fit(X, y)

        raw_weights = dict(zip(self.signal_cols, self.model.coef_[0]))
        max_abs = max(abs(w) for w in raw_weights.values()) or 1.0
        weights = {k: v / max_abs * 10 for k, v in raw_weights.items()}

        # Compute cold scores and percentile thresholds
        cold_scores = np.array([
            sum(weights[s] * df[s].fillna(0).values[i] for s in self.signal_cols)
            for i in range(len(df))
        ])
        cold_scores = np.clip(cold_scores, 0, 10)

        thresholds = [
            np.percentile(cold_scores, 50),
            np.percentile(cold_scores, 80),
            np.percentile(cold_scores, 95),
        ]

        self.config = ColdScoreConfig(
            weights=weights,
            bucket_thresholds=thresholds,
            bucket_multipliers=[1.0, 1.5, 2.0, 3.0],
        )

        logger.info(f"Cold score calibrated: weights={weights}")
        logger.info(f"Bucket thresholds: {thresholds}")
        return self.config

    def _default_config(self) -> ColdScoreConfig:
        return ColdScoreConfig(
            weights={s: 1.0 for s in self.signal_cols},
            bucket_thresholds=[50, 80, 95],
            bucket_multipliers=[1.0, 1.5, 2.0, 3.0],
        )

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """Compute cold score 0-10 for each row."""
        if not self.config:
            self.calibrate(df)

        df = self.compute_signals(df)
        scores = np.zeros(len(df))
        for s in self.signal_cols:
            if s in self.config.weights and s in df.columns:
                scores += self.config.weights[s] * df[s].fillna(0).values

        return np.clip(scores, 0, 10)

    def get_multiplier(self, cold_score: float) -> float:
        """Get stake multiplier based on cold score bucket."""
        if not self.config:
            return 1.0
        for i, threshold in enumerate(self.config.bucket_thresholds):
            if cold_score < threshold:
                return self.config.bucket_multipliers[i]
        return self.config.bucket_multipliers[-1]
