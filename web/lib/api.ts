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

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export const api = {
  health: () => getJson<Record<string, unknown>>("/api/health"),
  dates: () => getJson<{ dates: string[] }>("/api/dates"),
  races: (date: string) => getJson<{ races: RaceSummary[] }>(`/api/races?date=${date}`),
  predict: (date: string, venue: string, race_no: number) =>
    getJson<Prediction>(`/api/predict?date=${date}&venue=${venue}&race_no=${race_no}`),
  backtestSummary: () => getJson<BetSummary>("/api/backtest/summary"),
  backtestBets: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)]),
    ).toString();
    return getJson<{ bets: Bet[]; total: number }>(`/api/backtest/bets?${qs}`);
  },
  featureImportance: (model: string) =>
    getJson<{ model: string; features: FeatureImportance[] }>(
      `/api/models/importance?model=${model}`,
    ),
  modelInfo: () => getJson<Record<string, unknown>>("/api/models/info"),
  liveRaces: (date: string) =>
    getJson<{ races: LiveRaceSummary[] }>(`/api/live/races?date=${date}`),
  livePredict: (date: string, venue: string, race_no: number) =>
    getJson<LivePrediction>(`/api/live/predict?date=${date}&venue=${venue}&race_no=${race_no}`),
  liveStatus: () => getJson<Record<string, unknown>>("/api/live/status"),
};
