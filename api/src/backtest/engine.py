import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

from config import BET_SIZE, STARTING_BANKROLL, MAX_DAILY_LOSS, MAX_WEEKLY_LOSS, MAX_BETS_PER_DAY


@dataclass
class Bet:
    date: str
    venue: str
    race_no: int
    horse_name: str
    bet_type: str  # "WIN" or "PLACE"
    stake: float
    odds: float
    win_prob: float
    result: Optional[str] = None
    profit: float = 0.0


@dataclass
class BacktestResult:
    total_bets: int = 0
    total_wins: int = 0
    win_rate: float = 0.0
    total_staked: float = 0.0
    total_return: float = 0.0
    roi: float = 0.0
    final_bankroll: float = STARTING_BANKROLL
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    daily_pnl: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    bets: list = field(default_factory=list)


class BacktestEngine:
    def __init__(self, bankroll: float = STARTING_BANKROLL):
        self.initial_bankroll = bankroll
        self.bankroll = bankroll
        self.bets: list[Bet] = []
        self.equity_curve = [bankroll]
        self.daily_pnl: dict[str, float] = {}
        self.weekly_pnl: dict[str, float] = {}

    def walk_forward(
        self,
        predictions: pd.DataFrame,
        model_class,
        feature_cols: list[str],
        bet_strategy: str = "kelly_fraction",
        max_bets_per_race: int = 3,
        min_train_dates: int = 5,
        exclude_odds: bool = True,
    ) -> BacktestResult:
        self.bankroll = self.initial_bankroll
        self.bets = []
        self.equity_curve = [self.initial_bankroll]
        self.daily_pnl = {}

        preds = predictions.sort_values("race_date").copy()
        dates = sorted(preds["race_date"].unique())

        for i, test_date in enumerate(dates[min_train_dates:], start=min_train_dates):
            train_dates = dates[:i]
            test_mask = preds["race_date"] == test_date

            train_df = preds[preds["race_date"].isin(train_dates)]
            test_df = preds[test_mask].copy()

            if len(train_df) < 50:
                continue

            feats = [f for f in feature_cols if f in train_df.columns and f in test_df.columns]
            if not feats:
                continue

            X_train = train_df[feats].fillna(train_df[feats].median()).values
            y_train = train_df["target_win"].values if "target_win" in train_df.columns else np.zeros(len(train_df))

            pos_weight = (len(y_train) - y_train.sum()) / max(y_train.sum(), 1)

            model = model_class(exclude_odds=exclude_odds)
            model.feature_names = feats
            import lightgbm as lgb
            model.model = lgb.LGBMClassifier(scale_pos_weight=pos_weight, **{
                "objective": "binary", "metric": "auc", "boosting_type": "gbdt",
                "num_leaves": 31, "learning_rate": 0.03, "feature_fraction": 0.7,
                "bagging_fraction": 0.7, "bagging_freq": 5, "min_child_samples": 30,
                "reg_alpha": 0.2, "reg_lambda": 0.2, "verbose": -1, "n_estimators": 200,
            })
            model.model.fit(X_train, y_train)

            X_test = test_df[feats].fillna(test_df[feats].median()).values
            test_df["win_prob"] = model.model.predict_proba(X_test)[:, 1]

            self._run_date(test_df, test_date, bet_strategy, max_bets_per_race)

        return self._compile_results()

    def _run_date(self, race_date_df, date, strategy, max_per_race):
        for (venue, race_no), race_group in race_date_df.groupby(["venue", "race_no"]):
            race_group = race_group.sort_values("win_prob", ascending=False)

            bets_today = sum(1 for b in self.bets if b.date == str(date))
            if bets_today >= MAX_BETS_PER_DAY:
                continue

            today_pnl = sum(b.profit for b in self.bets if b.date == str(date))
            if today_pnl <= -MAX_DAILY_LOSS:
                return

            for _, row in race_group.head(max_per_race).iterrows():
                prob = row.get("win_prob", 0)
                odds = row.get("odds", row.get("win_odds", 0))

                if prob < 0.10 or odds <= 1.0:
                    continue

                stake = self._calculate_stake(prob, odds, strategy)
                if stake <= 0:
                    continue

                bet = Bet(
                    date=str(date),
                    venue=str(row.get("venue", "")),
                    race_no=int(race_no),
                    horse_name=str(row.get("horse_name", "")),
                    bet_type="WIN",
                    stake=round(stake, 2),
                    odds=float(odds),
                    win_prob=float(prob),
                )

                finish_pos = row.get("finish_pos", 99)
                if finish_pos == 1:
                    bet.result = "WIN"
                    bet.profit = round(stake * (odds - 1), 2)
                else:
                    bet.result = "LOSS"
                    bet.profit = -stake

                self.bankroll += bet.profit
                self.bets.append(bet)
                self.equity_curve.append(self.bankroll)

                date_key = str(date)
                self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0) + bet.profit

    def run(
        self,
        predictions: pd.DataFrame,
        bet_strategy: str = "kelly_fraction",
        max_bets_per_race: int = 3,
        min_prob: float = 0.10,
    ) -> BacktestResult:
        """
        predictions DataFrame must have columns:
        - race_date, venue, race_no, horse_name
        - win_prob (probability of winning)
        - odds (starting odds)
        - finish_pos (actual finish position)
        """
        preds = predictions.sort_values(["race_date", "venue", "race_no"]).copy()

        for (date, venue, race_no), race_group in preds.groupby(["race_date", "venue", "race_no"]):
            race_group = race_group.sort_values("win_prob", ascending=False)

            bets_today = sum(1 for b in self.bets if b.date == str(date))
            if bets_today >= MAX_BETS_PER_DAY:
                continue

            # Check daily loss limit
            today_pnl = sum(b.profit for b in self.bets if b.date == str(date))
            if today_pnl <= -MAX_DAILY_LOSS:
                continue

            # Check weekly loss limit
            week_start = pd.Timestamp(date) - pd.Timedelta(days=pd.Timestamp(date).dayofweek)
            week_key = str(week_start.date())
            week_pnl = sum(
                b.profit for b in self.bets
                if pd.Timestamp(b.date) >= week_start
            )
            if week_pnl <= -MAX_WEEKLY_LOSS:
                continue

            for _, row in race_group.head(max_bets_per_race).iterrows():
                prob = row.get("win_prob", 0)
                odds = row.get("odds", row.get("win_odds", 0))

                if prob < min_prob or odds <= 0:
                    continue

                stake = self._calculate_stake(prob, odds, bet_strategy)
                if stake <= 0:
                    continue

                bet = Bet(
                    date=str(date),
                    venue=str(row.get("venue", "")),
                    race_no=int(race_no),
                    horse_name=str(row.get("horse_name", "")),
                    bet_type="WIN",
                    stake=round(stake, 2),
                    odds=float(odds),
                    win_prob=float(prob),
                )

                finish_pos = row.get("finish_pos", 99)
                if finish_pos == 1:
                    bet.result = "WIN"
                    bet.profit = round(stake * (odds - 1), 2)
                else:
                    bet.result = "LOSS"
                    bet.profit = -stake

                self.bankroll += bet.profit
                self.bets.append(bet)
                self.equity_curve.append(self.bankroll)

                date_key = str(date)
                self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0) + bet.profit

        return self._compile_results()

    def _calculate_stake(self, prob: float, odds: float, strategy: str) -> float:
        if strategy == "kelly_fraction":
            # Fractional Kelly: bet 25% of full Kelly
            b = odds - 1  # net odds
            p = prob
            q = 1 - p
            kelly = (b * p - q) / b if b > 0 else 0
            kelly = max(0, kelly)
            stake = self.bankroll * kelly * 0.25  # quarter-Kelly
            return min(stake, self.bankroll * 0.01)  # max 1% per bet

        elif strategy == "flat":
            return BET_SIZE

        elif strategy == "proportional":
            # Bet proportional to edge
            edge = prob - (1.0 / odds)
            stake = BET_SIZE * max(0.5, edge * 3)
            return min(stake, self.bankroll * 0.01)

        elif strategy == "expected_value":
            ev = prob * (odds - 1) - (1 - prob)
            if ev <= 0.05:
                return 0
            stake = BET_SIZE * (1 + ev)
            return min(stake, self.bankroll * 0.01)

        return BET_SIZE

    def _compile_results(self) -> BacktestResult:
        wins = [b for b in self.bets if b.result == "WIN"]
        total_staked = sum(b.stake for b in self.bets)
        total_return = sum(b.profit + b.stake for b in self.bets if b.result == "WIN")

        # Drawdown calculation
        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdowns = (peak - equity) / peak
        max_dd = drawdowns.max() if len(drawdowns) > 0 else 0

        # Sharpe ratio (daily)
        if len(self.daily_pnl) > 1:
            daily_returns = np.array(list(self.daily_pnl.values())) / self.initial_bankroll
            sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0
        else:
            sharpe = 0

        # Profit factor
        gross_profit = sum(b.profit for b in wins)
        gross_loss = abs(sum(b.profit for b in self.bets if b.result != "WIN"))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        return BacktestResult(
            total_bets=len(self.bets),
            total_wins=len(wins),
            win_rate=len(wins) / len(self.bets) if self.bets else 0,
            total_staked=total_staked,
            total_return=total_return,
            roi=(self.bankroll - self.initial_bankroll) / self.initial_bankroll,
            final_bankroll=self.bankroll,
            max_drawdown=max_dd * self.initial_bankroll,
            max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            daily_pnl=list(self.daily_pnl.values()),
            equity_curve=self.equity_curve,
            bets=self.bets,
        )

    def print_report(self, result: BacktestResult):
        print("\n" + "=" * 60)
        print("  HORSE RACING BACKTEST REPORT")
        print("=" * 60)
        print(f"  Total Bets:          {result.total_bets:>8}")
        print(f"  Wins:                {result.total_wins:>8}")
        print(f"  Win Rate:            {result.win_rate:>8.1%}")
        print(f"  Total Staked:        ${result.total_staked:>8,.2f}")
        print(f"  Total Return:        ${result.total_return:>8,.2f}")
        print(f"  ROI:                 {result.roi:>8.1%}")
        print(f"  Final Bankroll:      ${result.final_bankroll:>8,.2f}")
        print(f"  Max Drawdown:        ${result.max_drawdown:>8,.2f} ({result.max_drawdown_pct:.1%})")
        print(f"  Sharpe Ratio:        {result.sharpe_ratio:>8.2f}")
        print(f"  Profit Factor:       {result.profit_factor:>8.2f}")
        print("=" * 60)

        if result.daily_pnl:
            print(f"\n  Daily P&L Stats:")
            pnl = np.array(result.daily_pnl)
            print(f"    Best Day:          ${pnl.max():>8,.2f}")
            print(f"    Worst Day:         ${pnl.min():>8,.2f}")
            print(f"    Avg Day:           ${pnl.mean():>8,.2f}")
            print(f"    Profitable Days:   {(pnl > 0).sum()} / {len(pnl)}")
        print()
