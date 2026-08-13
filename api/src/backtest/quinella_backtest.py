"""Quinella walk-forward backtest using 4-model system + ComboEngine."""

import numpy as np
import pandas as pd
import lightgbm as lgb
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
from collections import defaultdict

from src.models.train import RacePredictor, HorseRaceModel
from src.combo.engine import ComboEngine, ComboBet
from src.risk.breakers import CircuitBreaker


@dataclass
class QuinellaBet:
    date: str
    venue: str
    race_no: int
    horse_i: str
    horse_j: str
    horse_i_no: int
    horse_j_no: int
    prob: float
    est_dividend: float
    ev: float
    stake: float = 100.0
    result: Optional[str] = None
    actual_dividend: Optional[float] = None
    profit: float = 0.0
    bet_type: str = "quinella"


@dataclass
class QuinellaBacktestResult:
    total_races: int = 0
    total_bets: int = 0
    total_wins: int = 0
    win_rate: float = 0.0
    total_staked: float = 0.0
    total_profit: float = 0.0
    roi: float = 0.0
    final_bankroll: float = 100_000.0
    max_drawdown_pct: float = 0.0
    bets: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)


class QuinellaBacktest:
    def __init__(self, bankroll: float = 100_000, base_stake: float = 100,
                 gamma: float = 1.0, beta: float = 0.855, ev_threshold: float = 0.0,
                 use_cold_score: bool = False):
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        self.base_stake = base_stake
        self.gamma = gamma
        self.beta = beta
        self.ev_threshold = ev_threshold
        self.use_cold_score = use_cold_score
        self.cold_calibrator = None
        self.breaker = CircuitBreaker(current_bankroll=bankroll)
        self.bets: list[QuinellaBet] = []
        self.equity = [bankroll]

    def run(
        self,
        features_df: pd.DataFrame,
        n_anchors: int = 3,
        ev_threshold: float = 0.95,
        min_train_dates: int = 5,
        bet_type: str = "quinella",
    ) -> QuinellaBacktestResult:
        preds = features_df.sort_values("race_date").copy()
        dates = sorted(preds["race_date"].unique())

        skipped_races = 0
        total_races = 0

        for i, test_date in enumerate(dates[min_train_dates:], start=min_train_dates):
            train_dates = dates[:i]
            train_df = preds[preds["race_date"].isin(train_dates)]
            test_date_df = preds[preds["race_date"] == test_date].copy()

            if len(train_df) < 100:
                continue

            # Cold score calibration on training data
            if self.use_cold_score and self.cold_calibrator is None:
                from src.signals.cold_score import ColdScoreCalibrator
                self.cold_calibrator = ColdScoreCalibrator()
                self.cold_calibrator.calibrate(train_df)

            # Train models on past data
            models = self._train_models(train_df)
            if models is None:
                continue

            # Predict on test date
            test_date_df = self._predict_race_day(models, test_date_df)

            # Run quinella for each race on this date
            for (race_no), race_group in test_date_df.groupby("race_no"):
                total_races += 1

                result = self._simulate_race(
                    race_group, models, n_anchors, ev_threshold, bet_type=bet_type,
                )
                if result["skipped"]:
                    skipped_races += 1
                    continue

                for bet_info in result["bets"]:
                    self._record_bet(bet_info)

        return self._compile_results(total_races, skipped_races)

    def _train_models(self, train_df: pd.DataFrame) -> Optional[RacePredictor]:
        """Fast training for walk-forward — skip calibration, fewer trees."""
        predictor = RacePredictor()
        try:
            # Override model params for speed
            for model in [predictor.fundamental, predictor.top2, predictor.market, predictor.place]:
                model.model_type = "lightgbm"

            # Only train fundamental + top2 (what we need for quinella)
            predictor.fundamental.model = lgb.LGBMClassifier(
                scale_pos_weight=11, n_estimators=80, num_leaves=31,
                learning_rate=0.08, verbose=-1, objective="binary",
            )
            predictor.top2.model = lgb.LGBMClassifier(
                scale_pos_weight=5, n_estimators=80, num_leaves=31,
                learning_rate=0.08, verbose=-1, objective="binary",
            )

            feats_fund = [f for f in predictor.fundamental._get_features(train_df) if f in train_df.columns]
            feats_top2 = [f for f in predictor.top2._get_features(train_df) if f in train_df.columns]

            X_fund = train_df[feats_fund].fillna(train_df[feats_fund].median()).values
            X_top2 = train_df[feats_top2].fillna(train_df[feats_top2].median()).values

            y_win = train_df["target_win"].values
            y_top2 = train_df["target_top2"].values

            predictor.fundamental.model.fit(X_fund, y_win)
            predictor.top2.model.fit(X_top2, y_top2)
            predictor.market.model = predictor.fundamental.model
            predictor.place.model = predictor.fundamental.model

            predictor.fundamental.feature_names = feats_fund
            predictor.top2.feature_names = feats_top2
            predictor.market.feature_names = feats_fund

            return predictor
        except Exception as e:
            logger.error(f"Model training failed: {e}")
            return None

    def _predict_race_day(self, models: RacePredictor, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        race_group = ["race_date", "venue", "race_no"]

        for model, col_prefix, target in [
            (models.fundamental, "fund", "target_win"),
            (models.top2, "top2", "target_top2"),
            (models.market, "market", "target_win"),
        ]:
            feats = [f for f in model.feature_names if f in result.columns]
            if not feats:
                continue
            X = result[feats].fillna(result[feats].median()).values

            # Per-race softmax
            result[f"{col_prefix}_raw"] = model.predict_raw(X)
            result[f"{col_prefix}_prob"] = result.groupby(race_group)[f"{col_prefix}_raw"].transform(
                lambda x: (lambda s: s / s.sum())(np.exp(x - x.max()))
                if x.max() > -np.inf else np.ones(len(x)) / len(x)
            )

        return result

    def _simulate_race(
        self, race_df: pd.DataFrame, models: RacePredictor,
        n_anchors: int, ev_threshold: float, bet_type: str = "quinella",
    ) -> dict:
        engine = ComboEngine(gamma=self.gamma, beta_quinella=self.beta)

        # Compute cold scores for anchor ranking
        cold_scores = None
        if self.use_cold_score and self.cold_calibrator and self.cold_calibrator.config:
            cold_scores = self.cold_calibrator.score(race_df)

        combo_result = engine.build_combos(race_df, n_anchors=n_anchors, cold_scores=cold_scores)

        if combo_result.skipped or not combo_result.combos:
            return {"skipped": True, "bets": []}

        bets = []

        for combo in combo_result.combos:
            # EV filter: skip combos below threshold
            if self.ev_threshold > 0 and combo.ev < self.ev_threshold:
                continue

            if bet_type == "placeQ":
                actual_dividend = self._get_actual_placeQ(race_df, combo.horse_i_no, combo.horse_j_no)
            else:
                actual_dividend = self._get_actual_quinella(race_df, combo.horse_i_no, combo.horse_j_no)
            is_win = actual_dividend is not None and actual_dividend > 0

            stake = self.base_stake

            # Cold score multiplier
            if self.use_cold_score and self.cold_calibrator and self.cold_calibrator.config:
                idx_i = race_df[race_df['horse_no'] == combo.horse_i_no].index
                idx_j = race_df[race_df['horse_no'] == combo.horse_j_no].index
                if len(idx_i) > 0 and len(idx_j) > 0:
                    si = self.cold_calibrator.score(race_df.loc[idx_i])[0]
                    sj = self.cold_calibrator.score(race_df.loc[idx_j])[0]
                    avg_score = (si + sj) / 2
                    multiplier = self.cold_calibrator.get_multiplier(avg_score)
                    stake = self.base_stake * multiplier

            bet = QuinellaBet(
                date=str(race_df.iloc[0].get("race_date", "")),
                venue=str(race_df.iloc[0].get("venue", "")),
                race_no=int(race_df.iloc[0].get("race_no", 0)),
                horse_i=combo.horse_i,
                horse_j=combo.horse_j,
                horse_i_no=combo.horse_i_no,
                horse_j_no=combo.horse_j_no,
                prob=combo.quinella_prob,
                est_dividend=combo.est_dividend,
                ev=combo.ev,
                stake=stake,
                result="WIN" if is_win else "LOSS",
                actual_dividend=actual_dividend,
                profit=(actual_dividend - 10) * (stake / 10) if is_win else -stake,
                bet_type=bet_type,
            )
            bets.append(bet)

        return {"skipped": False, "bets": bets}

    def _get_actual_quinella(
        self, race_df: pd.DataFrame, horse_i_no: int, horse_j_no: int,
    ) -> Optional[float]:
        positions = race_df["finish_pos"].values
        horse_nos = race_df["horse_no"].astype(int).values
        try:
            i_idx = list(horse_nos).index(horse_i_no)
            j_idx = list(horse_nos).index(horse_j_no)
        except ValueError:
            return None
        pos_i = int(positions[i_idx]); pos_j = int(positions[j_idx])
        if {pos_i, pos_j} == {1, 2}:
            if "quinella_div" in race_df.columns:
                qdiv = race_df.iloc[i_idx].get("quinella_div", 0) or race_df.iloc[j_idx].get("quinella_div", 0)
                if qdiv > 0: return float(qdiv)
            odds_i = race_df.iloc[i_idx].get("win_odds", 10)
            odds_j = race_df.iloc[j_idx].get("win_odds", 10)
            return float(odds_i * odds_j / 3)
        return None

    def _get_actual_placeQ(
        self, race_df: pd.DataFrame, horse_i_no: int, horse_j_no: int,
    ) -> Optional[float]:
        positions = race_df["finish_pos"].values
        horse_nos = race_df["horse_no"].astype(int).values
        try:
            i_idx = list(horse_nos).index(horse_i_no)
            j_idx = list(horse_nos).index(horse_j_no)
        except ValueError:
            return None
        pos_i = int(positions[i_idx]); pos_j = int(positions[j_idx])
        if pos_i <= 3 and pos_j <= 3:
            if "quinella_place_div" in race_df.columns:
                qdiv = race_df.iloc[i_idx].get("quinella_place_div", 0) or race_df.iloc[j_idx].get("quinella_place_div", 0)
                if qdiv > 0: return float(qdiv)
            odds_i = race_df.iloc[i_idx].get("win_odds", 10)
            odds_j = race_df.iloc[j_idx].get("win_odds", 10)
            return float(odds_i * odds_j / 6)
        return None

    def _record_bet(self, bet: QuinellaBet):
        self.bets.append(bet)
        self.bankroll += bet.profit
        self.equity.append(self.bankroll)

    def _compile_results(self, total_races: int, skipped: int) -> QuinellaBacktestResult:
        if not self.bets:
            return QuinellaBacktestResult()

        wins = [b for b in self.bets if b.result == "WIN"]
        total_staked = sum(b.stake for b in self.bets)
        total_profit = sum(b.profit for b in self.bets)

        peak = np.maximum.accumulate(self.equity)
        dd = (np.array(self.equity) - peak) / peak * 100

        return QuinellaBacktestResult(
            total_races=total_races,
            total_bets=len(self.bets),
            total_wins=len(wins),
            win_rate=len(wins) / len(self.bets) if self.bets else 0,
            total_staked=total_staked,
            total_profit=total_profit,
            roi=total_profit / total_staked if total_staked > 0 else 0,
            final_bankroll=self.bankroll,
            max_drawdown_pct=float(dd.min()) if len(dd) > 0 else 0,
            bets=self.bets,
            equity_curve=self.equity,
        )

    def print_report(self, result: QuinellaBacktestResult):
        print("\n" + "=" * 60)
        print("  QUINELLA BACKTEST REPORT")
        print("=" * 60)
        print(f"  Races Analyzed:       {result.total_races:>8}")
        print(f"  Combo Bets Placed:    {result.total_bets:>8}")
        print(f"  Winning Combos:       {result.total_wins:>8}")
        print(f"  Win Rate:            {result.win_rate:>8.1%}")
        print(f"  Total Staked:        ${result.total_staked:>8,.0f}")
        print(f"  Total P&L:           ${result.total_profit:>8,.0f}")
        print(f"  ROI:                 {result.roi:>8.1%}")
        print(f"  Final Bankroll:      ${result.final_bankroll:>8,.0f}")
        print(f"  Max Drawdown:        {result.max_drawdown_pct:>8.1%}")
        print("=" * 60)

        if result.bets:
            wins = [b for b in result.bets if b.result == "WIN"]
            if wins:
                avg_div = np.mean([b.actual_dividend for b in wins])
                print(f"\n  Avg Win Dividend:    ${avg_div:>8,.0f}")
                print(f"  Best Win:            {wins[0].horse_i} + {wins[0].horse_j} "
                      f"(${wins[0].actual_dividend:,.0f})")
        print()
