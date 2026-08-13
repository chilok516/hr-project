"""ADR-007/008/009: Quinella combo construction + EV filtering + anchor sweep."""

import numpy as np
import pandas as pd
from itertools import combinations
from typing import Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

from src.combo.harville import (
    quinella_combo_prob, estimate_quinella_dividend, calibrate_gamma, calibrate_beta,
)


@dataclass
class ComboBet:
    horse_i: str
    horse_j: str
    horse_i_no: int
    horse_j_no: int
    quinella_prob: float
    est_dividend: float
    ev: float
    bet_type: str  # "quinella" or "placeQ"


@dataclass
class RaceComboResult:
    race_date: str
    venue: str
    race_no: int
    n_horses: int
    n_anchors: int
    combos: list = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class ComboEngine:
    def __init__(
        self,
        gamma: float = 1.0,
        beta_quinella: float = 1.0,
        beta_placeQ: float = 1.0,
        ev_threshold: float = 0.95,
        min_combos: int = 2,
        takeout_quinella: float = 0.25,
        takeout_placeQ: float = 0.25,
    ):
        self.gamma = gamma
        self.beta_quinella = beta_quinella
        self.beta_placeQ = beta_placeQ
        self.ev_threshold = ev_threshold
        self.min_combos = min_combos
        self.takeout_quinella = takeout_quinella
        self.takeout_placeQ = takeout_placeQ

    def calibrate(self, features_df: pd.DataFrame):
        """Calibrate γ and β from historical data."""
        logger.info("Calibrating Stern γ...")
        self.gamma, _ = calibrate_gamma(features_df)
        logger.info(f"Optimal γ = {self.gamma:.3f}")

    def get_optimal_anchors(
        self, race_df: pd.DataFrame, max_anchors: int = 6,
        cold_scores: np.ndarray = None,
    ) -> pd.DataFrame:
        """ADR-007: Rank horses by EV contribution for quinella anchoring.

        Score = top2_prob × log(1 + win_odds) × (1 + cold_score/10)
        """
        df = race_df.copy()
        n = len(df)

        if "top2_prob" not in df.columns:
            df["top2_prob"] = df.get("fund_prob", 1.0 / n)

        if "win_odds" in df.columns:
            df["ev_score"] = df["top2_prob"] * np.log1p(df["win_odds"])
        else:
            df["ev_score"] = df["top2_prob"]

        # Cold score boost
        if cold_scores is not None and len(cold_scores) == len(df):
            df["ev_score"] = df["ev_score"] * (1 + np.clip(cold_scores, 0, 10) / 10)

        return df.sort_values("ev_score", ascending=False)

    def build_combos(
        self,
        race_df: pd.DataFrame,
        n_anchors: int = 3,
        prob_col: str = "top2_prob",
        cold_scores: np.ndarray = None,
    ) -> RaceComboResult:
        """Get top N anchors, generate C(N,2) combos, filter by EV."""

        first = race_df.iloc[0]
        result = RaceComboResult(
            race_date=str(first.get("race_date", "")),
            venue=str(first.get("venue", "")),
            race_no=int(first.get("race_no", 0)),
            n_horses=len(race_df),
            n_anchors=n_anchors,
        )

        if prob_col not in race_df.columns:
            result.skipped = True
            result.skip_reason = f"no_{prob_col}"
            return result

        df = race_df.copy()
        n = len(df)

        # Rank by EV score and select top N
        ranked = self.get_optimal_anchors(df, cold_scores=cold_scores)
        anchors = ranked.head(min(n_anchors, n))
        # Convert original df indices to positional indices (0..n-1)
        pos_map = {orig_idx: pos for pos, orig_idx in enumerate(df.index)}
        anchor_positions = [pos_map[idx] for idx in anchors.index]

        if len(anchor_positions) < 2:
            result.skipped = True
            result.skip_reason = "too_few_anchors"
            return result

        probs = df[prob_col].values
        if probs.sum() > 0:
            probs = probs / probs.sum()
        else:
            probs = np.ones(n) / n

        # Generate all C(N,2) combinations
        for pos_i, pos_j in combinations(anchor_positions, 2):
            p = quinella_combo_prob(
                probs[pos_i], probs[pos_j], probs, pos_i, pos_j, self.gamma,
            )
            est_div = estimate_quinella_dividend(p, takeout=self.takeout_quinella)

            # Apply β adjustment for pool bias
            if self.beta_quinella < 1.0:
                est_div = est_div ** self.beta_quinella

            ev = p * (est_div / 10)

            row_i, row_j = df.iloc[pos_i], df.iloc[pos_j]

            result.combos.append(ComboBet(
                horse_i=str(row_i.get("horse_name", "")),
                horse_j=str(row_j.get("horse_name", "")),
                horse_i_no=int(row_i.get("horse_no", 0)),
                horse_j_no=int(row_j.get("horse_no", 0)),
                quinella_prob=float(p),
                est_dividend=float(est_div),
                ev=float(ev),
                bet_type="quinella",
            ))

        if len(result.combos) < self.min_combos:
            result.skipped = True
            result.skip_reason = f"too_few_combos_after_filter ({len(result.combos)})"

        return result

    def sweep_anchors(
        self,
        race_df: pd.DataFrame,
        anchor_range: range = None,
    ) -> pd.DataFrame:
        """Q3-1: Sweep anchor counts to find optimal N per field size."""
        if anchor_range is None:
            n = len(race_df)
            anchor_range = range(2, min(7, n))

        results = []
        for n_anchors in anchor_range:
            combo_result = self.build_combos(race_df, n_anchors=n_anchors)
            if combo_result.skipped or not combo_result.combos:
                results.append({
                    "n_anchors": n_anchors,
                    "n_combos": 0,
                    "avg_ev": 0,
                    "skipped": True,
                })
                continue

            avg_ev = np.mean([c.ev for c in combo_result.combos])
            results.append({
                "n_anchors": n_anchors,
                "n_combos": len(combo_result.combos),
                "avg_ev": avg_ev,
                "skipped": False,
            })

        return pd.DataFrame(results)

    def estimate_all_combos_ev(
        self,
        race_df: pd.DataFrame,
        prob_col: str = "top2_prob",
    ) -> pd.DataFrame:
        """Compute EV for ALL C(N,2) combos (not just anchors) — for analysis."""
        df = race_df.copy()
        n = len(df)

        probs = df[prob_col].values
        if probs.sum() > 0:
            probs = probs / probs.sum()

        rows = []
        for idx_i, idx_j in combinations(range(n), 2):
            p = quinella_combo_prob(
                probs[idx_i], probs[idx_j], probs, idx_i, idx_j, self.gamma
            )
            est_div = estimate_quinella_dividend(p, takeout=self.takeout_quinella)
            if self.beta_quinella < 1.0:
                est_div = est_div ** self.beta_quinella
            ev = p * (est_div / 10)

            rows.append({
                "idx_i": idx_i, "idx_j": idx_j,
                "horse_i": df.iloc[idx_i].get("horse_name", ""),
                "horse_j": df.iloc[idx_j].get("horse_name", ""),
                "prob": p, "est_dividend": est_div, "ev": ev,
            })

        return pd.DataFrame(rows)
