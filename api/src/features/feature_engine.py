import re
from datetime import timedelta
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
from loguru import logger

from config import DATA_PROCESSED, DATA_RAW


class FeatureEngineer:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.df["race_date"] = pd.to_datetime(self.df["race_date"], errors="coerce")
        self.df = self.df.sort_values(["race_date", "venue", "race_no"])

    def build_all_features(self) -> pd.DataFrame:
        self._encode_categoricals()
        self._add_horse_form()
        self._add_jockey_stats()
        self._add_trainer_stats()
        self._add_track_features()
        self._add_going_features()
        self._add_odds_features()
        self._add_weight_features()
        self._add_relative_to_field()
        self._add_combination_features()
        self._add_pace_features()
        self._add_horse_weight_features()
        self._add_incident_features()
        self._add_time_features()
        self._add_trainer_momentum()
        self._add_speed_features()
        self._add_class_change()
        self._add_barrier_stats()
        self._add_target()
        self._cleanup()
        return self.df
        return self.df

    def _encode_categoricals(self):
        for col in ["venue", "going"]:
            if col in self.df.columns:
                self.df[f"{col}_encoded"] = self.df[col].astype("category").cat.codes

    def _add_horse_form(self):
        horse_stats = []
        horse_history = defaultdict(list)

        for idx, row in self.df.iterrows():
            horse = row["horse_name"]
            hist = horse_history.get(horse, [])

            if len(hist) >= 3:
                horse_stats.append({
                    "horse_avg_pos": np.mean(hist[-5:]),
                    "horse_win_rate": sum(1 for p in hist[-10:] if p == 1) / min(len(hist), 10),
                    "horse_top3_rate": sum(1 for p in hist[-10:] if p <= 3) / min(len(hist), 10),
                    "horse_top2_rate": sum(1 for p in hist[-10:] if p <= 2) / min(len(hist), 10),
                    "horse_runs": len(hist),
                    "horse_last_pos": hist[-1],
                    "horse_last3_avg": np.mean(hist[-3:]) if len(hist) >= 3 else np.mean(hist),
                    "horse_form_trend": self._calc_trend(hist[-5:]) if len(hist) >= 3 else 0,
                })
            else:
                horse_stats.append({
                    "horse_avg_pos": 7.0, "horse_win_rate": 0.0, "horse_top3_rate": 0.0,
                    "horse_top2_rate": 0.0, "horse_runs": len(hist),
                    "horse_last_pos": 0, "horse_last3_avg": 7.0, "horse_form_trend": 0.0,
                })

            horse_history[horse].append(row["finish_pos"])

        stats_df = pd.DataFrame(horse_stats, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_jockey_stats(self):
        jockey_hist = defaultdict(list)
        stats = []
        for idx, row in self.df.iterrows():
            jockey = row.get("jockey", "")
            hist = jockey_hist.get(jockey, [])
            if len(hist) >= 10:
                stats.append({
                    "jockey_win_rate": sum(1 for p in hist[-50:] if p == 1) / min(len(hist), 50),
                    "jockey_top3_rate": sum(1 for p in hist[-50:] if p <= 3) / min(len(hist), 50),
                    "jockey_runs": len(hist),
                })
            else:
                stats.append({"jockey_win_rate": 0.1, "jockey_top3_rate": 0.3, "jockey_runs": len(hist)})
            jockey_hist[jockey].append(row["finish_pos"])

        stats_df = pd.DataFrame(stats, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_trainer_stats(self):
        trainer_hist = defaultdict(list)
        stats = []
        for idx, row in self.df.iterrows():
            trainer = row.get("trainer", "")
            hist = trainer_hist.get(trainer, [])
            if len(hist) >= 10:
                stats.append({
                    "trainer_win_rate": sum(1 for p in hist[-50:] if p == 1) / min(len(hist), 50),
                    "trainer_top3_rate": sum(1 for p in hist[-50:] if p <= 3) / min(len(hist), 50),
                    "trainer_runs": len(hist),
                })
            else:
                stats.append({"trainer_win_rate": 0.1, "trainer_top3_rate": 0.3, "trainer_runs": len(hist)})
            trainer_hist[trainer].append(row["finish_pos"])

        stats_df = pd.DataFrame(stats, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_track_features(self):
        if "distance" not in self.df.columns:
            return

        horse_dist_stats = defaultdict(lambda: defaultdict(list))
        horse_venue_stats = defaultdict(lambda: defaultdict(list))

        dist_stats, venue_stats = [], []

        for idx, row in self.df.iterrows():
            horse = row["horse_name"]
            dist = row.get("distance", 0)
            venue = row.get("venue", "")

            dist_hist = horse_dist_stats[horse].get(dist, [])
            dist_stats.append({
                "horse_dist_avg_pos": np.mean(dist_hist[-5:]) if dist_hist else 7.0,
                "horse_dist_runs": len(dist_hist),
            })

            venue_hist = horse_venue_stats[horse].get(venue, [])
            venue_stats.append({
                "horse_venue_avg_pos": np.mean(venue_hist[-5:]) if venue_hist else 7.0,
                "horse_venue_runs": len(venue_hist),
            })

            horse_dist_stats[horse][dist].append(row["finish_pos"])
            horse_venue_stats[horse][venue].append(row["finish_pos"])

        for s_df in [pd.DataFrame(dist_stats), pd.DataFrame(venue_stats)]:
            for col in s_df.columns:
                self.df[col] = s_df[col].values

    def _add_going_features(self):
        """ADR-003: Track condition preferences."""
        if "going" not in self.df.columns:
            return

        horse_going_stats = defaultdict(lambda: defaultdict(list))
        going_stats = []

        for idx, row in self.df.iterrows():
            horse = row["horse_name"]
            going = row.get("going", "GOOD")

            is_wet = going not in ["GOOD", "GOOD TO FIRM", "STANDARD"]
            hist = horse_going_stats[horse].get("dry" if not is_wet else "wet", [])
            dry_hist = horse_going_stats[horse].get("dry", [])
            wet_hist = horse_going_stats[horse].get("wet", [])

            going_stats.append({
                "horse_going_avg_pos": np.mean(hist[-5:]) if hist else 7.0,
                "horse_going_runs": len(hist),
                "horse_wet_place_rate": sum(1 for p in wet_hist[-10:] if p <= 3) / max(len(wet_hist[-10:]), 1),
            })

            horse_going_stats[horse]["dry" if not is_wet else "wet"].append(row["finish_pos"])

        stats_df = pd.DataFrame(going_stats, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_odds_features(self):
        if "win_odds" not in self.df.columns:
            return

        self.df["odds"] = self.df["win_odds"]
        self.df["odds_log"] = np.log1p(self.df["win_odds"])
        self.df["odds_inv"] = 1.0 / self.df["win_odds"].clip(lower=1.0)
        self.df["odds_rank"] = self.df.groupby(["race_date", "venue", "race_no"])["win_odds"].rank(pct=True)

    def _add_weight_features(self):
        if "weight" not in self.df.columns:
            return

        race_group = ["race_date", "venue", "race_no"]
        self.df["weight_zscore"] = self.df.groupby(race_group)["weight"].transform(
            lambda x: (x - x.mean()) / max(x.std(), 0.01)
        )
        self.df["weight_rank"] = self.df.groupby(race_group)["weight"].rank(pct=True)

    def _add_relative_to_field(self):
        """ADR-003: Opponent strength — relative-to-field features."""
        race_group = ["race_date", "venue", "race_no"]

        # Weight burden relative to field
        self.df["weight_burden"] = self.df["weight"] - self.df.groupby(race_group)["weight"].transform("mean")

        # Jockey quality relative to field
        if "jockey_win_rate" in self.df.columns:
            self.df["jockey_quality_delta"] = (
                self.df["jockey_win_rate"] -
                self.df.groupby(race_group)["jockey_win_rate"].transform("mean")
            )

        # Trainer quality relative to field
        if "trainer_win_rate" in self.df.columns:
            self.df["trainer_quality_delta"] = (
                self.df["trainer_win_rate"] -
                self.df.groupby(race_group)["trainer_win_rate"].transform("mean")
            )

        # Form rank within race
        if "horse_avg_pos" in self.df.columns:
            self.df["form_rank"] = self.df.groupby(race_group)["horse_avg_pos"].rank(pct=True)

        # Horse last_pos rank
        if "horse_last_pos" in self.df.columns:
            self.df["last_pos_rank"] = self.df.groupby(race_group)["horse_last_pos"].rank(pct=True)

        # Race-level field strength metrics
        if "rating_band" in self.df.columns:
            ratings = self.df["rating_band"].str.extract(r"(\d+)-(\d+)").astype(float)
            if not ratings.empty:
                self.df["rating_low"] = ratings[0]
                self.df["rating_high"] = ratings[1]
                self.df["field_rating_range"] = self.df.groupby(race_group)["rating_high"].transform("max") - \
                                                self.df.groupby(race_group)["rating_low"].transform("min")
                self.df["field_avg_rating"] = self.df.groupby(race_group)["rating_low"].transform("mean")

    def _add_combination_features(self):
        self.df["jt_win_rate"] = 0.1
        jt_combo = defaultdict(list)
        stats = []
        for idx, row in self.df.iterrows():
            combo = f"{row.get('jockey', '')}_{row.get('trainer', '')}"
            hist = jt_combo.get(combo, [])
            if len(hist) >= 3:
                stats.append({"jt_win_rate": sum(1 for p in hist if p == 1) / len(hist), "jt_runs": len(hist)})
            else:
                stats.append({"jt_win_rate": 0.1, "jt_runs": len(hist)})
            jt_combo[combo].append(row["finish_pos"])

        stats_df = pd.DataFrame(stats, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_pace_features(self):
        if "running_position" not in self.df.columns:
            return

        def parse_positions(pos_str):
            digits = re.findall(r"\d", str(pos_str))
            if len(digits) >= 2:
                return int(digits[0]), int(digits[1])
            if len(digits) == 1:
                return int(digits[0]), int(digits[0])
            return 0, 0

        parsed = self.df["running_position"].apply(parse_positions)
        self.df["pos_mid"] = parsed.apply(lambda x: x[0])
        self.df["pos_final_call"] = parsed.apply(lambda x: x[1])
        self.df["pos_improvement"] = self.df["pos_mid"] - self.df["pos_final_call"]

        race_group = ["race_date", "venue", "race_no"]
        self.df["pos_mid_rank"] = self.df.groupby(race_group)["pos_mid"].rank(pct=True)

    def _add_horse_weight_features(self):
        if "declared_weight" not in self.df.columns:
            return

        horse_weights = defaultdict(list)
        stats = []
        for idx, row in self.df.iterrows():
            horse = row["horse_name"]
            dw = row.get("declared_weight", 0)
            hist = horse_weights.get(horse, [])
            if len(hist) >= 2:
                prev_w = hist[-1]
                stats.append({
                    "weight_change": dw - prev_w,
                    "weight_change_pct": (dw - prev_w) / prev_w * 100 if prev_w > 0 else 0,
                })
            else:
                stats.append({"weight_change": 0, "weight_change_pct": 0})
            if dw > 0:
                horse_weights[horse].append(dw)

        stats_df = pd.DataFrame(stats, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_incident_features(self):
        if "incident_remark" not in self.df.columns:
            return

        from src.features.incident_parser import parse_incidents, get_excuse_features

        horse_excuse_history = defaultdict(list)
        excuse_stats = []

        for idx, row in self.df.iterrows():
            horse = row["horse_name"]
            remark = row.get("incident_remark", "")
            flags = parse_incidents(remark)

            hist = horse_excuse_history.get(horse, [])
            prev_excuse = hist[-1] if hist else False

            feats = get_excuse_features(flags)
            feats["prev_had_excuse"] = float(prev_excuse)
            feats["excuse_last_run"] = float(prev_excuse)

            excuse_stats.append(feats)
            horse_excuse_history[horse].append(flags.get("had_excuse", False))

        stats_df = pd.DataFrame(excuse_stats, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_time_features(self):
        """Days since last run, previous jockey, previous class for each horse."""
        horse_last_date = {}
        horse_prev_jockey = {}
        horse_prev_class = {}
        horse_prev_rating = {}

        days_since = []
        prev_jockey_list = []
        prev_class_list = []

        for idx, row in self.df.iterrows():
            horse = row["horse_name"]
            current_date = row["race_date"]
            current_jockey = row.get("jockey", "")
            current_class = row.get("race_class", "")

            # Days since last run
            last_date = horse_last_date.get(horse)
            if last_date and pd.notna(current_date) and pd.notna(last_date):
                days_since.append((current_date - last_date).days)
            else:
                days_since.append(0)

            # Previous jockey
            prev_jockey = horse_prev_jockey.get(horse, "")
            prev_jockey_list.append(prev_jockey)

            # Previous class
            prev_class = horse_prev_class.get(horse, "")
            prev_class_list.append(prev_class)

            horse_last_date[horse] = current_date
            horse_prev_jockey[horse] = current_jockey
            horse_prev_class[horse] = current_class

        self.df["days_since_last_run"] = days_since
        self.df["prev_jockey"] = prev_jockey_list
        self.df["prev_class"] = prev_class_list

    def _add_trainer_momentum(self):
        """Exponential-decay weighted trainer recent win rate.
        Weights: recent wins matter more (half-life ~14 days).
        """
        if "trainer" not in self.df.columns:
            return

        trainer_win_dates = defaultdict(list)
        momentum_list = []

        for idx, row in self.df.iterrows():
            trainer = row.get("trainer", "")
            current_date = row["race_date"]
            finish_pos = row["finish_pos"]

            if finish_pos == 1 and pd.notna(current_date):
                trainer_win_dates[trainer].append(current_date)

            # Compute exponential-decay weighted recent wins
            win_dates = trainer_win_dates.get(trainer, [])
            momentum = 0
            half_life = 14  # days

            if pd.notna(current_date):
                for win_date in win_dates:
                    days_ago = (current_date - win_date).days
                    if days_ago >= 0 and days_ago <= 60:
                        momentum += np.exp(-days_ago / half_life * np.log(2))

            momentum_list.append(momentum)

        self.df["trainer_momentum"] = momentum_list

    def _add_speed_features(self):
        """Speed rating from past races only — no current race data."""
        if "finish_time" not in self.df.columns:
            return

        def time_to_sec(t):
            if pd.isna(t) or not isinstance(t, str) or ':' not in t:
                return np.nan
            try:
                parts = t.split(':')
                return float(parts[0]) * 60 + float(parts[1])
            except (ValueError, IndexError):
                return np.nan

        self.df["finish_sec"] = self.df["finish_time"].apply(time_to_sec)

        # Rolling best finish time (in seconds, lower = faster) from PAST races only
        horse_times = defaultdict(list)
        best_time_list = []

        for idx, row in self.df.iterrows():
            horse = row["horse_name"]
            fin_sec = row.get("finish_sec", np.nan)
            hist = horse_times.get(horse, [])

            if len(hist) > 0:
                best_time_list.append(min(hist[-5:]))
            else:
                best_time_list.append(np.nan)

            if not np.isnan(fin_sec):
                horse_times[horse].append(fin_sec)

        self.df["best_finish_sec"] = best_time_list

    def _add_class_change(self):
        """Class change detection: is horse moving up or down in class?"""
        if "prev_class" not in self.df.columns or "race_class" not in self.df.columns:
            return

        def class_rank(c):
            if not isinstance(c, str):
                return 0
            if c.startswith('G') or c.startswith('Gr'):
                return 0  # Group races highest
            m = re.search(r'\d+', c)
            return int(m.group()) if m else 5

        self.df["class_curr_rank"] = self.df["race_class"].apply(class_rank)
        self.df["class_prev_rank"] = self.df["prev_class"].apply(class_rank)
        # Higher rank = lower class. Positive change = class drop (good)
        self.df["class_change"] = self.df["class_curr_rank"] - self.df["class_prev_rank"]
        self.df["class_drop"] = (self.df["class_change"] > 0).astype(int)
        self.df["class_rise"] = (self.df["class_change"] < 0).astype(int)

    def _add_barrier_stats(self):
        """Barrier/draw win rate by distance range (1000-1400 sprint, 1600+ route)."""
        if "draw" not in self.df.columns or "distance" not in self.df.columns:
            return

        self.df["dist_group"] = self.df["distance"].apply(
            lambda d: "sprint" if d <= 1400 else "route")

        # Barrier win rate per distance group (rolling)
        barrier_stats = defaultdict(lambda: defaultdict(list))
        barrier_features = []

        for idx, row in self.df.iterrows():
            draw = row.get("draw", 0)
            dist_g = row.get("dist_group", "sprint")
            pos = row["finish_pos"]

            hist = barrier_stats[dist_g].get(draw, [])
            if len(hist) >= 10:
                barrier_features.append({
                    "barrier_win_rate": sum(1 for p in hist[-50:] if p == 1) / min(len(hist), 50),
                    "barrier_top3_rate": sum(1 for p in hist[-50:] if p <= 3) / min(len(hist), 50),
                })
            else:
                barrier_features.append({"barrier_win_rate": 0.08, "barrier_top3_rate": 0.25})

            barrier_stats[dist_g][draw].append(pos)

        stats_df = pd.DataFrame(barrier_features, index=self.df.index)
        for col in stats_df.columns:
            self.df[col] = stats_df[col]

    def _add_target(self):
        self.df["target_win"] = (self.df["finish_pos"] == 1).astype(int)
        self.df["target_top2"] = (self.df["finish_pos"] <= 2).astype(int)
        self.df["target_place"] = (self.df["finish_pos"] <= 3).astype(int)

    def _calc_trend(self, positions: list) -> float:
        if len(positions) < 2:
            return 0.0
        x = np.arange(len(positions))
        y = np.array(positions)
        slope = np.polyfit(x, y, 1)[0]
        return -slope

    def _cleanup(self):
        self.df = self.df.replace([np.inf, -np.inf], np.nan)
        non_null_cols = [c for c in self.df.columns if self.df[c].notna().sum() > 100]
        self.df = self.df[non_null_cols]

    def save(self, path: Path = None):
        path = path or DATA_PROCESSED / "features.csv"
        self.df.to_csv(path, index=False)
        logger.info(f"Features saved to {path}")
