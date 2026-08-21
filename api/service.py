"""Prediction + backtest service layer for the FastAPI app."""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))

from config import DATA_PROCESSED, DATA_MODELS, DATA_RAW
from src.models.train import RacePredictor
from src.combo.engine import ComboEngine
from src.scraper.race_card import runners_to_dataframe, synthetic_race_card, RaceCardScraper, RACE_CARD_COLUMNS
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
        self.cn_names: dict = {"horses": {}, "jockeys": {}, "trainers": {}}
        # UK artifacts (models_uk / uk_features.csv / uk_race_results.csv)
        self.uk_predictor: RacePredictor = None
        self.uk_features_df: pd.DataFrame = None
        self.uk_raw_df: pd.DataFrame = None
        self.uk_bets_detail: dict = None

    def load(self):
        self._load_models()
        self._load_features()
        self._load_raw()
        self._load_bets()
        self._load_cold_score()
        self._load_cn_names()
        self._load_uk()

    def _load_cn_names(self):
        path = DATA_PROCESSED / "names_cn.json"
        if path.exists():
            try:
                with open(path) as f:
                    self.cn_names = json.load(f)
                logger.info(f"Chinese names loaded: {len(self.cn_names.get('horses', {}))} horses, "
                            f"{len(self.cn_names.get('jockeys', {}))} jockeys")
            except Exception as e:
                logger.warning(f"Failed to load Chinese names: {e}")

    def _cn_horse(self, name: str, names: dict = None) -> str:
        d = names if names is not None else self.cn_names
        return d.get("horses", {}).get(name, "")

    def _cn_jockey(self, name: str, names: dict = None) -> str:
        d = names if names is not None else self.cn_names
        return d.get("jockeys", {}).get(name, "")

    def _cn_trainer(self, name: str, names: dict = None) -> str:
        d = names if names is not None else self.cn_names
        return d.get("trainers", {}).get(name, "")

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

    def _load_uk(self):
        uk_models = DATA_MODELS.parent / "models_uk"
        if (uk_models / "top2_lightgbm.pkl").exists():
            self.uk_predictor = RacePredictor(model_dir=uk_models)
            try:
                self.uk_predictor.load_all()
                logger.info("UK models loaded")
            except Exception as e:
                logger.warning(f"UK models not loaded: {e}")

        path = DATA_PROCESSED / "uk_features.csv"
        if path.exists():
            self.uk_features_df = pd.read_csv(path, low_memory=False)
            self.uk_features_df["race_date"] = pd.to_datetime(
                self.uk_features_df["race_date"], errors="coerce")
            logger.info(f"UK features loaded: {len(self.uk_features_df)} records")

        raw_path = DATA_RAW / "uk_race_results.csv"
        if raw_path.exists():
            self.uk_raw_df = pd.read_csv(raw_path, low_memory=False)
            logger.info(f"UK raw loaded: {len(self.uk_raw_df)} records")

        bets_path = DATA_PROCESSED / "uk_bets_detail.json"
        if bets_path.exists():
            with open(bets_path) as f:
                self.uk_bets_detail = json.load(f)
            logger.info(f"UK bets loaded: {len(self.uk_bets_detail.get('bets', []))} bets")

    def _region_ctx(self, region: str) -> dict:
        if region == "uk":
            return {
                "features_df": self.uk_features_df,
                "raw_df": self.uk_raw_df,
                "predictor": self.uk_predictor,
                "cn": {"horses": {}, "jockeys": {}, "trainers": {}},
                "bets_detail": self.uk_bets_detail,
            }
        return {
            "features_df": self.features_df,
            "raw_df": self.raw_df,
            "predictor": self.predictor,
            "cn": self.cn_names,
            "bets_detail": self.bets_detail,
        }

    # ---- Prediction ----

    def list_dates(self, region: str = "hk") -> list:
        df = self._region_ctx(region)["features_df"]
        if df is None:
            return []
        dates = sorted(df["race_date"].dt.strftime("%Y-%m-%d").unique())
        return dates

    def list_races(self, date_str: str, region: str = "hk") -> list:
        df = self._region_ctx(region)["features_df"]
        if df is None:
            return []
        mask = df["race_date"].dt.strftime("%Y-%m-%d") == date_str
        races = df[mask].groupby(["venue", "race_no"]).agg(
            n_horses=("horse_name", "count"),
            distance=("distance", "first"),
            race_class=("race_class", "first"),
            going=("going", "first"),
        ).reset_index()
        return races.to_dict(orient="records")

    def predict_race(self, date_str: str, venue: str, race_no: int, region: str = "hk") -> dict:
        ctx = self._region_ctx(region)
        df = ctx["features_df"]
        predictor = ctx["predictor"]
        cn = ctx["cn"]
        if df is None or predictor is None:
            return {"error": "service not loaded"}

        mask = (
            (df["race_date"].dt.strftime("%Y-%m-%d") == date_str)
            & (df["venue"] == venue)
            & (df["race_no"] == race_no)
        )
        race = df[mask].copy()
        if race.empty:
            return {"error": "race not found"}

        pred = predictor.predict_race(race)

        # Build horse list
        horses = []
        for _, row in pred.iterrows():
            hname = str(row.get("horse_name", ""))
            jname = str(row.get("jockey", ""))
            tname = str(row.get("trainer", ""))
            horses.append({
                "horse_no": int(row.get("horse_no", 0)),
                "horse_name": hname,
                "horse_name_cn": self._cn_horse(hname, cn),
                "jockey": jname,
                "jockey_cn": self._cn_jockey(jname, cn),
                "trainer": tname,
                "trainer_cn": self._cn_trainer(tname, cn),
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
                    "horse_i_cn": self._cn_horse(c.horse_i, cn),
                    "horse_j_cn": self._cn_horse(c.horse_j, cn),
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

        cache_key = f"{date_str}:{venue}:{race_no}"
        if cache_key in self._live_cache:
            return self._live_cache[cache_key]

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
        self._live_cache[cache_key] = result
        return result

    def compute_live_prediction(self, runners, race_info: dict) -> dict:
        """Full live prediction: features → models → combos → stakes."""
        from datetime import timedelta
        from src.features.feature_engine import FeatureEngineer

        live_df = runners_to_dataframe(runners, race_info)

        # Use last 6 months of raw data for feature engineering (speed).
        # Rolling windows are short (5-50 races), so 6 months is sufficient
        # and cuts compute time ~5x on constrained containers.
        target = pd.to_datetime(race_info["race_date"])
        cutoff = target - timedelta(days=180)
        raw_dates = pd.to_datetime(self.raw_df["race_date"], errors="coerce")
        recent_raw = self.raw_df[raw_dates >= cutoff].copy()

        combined = pd.concat([recent_raw, live_df], ignore_index=True)

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
            hname = str(row.get("horse_name", ""))
            jname = str(row.get("jockey", ""))
            tname = str(row.get("trainer", ""))
            cs = float(cold_scores[i]) if i < len(cold_scores) else 0.0
            cold_by_no[hno] = cs
            horses.append({
                "horse_no": hno,
                "horse_name": hname,
                "horse_name_cn": self._cn_horse(hname),
                "jockey": jname,
                "jockey_cn": self._cn_jockey(jname),
                "trainer": tname,
                "trainer_cn": self._cn_trainer(tname),
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
                    "horse_i_cn": self._cn_horse(c.horse_i),
                    "horse_j_cn": self._cn_horse(c.horse_j),
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

    def uk_live_predict(self, meeting_code: str, race_no: int) -> dict:
        """Predict an upcoming HKJC simulcast (UK/IRE) race using the UK models."""
        from datetime import timedelta
        from src.scraper.hkjc_simulcast import get_race_cards
        from src.features.feature_engine import FeatureEngineer

        if self.uk_raw_df is None or self.uk_predictor is None:
            return {"error": "UK service not loaded"}

        cards = get_race_cards(meeting_code)
        if not cards or race_no > len(cards):
            return {"error": "race card not found"}
        card = cards[race_no - 1]
        runners = card["runners"]
        if not runners:
            return {"error": "no runners declared"}

        date_str = f"{meeting_code[:4]}-{meeting_code[4:6]}-{meeting_code[6:8]}"

        rows = []
        for i, r in enumerate(runners):
            row = {c: np.nan for c in RACE_CARD_COLUMNS}
            row.update({
                "race_date": date_str,
                "venue": card["venue_code"],
                "race_no": race_no,
                "race_class": card["group"] or card["race_name"],
                "distance": card["distance"],
                "going": "GOOD",
                "course": card["surface"],
                "rating_band": "0-0",
                "horse_name": r["horse"],
                "horse_id": "",
                "horse_no": i + 1,
                "draw": 0,
                "jockey": "",
                "trainer": r["trainer"],
                "weight": 0,
                "declared_weight": 0,
                "finish_pos": np.nan,
                "win_odds": np.nan,
            })
            rows.append(row)
        live_df = pd.DataFrame(rows, columns=RACE_CARD_COLUMNS)

        target = pd.to_datetime(date_str)
        cutoff = target - timedelta(days=180)
        raw_dates = pd.to_datetime(self.uk_raw_df["race_date"], errors="coerce")
        recent_raw = self.uk_raw_df[raw_dates >= cutoff].copy()
        combined = pd.concat([recent_raw, live_df], ignore_index=True)

        fe = FeatureEngineer(combined)
        fdf = fe.build_all_features()

        mask = (fdf["race_date"] == target) & (fdf["race_no"] == race_no)
        live_feat = fdf[mask].copy()
        if live_feat.empty:
            return {"error": "feature engineering produced no rows"}

        pred = self.uk_predictor.predict_race(live_feat)

        horses = []
        for _, row in pred.iterrows():
            hname = str(row.get("horse_name", ""))
            horses.append({
                "horse_no": int(row.get("horse_no", 0)),
                "horse_name": hname,
                "horse_name_cn": "",
                "jockey": str(row.get("jockey", "")),
                "jockey_cn": "",
                "trainer": str(row.get("trainer", "")),
                "trainer_cn": "",
                "draw": int(row.get("draw", 0)),
                "weight": int(row.get("weight", 0)),
                "win_odds": 0.0,
                "fund_prob": float(row.get("fund_prob", 0)),
                "top2_prob": float(row.get("top2_prob", 0)),
                "market_prob": float(row.get("market_prob", 0)),
                "place_prob": float(row.get("place_prob", 0)),
            })

        combos = []
        try:
            combo_result = self.combo_engine.build_combos(pred, n_anchors=3)
            for c in combo_result.combos:
                combos.append({
                    "horse_i": c.horse_i,
                    "horse_j": c.horse_j,
                    "horse_i_cn": "",
                    "horse_j_cn": "",
                    "horse_i_no": c.horse_i_no,
                    "horse_j_no": c.horse_j_no,
                    "prob": round(c.quinella_prob, 4),
                    "est_dividend": round(c.est_dividend, 0),
                    "ev": round(c.ev, 3),
                })
        except Exception as e:
            logger.warning(f"UK live combo build failed: {e}")

        return {
            "race_info": {
                "date": date_str,
                "venue": card["venue_code"],
                "race_no": race_no,
                "distance": card["distance"],
                "race_class": card["group"] or card["race_name"],
                "going": "GOOD",
            },
            "horses": sorted(horses, key=lambda h: -h["top2_prob"]),
            "combos": combos,
        }

    # ---- Horse form (past performance) ----

    @staticmethod
    def _form_trend(pos_list: list) -> str:
        if len(pos_list) < 2:
            return "flat"
        x = np.arange(len(pos_list), dtype=float)
        y = np.array(pos_list, dtype=float)
        slope = np.polyfit(x, y, 1)[0]
        t = -slope  # positive = improving (positions shrinking)
        if t > 0.3:
            return "up"
        if t < -0.3:
            return "down"
        return "flat"

    @staticmethod
    def _subset_stats(sub: pd.DataFrame) -> dict:
        n = len(sub)
        if n == 0:
            return {"runs": 0, "win_rate": 0.0, "top3_rate": 0.0, "avg_pos": None}
        pos = sub["finish_pos"].astype(float)
        return {
            "runs": n,
            "win_rate": round(float((pos == 1).mean()), 3),
            "top3_rate": round(float((pos <= 3).mean()), 3),
            "avg_pos": round(float(pos.mean()), 1),
        }

    @staticmethod
    def _is_wet(going: str) -> bool:
        return str(going) not in ("GOOD", "GOOD TO FIRM", "STANDARD")

    def horse_form(self, horse_name: str, as_of_date: str,
                   distance: int = 0, venue: str = "", going: str = "",
                   region: str = "hk") -> dict:
        ctx = self._region_ctx(region)
        raw = ctx["raw_df"]
        cn = ctx["cn"]
        if raw is None:
            return {"error": "no raw data"}

        h = raw[raw["horse_name"] == horse_name].copy()
        if h.empty:
            return {"error": "horse not found"}

        h["_dt"] = pd.to_datetime(h["race_date"], errors="coerce")
        as_of = pd.to_datetime(as_of_date, errors="coerce")
        h = h[h["_dt"] < as_of].sort_values("_dt", ascending=False)

        base = {
            "horse_name": horse_name,
            "horse_name_cn": self._cn_horse(horse_name, cn),
        }
        if h.empty:
            return {**base, "runs": 0, "form_string": "", "recent": []}

        total_runs = len(h)
        recent10 = h.head(10)
        recent6 = h.head(6)
        recent5 = h.head(5)

        # Form string (most recent first)
        form_string = "-".join(str(int(p)) for p in recent6["finish_pos"].tolist())

        # Consecutive top-3 streak
        streak = 0
        for p in h["finish_pos"].tolist():
            if p <= 3:
                streak += 1
            else:
                break

        # Form trend (ascending order for slope)
        last5_asc = recent5["finish_pos"].astype(float).tolist()[::-1]
        trend = self._form_trend(last5_asc)

        # Days since last run
        last_date = h.iloc[0]["_dt"]
        days_since = int((as_of - last_date).days) if pd.notna(last_date) and pd.notna(as_of) else None

        # Conditions
        if region == "uk":
            top_venues = h["venue"].value_counts().head(2).index.tolist()
        else:
            top_venues = ["ST", "HV"]
        venue_stats = {v: self._subset_stats(h[h["venue"] == v]) for v in top_venues}

        turf_mask = h["course"].astype(str).str.contains("TURF", na=False)
        course_stats = {
            "turf": self._subset_stats(h[turf_mask]),
            "awt": self._subset_stats(h[~turf_mask]),
        }

        wet_mask = h["going"].apply(self._is_wet)
        going_stats = {
            "good": self._subset_stats(h[~wet_mask]),
            "wet": self._subset_stats(h[wet_mask]),
        }

        dist_stats = None
        if distance and distance > 0:
            dist_stats = self._subset_stats(h[h["distance"] == distance])

        # Market
        odds = h["win_odds"].astype(float)
        odds_valid = odds[odds > 0]
        market = {
            "avg_odds": round(float(odds_valid.mean()), 1) if len(odds_valid) else None,
            "last_odds": round(float(h.iloc[0]["win_odds"]), 1)
            if pd.notna(h.iloc[0]["win_odds"]) else None,
            "min_odds": round(float(odds_valid.min()), 1) if len(odds_valid) else None,
            "max_odds": round(float(odds_valid.max()), 1) if len(odds_valid) else None,
        }

        # Recent races detail
        recent = []
        for _, r in h.head(8).iterrows():
            sectional = [s for s in str(r.get("sectional_time", "")).split()
                         if re.match(r"^\d+\.?\d*$", s)]
            recent.append({
                "date": str(r["race_date"]),
                "venue": str(r.get("venue", "")),
                "distance": int(r.get("distance", 0)),
                "race_class": str(r.get("race_class", "")),
                "going": str(r.get("going", "")),
                "draw": int(r.get("draw", 0)),
                "weight": int(r.get("weight", 0)),
                "jockey": str(r.get("jockey", "")),
                "jockey_cn": self._cn_jockey(str(r.get("jockey", "")), cn),
                "odds": float(r.get("win_odds", 0)) if pd.notna(r.get("win_odds", np.nan)) else 0.0,
                "finish_pos": int(r.get("finish_pos", 0)),
                "margin": str(r.get("margin", "")),
                "finish_time": str(r.get("finish_time", "")),
                "sectional_time": sectional,
            })

        return {
            **base,
            "runs": total_runs,
            "form_string": form_string,
            "win_rate": round(float((recent10["finish_pos"] == 1).mean()), 3),
            "top2_rate": round(float((recent10["finish_pos"] <= 2).mean()), 3),
            "top3_rate": round(float((recent10["finish_pos"] <= 3).mean()), 3),
            "avg_pos": round(float(recent5["finish_pos"].astype(float).mean()), 1),
            "last_pos": int(h.iloc[0]["finish_pos"]),
            "days_since_last": days_since,
            "form_trend": trend,
            "streak_top3": streak,
            "venue": venue_stats,
            "course": course_stats,
            "going": going_stats,
            "dist": dist_stats,
            "market": market,
            "recent": recent,
        }

    # ---- Backtest ----

    def backtest_summary(self, region: str = "hk") -> dict:
        bets_detail = self._region_ctx(region)["bets_detail"]
        if bets_detail is None:
            return {"error": "no backtest data"}
        return bets_detail.get("summary", {})

    def backtest_bets(
        self,
        result: str = None,
        venue: str = None,
        search: str = None,
        min_div: float = None,
        limit: int = 500,
        offset: int = 0,
        region: str = "hk",
    ) -> dict:
        ctx = self._region_ctx(region)
        bets_detail = ctx["bets_detail"]
        cn = ctx["cn"]
        if bets_detail is None:
            return {"error": "no backtest data", "bets": [], "total": 0}

        bets = bets_detail.get("bets", [])

        if result and result != "all":
            bets = [b for b in bets if b["result"] == result]
        if venue and venue != "all":
            bets = [b for b in bets if b["venue"] == venue]
        if search:
            s = search.lower()
            bets = [
                b for b in bets
                if s in b.get("combo", "").lower()
                or s in self._cn_horse(b.get("horse_i", ""), cn).lower()
                or s in self._cn_horse(b.get("horse_j", ""), cn).lower()
            ]
        if min_div and min_div > 0:
            bets = [b for b in bets if b.get("actual_div", 0) >= min_div]

        total = len(bets)
        page = bets[offset:offset + limit]

        # Enrich with Chinese names
        for b in page:
            b["horse_i_cn"] = self._cn_horse(b.get("horse_i", ""), cn)
            b["horse_j_cn"] = self._cn_horse(b.get("horse_j", ""), cn)

        return {"bets": page, "total": total}

    # ---- Models ----

    def feature_importance(self, model: str = "top2", region: str = "hk") -> list:
        predictor = self._region_ctx(region)["predictor"]
        if predictor is None:
            return []
        m = getattr(predictor, model, None)
        if m is None:
            return []
        imp = m.get_feature_importance()
        return imp.head(20).to_dict(orient="records")

    def model_info(self, region: str = "hk") -> dict:
        predictor = self._region_ctx(region)["predictor"]
        if predictor is None:
            return {}
        return {
            name: {
                "features": len(getattr(predictor, name).feature_names),
                "threshold": getattr(predictor, name).threshold,
                "loaded": getattr(predictor, name).model is not None,
            }
            for name in ["fundamental", "top2", "market", "place"]
        }
