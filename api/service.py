"""Prediction + backtest service layer for the FastAPI app."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))

from config import DATA_PROCESSED, DATA_MODELS
from src.models.train import RacePredictor
from src.combo.engine import ComboEngine


class PredictionService:
    def __init__(self):
        self.predictor: RacePredictor = None
        self.features_df: pd.DataFrame = None
        self.bets_detail: dict = None
        self.combo_engine = ComboEngine(gamma=1.0, beta_quinella=0.855)

    def load(self):
        self._load_models()
        self._load_features()
        self._load_bets()

    def _load_models(self):
        self.predictor = RacePredictor()
        try:
            self.predictor.load_all()
            logger.info("4 models loaded")
        except FileNotFoundError as e:
            logger.warning(f"Models not found: {e}")

    def _load_features(self):
        path = DATA_PROCESSED / "features.csv"
        if path.exists():
            self.features_df = pd.read_csv(path, low_memory=False)
            self.features_df["race_date"] = pd.to_datetime(
                self.features_df["race_date"], errors="coerce")
            logger.info(f"Features loaded: {len(self.features_df)} records")

    def _load_bets(self):
        path = DATA_PROCESSED / "bets_detail.json"
        if path.exists():
            with open(path) as f:
                self.bets_detail = json.load(f)
            logger.info(f"Bets loaded: {len(self.bets_detail.get('bets', []))} bets")

    # ---- Prediction ----

    def list_dates(self) -> list:
        if self.features_df is None:
            return []
        dates = sorted(self.features_df["race_date"].dt.strftime("%Y-%m-%d").unique())
        return dates

    def list_races(self, date_str: str) -> list:
        if self.features_df is None:
            return []
        df = self.features_df
        mask = df["race_date"].dt.strftime("%Y-%m-%d") == date_str
        races = df[mask].groupby(["venue", "race_no"]).agg(
            n_horses=("horse_name", "count"),
            distance=("distance", "first"),
            race_class=("race_class", "first"),
            going=("going", "first"),
        ).reset_index()
        return races.to_dict(orient="records")

    def predict_race(self, date_str: str, venue: str, race_no: int) -> dict:
        if self.features_df is None or self.predictor is None:
            return {"error": "service not loaded"}

        df = self.features_df
        mask = (
            (df["race_date"].dt.strftime("%Y-%m-%d") == date_str)
            & (df["venue"] == venue)
            & (df["race_no"] == race_no)
        )
        race = df[mask].copy()
        if race.empty:
            return {"error": "race not found"}

        pred = self.predictor.predict_race(race)

        # Build horse list
        horses = []
        for _, row in pred.iterrows():
            horses.append({
                "horse_no": int(row.get("horse_no", 0)),
                "horse_name": str(row.get("horse_name", "")),
                "jockey": str(row.get("jockey", "")),
                "trainer": str(row.get("trainer", "")),
                "win_odds": float(row.get("win_odds", 0)),
                "finish_pos": int(row.get("finish_pos", 0)),
                "fund_prob": float(row.get("fund_prob", 0)),
                "top2_prob": float(row.get("top2_prob", 0)),
                "market_prob": float(row.get("market_prob", 0)),
                "place_prob": float(row.get("place_prob", 0)),
            })

        # Build quinella combos from top 3 anchors
        combos = []
        try:
            combo_result = self.combo_engine.build_combos(pred, n_anchors=3)
            for c in combo_result.combos:
                combos.append({
                    "horse_i": c.horse_i,
                    "horse_j": c.horse_j,
                    "horse_i_no": c.horse_i_no,
                    "horse_j_no": c.horse_j_no,
                    "prob": round(c.quinella_prob, 4),
                    "est_dividend": round(c.est_dividend, 0),
                    "ev": round(c.ev, 3),
                })
        except Exception as e:
            logger.warning(f"Combo build failed: {e}")

        first = race.iloc[0]
        return {
            "race_info": {
                "date": date_str,
                "venue": venue,
                "race_no": race_no,
                "distance": int(first.get("distance", 0)),
                "race_class": str(first.get("race_class", "")),
                "going": str(first.get("going", "")),
            },
            "horses": sorted(horses, key=lambda h: -h["fund_prob"]),
            "combos": combos,
        }

    # ---- Backtest ----

    def backtest_summary(self) -> dict:
        if self.bets_detail is None:
            return {"error": "no backtest data"}
        return self.bets_detail.get("summary", {})

    def backtest_bets(
        self,
        result: str = None,
        venue: str = None,
        search: str = None,
        min_div: float = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        if self.bets_detail is None:
            return {"error": "no backtest data", "bets": [], "total": 0}

        bets = self.bets_detail.get("bets", [])

        if result and result != "all":
            bets = [b for b in bets if b["result"] == result]
        if venue and venue != "all":
            bets = [b for b in bets if b["venue"] == venue]
        if search:
            bets = [b for b in bets if search.lower() in b.get("combo", "").lower()]
        if min_div and min_div > 0:
            bets = [b for b in bets if b.get("actual_div", 0) >= min_div]

        total = len(bets)
        page = bets[offset:offset + limit]
        return {"bets": page, "total": total}

    # ---- Models ----

    def feature_importance(self, model: str = "top2") -> list:
        if self.predictor is None:
            return []
        m = getattr(self.predictor, model, None)
        if m is None:
            return []
        imp = m.get_feature_importance()
        return imp.head(20).to_dict(orient="records")

    def model_info(self) -> dict:
        if self.predictor is None:
            return {}
        return {
            name: {
                "features": len(getattr(self.predictor, name).feature_names),
                "threshold": getattr(self.predictor, name).threshold,
                "loaded": getattr(self.predictor, name).model is not None,
            }
            for name in ["fundamental", "top2", "market", "place"]
        }
