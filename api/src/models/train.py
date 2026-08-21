import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, log_loss, precision_score, recall_score
import lightgbm as lgb

from config import DATA_MODELS, DATA_PROCESSED

EXCLUDE_COLS = {
    "race_date", "horse_name", "horse_id", "jockey", "trainer",
    "finish_pos", "going", "venue", "race_class", "finish_time",
    "target_win", "target_place", "target_top2", "margin",
    "sectional_time", "course", "prize", "horse_no",
    "running_position", "rating_band", "win_prob", "place_prob", "top2_prob",
    "quinella_div", "quinella_place_div", "incident_remark",
    "finish_sec",  # same-race time → leakage
    "dist_group",  # string column
    "prev_jockey", "prev_class",  # string columns
}

LGB_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.03,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.7,
    "bagging_freq": 5,
    "min_child_samples": 30,
    "reg_alpha": 0.2,
    "reg_lambda": 0.2,
    "verbose": -1,
    "n_estimators": 300,
}


def date_grouped_cv(df: pd.DataFrame, n_splits: int = 3):
    """ADR-005: Split by date so no same-date rows leak across folds."""
    dates = sorted(df["race_date"].unique())
    if len(dates) < n_splits + 1:
        n_splits = max(1, len(dates) - 1)

    fold_size = max(1, len(dates) // (n_splits + 1))

    for i in range(n_splits):
        train_end = (i + 1) * fold_size
        train_dates = dates[:train_end]
        test_dates = dates[train_end:train_end + fold_size]

        train_mask = df["race_date"].isin(train_dates)
        test_mask = df["race_date"].isin(test_dates)

        if train_mask.sum() == 0 or test_mask.sum() == 0:
            continue

        yield df[train_mask].index.values, df[test_mask].index.values


def _get_numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in EXCLUDE_COLS
            and df[c].dtype in [np.float64, np.int64, np.int32, np.float32]]


class HorseRaceModel:
    def __init__(self, name: str = "model", exclude_odds: bool = False, model_dir=None):
        self.name = name
        self.exclude_odds = exclude_odds
        self.model_dir = Path(model_dir) if model_dir else DATA_MODELS
        self.model = None
        self.calibrator = None
        self.feature_names = []
        self.threshold = 0.5

    def _extra_exclude(self) -> set:
        if self.exclude_odds:
            return {"win_odds", "odds", "odds_log", "odds_inv", "odds_rank"}
        return set()

    def _get_features(self, df: pd.DataFrame) -> list[str]:
        ex = EXCLUDE_COLS | self._extra_exclude()
        return [c for c in df.columns if c not in ex
                and df[c].dtype in [np.float64, np.int64, np.int32, np.float32]]

    def train(self, df: pd.DataFrame, target: str = "target_win", n_splits: int = 3):
        df = df.sort_values("race_date").copy()
        feature_cols = self._get_features(df)
        self.feature_names = feature_cols

        y = df[target].values
        pos_weight = (len(y) - y.sum()) / max(y.sum(), 1)
        logger.info(f"[{self.name}] Class balance: {y.sum()}/{len(y)} pos, pw={pos_weight:.1f}")

        scores = {"auc": [], "precision": [], "recall": []}

        for fold, (tr_idx, val_idx) in enumerate(date_grouped_cv(df, n_splits)):
            X_tr = df.loc[tr_idx, feature_cols].fillna(df[feature_cols].median()).values
            X_val = df.loc[val_idx, feature_cols].fillna(df[feature_cols].median()).values
            y_tr = y[tr_idx]
            y_val = y[val_idx]

            fold_model = lgb.LGBMClassifier(scale_pos_weight=pos_weight, **{
                k: v for k, v in LGB_PARAMS.items() if k != "n_estimators"
            })
            fold_model.fit(X_tr, y_tr)

            # Platt calibration (ADR-004)
            calibrator = CalibratedClassifierCV(
                estimator=lgb.LGBMClassifier(scale_pos_weight=pos_weight, **{
                    k: v for k, v in LGB_PARAMS.items() if k != "n_estimators"
                }),
                method='sigmoid', cv=3
            )

            # Need raw LightGBM for CalibratedClassifierCV to wrap
            # Train on train, calibrate on validation
            base_model = lgb.LGBMClassifier(scale_pos_weight=pos_weight, **{
                k: v for k, v in LGB_PARAMS.items() if k != "n_estimators"
            })
            base_model.fit(X_tr, y_tr)
            calibrator.fit(X_val, y_val)

            y_prob = calibrator.predict_proba(X_val)[:, 1]
            best_thresh = self._find_threshold(y_val, y_prob)
            y_pred = (y_prob >= best_thresh).astype(int)

            scores["auc"].append(roc_auc_score(y_val, y_prob))
            rec = recall_score(y_val, y_pred, zero_division=0)
            prec = precision_score(y_val, y_pred, zero_division=0)
            scores["recall"].append(rec)
            if prec > 0:
                scores["precision"].append(prec)

            logger.debug(f"[{self.name}] Fold {fold+1}: AUC={scores['auc'][-1]:.3f} "
                        f"Prec={scores['precision'][-1] if scores['precision'] else 0:.3f} "
                        f"Rec={scores['recall'][-1]:.3f}")

        logger.info(f"[{self.name}] CV AUC: {np.mean(scores['auc']):.3f} ± {np.std(scores['auc']):.3f}")
        logger.info(f"[{self.name}] CV recall: {np.mean(scores['recall']):.3f}")

        # Train final model on all data with calibration
        X_all = df[feature_cols].fillna(df[feature_cols].median()).values
        self.model = lgb.LGBMClassifier(scale_pos_weight=pos_weight, **{
            k: v for k, v in LGB_PARAMS.items() if k != "n_estimators"
        })
        self.model.fit(X_all, y)

        self.calibrator = CalibratedClassifierCV(
            estimator=lgb.LGBMClassifier(scale_pos_weight=pos_weight, **{
                k: v for k, v in LGB_PARAMS.items() if k != "n_estimators"
            }),
            method='sigmoid', cv=3
        )
        self.calibrator.fit(X_all, y)

        y_prob_all = self.calibrator.predict_proba(X_all)[:, 1]
        self.threshold = self._find_threshold(y, y_prob_all)
        logger.info(f"[{self.name}] Threshold: {self.threshold:.3f}")

        return scores

    def _find_threshold(self, y_true, y_prob, min_recall: float = 0.3) -> float:
        best_f1 = 0
        best_t = 0.15
        for t in np.linspace(0.05, 0.5, 46):
            y_pred = (y_prob >= t).astype(int)
            prec = precision_score(y_true, y_pred, zero_division=0)
            rec = recall_score(y_true, y_pred, zero_division=0)
            if prec > 0 and rec > 0 and rec >= min_recall:
                f1 = 2 * prec * rec / (prec + rec)
                if f1 > best_f1:
                    best_f1 = f1
                    best_t = t
        return best_t

    def predict(self, X) -> np.ndarray:
        return self.calibrator.predict_proba(X)[:, 1] if self.calibrator else self.model.predict_proba(X)[:, 1]

    def predict_raw(self, X) -> np.ndarray:
        return self.model.predict(X, raw_score=True) if self.model else np.zeros(len(X))

    def get_feature_importance(self) -> pd.DataFrame:
        if not self.model or not self.feature_names:
            return pd.DataFrame()
        imp = self.model.feature_importances_
        df = pd.DataFrame({"feature": self.feature_names, "importance": imp})
        return df.sort_values("importance", ascending=False)

    def save(self):
        path = self.model_dir / f"{self.name}_lightgbm.pkl"
        joblib.dump({
            "model": self.model,
            "calibrator": self.calibrator,
            "features": self.feature_names,
            "threshold": self.threshold,
            "exclude_odds": self.exclude_odds,
        }, path)
        logger.info(f"[{self.name}] Saved to {path}")

    def load(self):
        path = self.model_dir / f"{self.name}_lightgbm.pkl"
        data = joblib.load(path)
        self.model = data["model"]
        self.calibrator = data.get("calibrator")
        self.feature_names = data["features"]
        self.threshold = data.get("threshold", 0.15)
        self.exclude_odds = data.get("exclude_odds", False)
        logger.info(f"[{self.name}] Loaded (thresh={self.threshold:.3f})")


class RacePredictor:
    """ADR-002: Three-model system — fundamental, top2, market."""

    def __init__(self, model_dir=None):
        self.fundamental = HorseRaceModel("fundamental", exclude_odds=True, model_dir=model_dir)
        self.top2 = HorseRaceModel("top2", exclude_odds=True, model_dir=model_dir)
        self.market = HorseRaceModel("market", exclude_odds=False, model_dir=model_dir)
        self.place = HorseRaceModel("place", exclude_odds=False, model_dir=model_dir)

    def train_all(self, df: pd.DataFrame):
        logger.info("=== Fundamental Model (no odds) ===")
        self.fundamental.train(df, "target_win")

        logger.info("=== Top2 Model (no odds, target=top2) ===")
        self.top2.train(df, "target_top2")

        logger.info("=== Market Model (with odds) ===")
        self.market.train(df, "target_win")

        logger.info("=== Place Model ===")
        self.place.train(df, "target_place")

    def predict_race(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict all probs + per-race softmax (ADR-002)."""
        result = df.copy()
        race_group = ["race_date", "venue", "race_no"]

        for model, col_prefix in [
            (self.fundamental, "fund"),
            (self.top2, "top2"),
            (self.market, "market"),
            (self.place, "place"),
        ]:
            feats = [f for f in model.feature_names if f in result.columns]
            if not feats:
                continue

            X = result[feats].fillna(result[feats].median()).values

            # Per-race softmax normalization using raw logits
            result[f"{col_prefix}_raw"] = model.predict_raw(X)
            result[f"{col_prefix}_prob"] = result.groupby(race_group)[f"{col_prefix}_raw"].transform(
                lambda x: np.exp(x - x.max()) / np.exp(x - x.max()).sum()
                if x.max() > -np.inf else np.ones(len(x)) / len(x)
            )

        result = result.sort_values("fund_prob", ascending=False)
        return result

    def save_all(self):
        for m in [self.fundamental, self.top2, self.market, self.place]:
            m.save()

    def load_all(self):
        for m in [self.fundamental, self.top2, self.market, self.place]:
            m.load()
