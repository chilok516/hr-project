"""ADR-006: Harville-Stern conditional probability for quinella/quinella place.

Harville (1973):
  P(i 1st, j 2nd) = P(i) × P(j) / (1 - P(i))

Stern (1990) correction with discount factor γ:
  P(i 1st, j 2nd) = P(i) × P(j)^γ / Σ(k≠i) P(k)^γ

γ < 1 accounts for favourite-longshot bias in conditional finishing probabilities.
Empirically calibrated from HKJC data.
"""

import numpy as np
from typing import Tuple, Optional


def harville_quinella(
    prob_i: float, prob_j: float,
    all_probs: np.ndarray, idx_i: int, idx_j: int,
    gamma: float = 1.0,
) -> float:
    """P(horse i wins, horse j runs 2nd) using Harville-Stern."""
    if idx_i == idx_j:
        return 0.0

    # P(i) * P(j)^γ / sum(k≠i) P(k)^γ
    p_i = prob_i
    p_j_gamma = prob_j ** gamma

    probs_gamma = all_probs ** gamma
    denom = probs_gamma.sum() - (probs_gamma[idx_i])

    if denom <= 0:
        return 0.0

    return p_i * p_j_gamma / denom


def harville_quinella_matrix(
    probs: np.ndarray, gamma: float = 1.0,
) -> np.ndarray:
    """Compute N×N matrix where [i,j] = P(i 1st, j 2nd)."""
    n = len(probs)
    matrix = np.zeros((n, n))

    probs_gamma = probs ** gamma
    sum_gamma = probs_gamma.sum()

    for i in range(n):
        denom = sum_gamma - probs_gamma[i]
        if denom <= 0:
            continue
        for j in range(n):
            if i == j:
                continue
            matrix[i, j] = probs[i] * probs_gamma[j] / denom

    return matrix


def quinella_combo_prob(
    prob_i: float, prob_j: float,
    all_probs: np.ndarray, idx_i: int, idx_j: int,
    gamma: float = 1.0,
) -> float:
    """P({i,j} in top 2, any order) = P(i 1st,j 2nd) + P(j 1st,i 2nd)."""
    p_ij = harville_quinella(prob_i, prob_j, all_probs, idx_i, idx_j, gamma)
    p_ji = harville_quinella(prob_j, prob_i, all_probs, idx_j, idx_i, gamma)
    return p_ij + p_ji


def estimate_quinella_dividend(
    combo_prob: float,
    pool_size: Optional[float] = None,
    takeout: float = 0.25,
) -> float:
    """ADR-006: Estimate quinella dividend from combo probability + pool info.

    If pool_size is None, assume market bet share = combo_prob
    (no favourite-longshot bias adjustment — apply β correction separately).
    """
    if combo_prob <= 0:
        return float('inf')

    if pool_size is not None:
        net_pool = pool_size * (1 - takeout)
        est_bet_amount = pool_size * combo_prob
        if est_bet_amount <= 0:
            return float('inf')
        return (net_pool / est_bet_amount) * 10
    else:
        return (1 - takeout) / combo_prob * 10


def calibrate_gamma(
    df_races, gamma_range: np.ndarray = None,
) -> Tuple[float, list]:
    """Calibrate Stern γ from historical quinella outcomes.

    For each race, compute log-likelihood of actual quinella outcome
    under Harville-Stern with various γ values. Return best γ and LL curve.
    """
    if gamma_range is None:
        gamma_range = np.linspace(0.6, 1.0, 21)

    from itertools import combinations

    best_gamma = 1.0
    best_ll = -float('inf')
    ll_curve = []

    for gamma in gamma_range:
        total_ll = 0
        total_pairs = 0

        for _, race in df_races.groupby(["race_date", "venue", "race_no"]):
            n = len(race)
            if n < 3:
                continue

            probs = race["fund_prob"].values
            if probs.sum() == 0:
                continue
            probs = probs / probs.sum()

            positions = race["finish_pos"].values

            # Find actual winning combo
            winner_idx = np.argmin(positions)
            second_idx = np.argsort(positions)[1] if n > 1 else -1

            if second_idx < 0:
                continue

            # Compute log-likelihood
            p = harville_quinella(
                probs[winner_idx], probs[second_idx],
                probs, winner_idx, second_idx, gamma,
            )
            p = max(p, 1e-10)
            total_ll += np.log(p)
            total_pairs += 1

        avg_ll = total_ll / max(total_pairs, 1)
        ll_curve.append((gamma, avg_ll))

        if avg_ll > best_ll:
            best_ll = avg_ll
            best_gamma = gamma

    return best_gamma, ll_curve


def calibrate_beta(
    actual_dividends: np.ndarray,
    harville_fair_dividends: np.ndarray,
) -> float:
    """ADR-011: Calibrate pool bias β from log-log regression.
    log(actual_dividend) = β × log(harville_fair_dividend)
    β < 1 indicates favourite-longshot bias.
    """
    mask = (actual_dividends > 0) & (harville_fair_dividends > 0)
    if mask.sum() < 10:
        return 1.0

    log_actual = np.log(actual_dividends[mask])
    log_fair = np.log(harville_fair_dividends[mask])

    # Simple linear regression through origin
    beta = np.sum(log_actual * log_fair) / np.sum(log_fair ** 2)
    return max(0.5, min(1.0, beta))
