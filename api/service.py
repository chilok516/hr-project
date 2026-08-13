"""Prediction + backtest service layer for the FastAPI app."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))

from config import DATA_PROCESSED, DATA_MODELS, DATA_RAW
from src.models.train import RacePredictor
from src.combo.engine import ComboEngine
from src.scraper.race_card import runners_to_dataframe, synthetic_race_card, RaceCardScraper
from src.signals.cold_score import ColdScoreCalibrator


class PredictionService:
    def __init__(self):
        self.predictor: RacePredictor = None
        self.features_df: pd.DataFrame = None
        self.raw_df: pd.DataFrame = None
        self.bets_detail: dict = None
        self.combo_engine = ComboEngine(gamma=1.0, beta_quinella=0.855)
        self.cold_calibrator = ColdScoreCalibrator()
        self.race_card_scraper = RaceCardScraper()
        # Cache: date -> list of race card results (avoid re-scrape per request)
        self._live_cache: dict = {}

    def load(self):
        self._load_models()
        self._load_features()
        self._load_raw()
        self._load_bets()
        self._load_cold_score()

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

    def _load_raw(self):
        path = DATA_RAW / "race_results.csv"
        if path.exists():
            self.raw_df = pd.read_csv(path, low_memory=False)
            logger.info(f"Raw data loaded: {len(self.raw_df)} records")

    def _load_cold_score(self):
        if self.features_df is not None:
            try:
                self.cold_calibrator.calibrate(self.features_df)
                logger.info("Cold score calibrated")
            except Exception as e:
                logger.warning(f"Cold score calibration failed: {e}")

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

    # ---- Live ----

    LIVE_SOURCE_DATE = "2026/07/15"  # synthetic source (most recent historical race day)

    def _get_race_card(self, date_str: str, venue: str, race_no: int) -> dict:
        """Get a race card (real scrape or synthetic fallback)."""
        slash_date = date_str.replace("-", "/")

        # Try real scrape first
        try:
            card = self.race_card_scraper.get_race_card(slash_date, venue, race_no)
            if card.get("runners"):
                card["race_info"] = {
                    "race_date": slash_date, "venue": venue, "race_no": race_no,
                    "race_class": "", "distance": 0, "going": "", "course": "", "rating_band": "",
                }
                return card
        except Exception:
            pass

        # Synthetic fallback (off-season / test)
        return synthetic_race_card(self.LIVE_SOURCE_DATE, race_no, slash_date, venue=venue)

    def list_live_races(self, date_str: str) -> list:
        """List races for a live date (synthetic during off-season)."""
        slash_date = date_str.replace("-", "/")
        source = self.LIVE_SOURCE_DATE

        if self.raw_df is None:
            return []

        source_races = self.raw_df[self.raw_df["race_date"] == source]
        if source_races.empty:
            return []

        races = []
        for (venue, race_no), grp in source_races.groupby(["venue", "race_no"]):
            first = grp.iloc[0]
            races.append({
                "venue": venue,
                "race_no": int(race_no),
                "n_runners": len(grp),
                "distance": int(first.get("distance", 0)),
                "race_class": str(first.get("race_class", "")),
                "going": str(first.get("going", "")),
                "race_date": slash_date,
            })
        return sorted(races, key=lambda r: (r["venue"], r["race_no"]))

    def live_predict(self, date_str: str, venue: str, race_no: int) -> dict:
        """Predict an upcoming race (no results yet)."""
        if self.predictor is None or self.raw_df is None:
            return {"error": "service not loaded"}

        card = self._get_race_card(date_str, venue, race_no)
        runners = card.get("runners", [])
        if not runners:
            return {"error": "no runners found for this race"}

        # Race info defaults (from synthetic card or scrape)
        race_info = card.get("race_info", {}) or {}
        race_info.setdefault("race_date", date_str.replace("-", "/"))
        race_info.setdefault("venue", venue)
        race_info.setdefault("race_no", race_no)
        race_info.setdefault("race_class", "")
        race_info.setdefault("distance", 0)
        race_info.setdefault("going", "")

        result = self.compute_live_prediction(runners, race_info)
        result["race_info"] = {
            "date": race_info["race_date"].replace("/", "-"),
            "venue": race_info["venue"],
            "race_no": race_no,
            "distance": int(race_info.get("distance", 0)),
            "race_class": str(race_info.get("race_class", "")),
            "going": str(race_info.get("going", "")),
        }
        return result

    def compute_live_prediction(self, runners, race_info: dict) -> dict:
        """Full live prediction: features → models → combos → stakes."""
        from src.features.feature_engine import FeatureEngineer

        live_df = runners_to_dataframe(runners, race_info)
        combined = pd.concat([self.raw_df, live_df], ignore_index=True)

        fe = FeatureEngineer(combined)
        fdf = fe.build_all_features()

        target_date = pd.to_datetime(race_info["race_date"])
        mask = (fdf["race_date"] == target_date) & (fdf["race_no"] == race_info["race_no"])
        if "venue" in race_info and race_info["venue"]:
            mask = mask & (fdf["venue"] == race_info["venue"])
        live_feat = fdf[mask].copy()

        if live_feat.empty:
            return {"error": "feature engineering produced no rows"}

        pred = self.predictor.predict_race(live_feat)

        # Cold scores
        try:
            cold_scores = self.cold_calibrator.score(live_feat)
        except Exception:
            cold_scores = np.zeros(len(live_feat))

        horses = []
        cold_by_no = {}
        for i, (_, row) in enumerate(pred.iterrows()):
            hno = int(row.get("horse_no", 0))
            cs = float(cold_scores[i]) if i < len(cold_scores) else 0.0
            cold_by_no[hno] = cs
            horses.append({
                "horse_no": hno,
                "horse_name": str(row.get("horse_name", "")),
                "jockey": str(row.get("jockey", "")),
                "trainer": str(row.get("trainer", "")),
                "draw": int(row.get("draw", 0)),
                "weight": int(row.get("weight", 0)),
                "win_odds": float(row.get("win_odds", 0)) if pd.notna(row.get("win_odds", np.nan)) else 0.0,
                "fund_prob": float(row.get("fund_prob", 0)),
                "top2_prob": float(row.get("top2_prob", 0)),
                "market_prob": float(row.get("market_prob", 0)),
                "place_prob": float(row.get("place_prob", 0)),
                "cold_score": round(cs, 1),
            })

        # Combos
        combos = []
        try:
            combo_result = self.combo_engine.build_combos(pred, n_anchors=3)
            for c in combo_result.combos:
                avg_cold = (cold_by_no.get(c.horse_i_no, 0) + cold_by_no.get(c.horse_j_no, 0)) / 2
                mult = self.cold_calibrator.get_multiplier(avg_cold)
                stake = round(100 * mult, 2)
                combos.append({
                    "horse_i": c.horse_i,
                    "horse_j": c.horse_j,
                    "horse_i_no": c.horse_i_no,
                    "horse_j_no": c.horse_j_no,
                    "prob": round(c.quinella_prob, 4),
                    "est_dividend": round(c.est_dividend, 0),
                    "ev": round(c.ev, 3),
                    "cold_score": round(avg_cold, 1),
                    "multiplier": mult,
                    "suggested_stake": stake,
                })
        except Exception as e:
            logger.warning(f"Live combo build failed: {e}")

        total_stake = round(sum(c["suggested_stake"] for c in combos), 2)

        return {
            "horses": sorted(horses, key=lambda h: -h["fund_prob"]),
            "combos": combos,
            "suggested_total_stake": total_stake,
            "risk_caps": {"max_per_race": 500, "max_per_day": 2000},
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
