// Client-side API client — fetches Next.js BFF routes (which proxy to FastAPI).

export interface RaceInfo {
  date: string;
  venue: string;
  race_no: number;
  distance: number;
  race_class: string;
  going: string;
}

export interface Horse {
  horse_no: number;
  horse_name: string;
  horse_name_cn: string;
  jockey: string;
  jockey_cn: string;
  trainer: string;
  trainer_cn: string;
  win_odds: number;
  finish_pos: number;
  fund_prob: number;
  top2_prob: number;
  market_prob: number;
  place_prob: number;
}

export interface Combo {
  horse_i: string;
  horse_j: string;
  horse_i_cn: string;
  horse_j_cn: string;
  horse_i_no: number;
  horse_j_no: number;
  prob: number;
  est_dividend: number;
  ev: number;
}

export interface Prediction {
  race_info: RaceInfo;
  horses: Horse[];
  combos: Combo[];
}

export interface BetSummary {
  total_races: number;
  total_bets: number;
  total_wins: number;
  win_rate: number;
  roi: number;
  total_staked: number;
  total_profit: number;
  final_bankroll: number;
  max_drawdown_pct: number;
  equity_curve: number[];
}

export interface Bet {
  date: string;
  venue: string;
  race_no: number;
  combo: string;
  horse_i: string;
  horse_j: string;
  horse_i_cn: string;
  horse_j_cn: string;
  horse_i_no: number;
  horse_j_no: number;
  prob: number;
  est_div: number;
  ev: number;
  stake: number;
  result: string;
  actual_div: number;
  profit: number;
}

export interface RaceSummary {
  venue: string;
  race_no: number;
  n_horses: number;
  distance: number;
  race_class: string;
  going: string;
}

export interface FeatureImportance {
  feature: string;
  importance: number;
}

export interface LiveRaceSummary {
  venue: string;
  race_no: number;
  n_runners: number;
  distance: number;
  race_class: string;
  going: string;
  race_date: string;
}

export interface LiveHorse {
  horse_no: number;
  horse_name: string;
  horse_name_cn: string;
  jockey: string;
  jockey_cn: string;
  trainer: string;
  trainer_cn: string;
  draw: number;
  weight: number;
  win_odds: number;
  fund_prob: number;
  top2_prob: number;
  market_prob: number;
  place_prob: number;
  cold_score: number;
}

export interface LiveCombo {
  horse_i: string;
  horse_j: string;
  horse_i_cn: string;
  horse_j_cn: string;
  horse_i_no: number;
  horse_j_no: number;
  prob: number;
  est_dividend: number;
  ev: number;
  cold_score: number;
  multiplier: number;
  suggested_stake: number;
}

export interface LivePrediction {
  race_info: RaceInfo;
  horses: LiveHorse[];
  combos: LiveCombo[];
  suggested_total_stake: number;
  risk_caps: { max_per_race: number; max_per_day: number };
}

export interface HorseFormConditions {
  runs: number;
  win_rate: number;
  top3_rate: number;
  avg_pos: number | null;
}

export interface HorseRecentRace {
  date: string;
  venue: string;
  distance: number;
  race_class: string;
  going: string;
  draw: number;
  weight: number;
  jockey: string;
  jockey_cn: string;
  odds: number;
  finish_pos: number;
  margin: string;
  finish_time: string;
  sectional_time: string[];
}

export interface HorseForm {
  horse_name: string;
  horse_name_cn: string;
  runs: number;
  form_string: string;
  win_rate: number;
  top2_rate: number;
  top3_rate: number;
  avg_pos: number;
  last_pos: number;
  days_since_last: number | null;
  form_trend: string;
  streak_top3: number;
  venue: Record<string, HorseFormConditions>;
  course: Record<string, HorseFormConditions>;
  going: Record<string, HorseFormConditions>;
  dist: HorseFormConditions | null;
  market: { avg_odds: number | null; last_odds: number | null; min_odds: number | null; max_odds: number | null };
  recent: HorseRecentRace[];
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export const api = {
  health: () => getJson<Record<string, unknown>>("/api/health"),
  dates: (region = "hk") => getJson<{ dates: string[] }>(`/api/dates?region=${region}`),
  races: (date: string, region = "hk") =>
    getJson<{ races: RaceSummary[] }>(`/api/races?date=${date}&region=${region}`),
  predict: (date: string, venue: string, race_no: number, region = "hk") =>
    getJson<Prediction>(`/api/predict?date=${date}&venue=${venue}&race_no=${race_no}&region=${region}`),
  backtestSummary: (region = "hk") => getJson<BetSummary>(`/api/backtest/summary?region=${region}`),
  backtestBets: (params: Record<string, string | number>, region = "hk") => {
    const qs = new URLSearchParams(
      Object.entries({ ...params, region }).map(([k, v]) => [k, String(v)]),
    ).toString();
    return getJson<{ bets: Bet[]; total: number }>(`/api/backtest/bets?${qs}`);
  },
  featureImportance: (model: string, region = "hk") =>
    getJson<{ model: string; features: FeatureImportance[] }>(
      `/api/models/importance?model=${model}&region=${region}`,
    ),
  modelInfo: (region = "hk") => getJson<Record<string, unknown>>(`/api/models/info?region=${region}`),
  liveRaces: (date: string) =>
    getJson<{ races: LiveRaceSummary[] }>(`/api/live/races?date=${date}`),
  livePredict: (date: string, venue: string, race_no: number) =>
    getJson<LivePrediction>(`/api/live/predict?date=${date}&venue=${venue}&race_no=${race_no}`),
  liveStatus: () => getJson<Record<string, unknown>>("/api/live/status"),
  horseForm: (name: string, date: string, distance: number, venue: string, going: string, region = "hk") =>
    getJson<HorseForm>(
      `/api/horse/form?name=${encodeURIComponent(name)}&date=${date}&distance=${distance}&venue=${venue}&going=${encodeURIComponent(going)}&region=${region}`,
    ),
};
