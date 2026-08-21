// i18n: UI strings + technical field mappings for EN/中文 bilingual support.

export type Lang = "en" | "zh";

type UIString = string | ((...args: any[]) => string);

export const UI: Record<Lang, Record<string, UIString>> = {
  en: {
    live: "Live",
    predictions: "Predictions",
    backtest: "Backtest",
    models: "Models",
    liveSub: "Upcoming race predictions — top picks, quinella combos, suggested stakes",
    noRaces: (d: string) => `No races for ${d}.`,
    seasonNote: "HK racing season runs September–July. Next season starts early September.",
    today: "Today",
    loading: "Loading prediction...",
    horseProbs: "Horse Probabilities",
    combos: "Quinella Combos + Suggested Stakes",
    noCombos: "No combos passed the EV filter.",
    combo: "Combo",
    prob: "Prob",
    estDiv: "Est Div",
    ev: "EV",
    cold: "Cold",
    stake: "Stake",
    totalStake: "Suggested total stake",
    riskCap: (r: number, d: number) => `Cap: $${r}/race · $${d}/day`,
    countdown: "Countdown",
    started: "Started",
    horseNo: "#",
    horse: "Horse",
    jockey: "Jockey",
    trainer: "Trainer",
    draw: "Draw",
    weight: "Wt",
    odds: "Odds",
    fund: "Fund",
    top2: "Top2",
    mkt: "Mkt",
    place: "Place",
    actual: "Actual",
    selectRace: "Select a historical race to view model predictions vs actual results",
    backtestTitle: "Backtest Bets",
    modelsTitle: "Model Feature Importance",
    modelsSub: "4 LightGBM models · date-grouped CV · Platt calibration",
    date: "Date",
    result: "Result",
    profit: "P&L",
    all: "All",
    wins: "Wins",
    losses: "Losses",
    venues: "All Venues",
    searchHorse: "Search horse...",
    minDiv: "Min dividend",
    prev: "Prev",
    next: "Next",
    page: "Page",
    feature: "Feature",
    importance: "Importance",
    races: "Races",
    distance: "Distance",
    going: "Going",
    drawTip: "Gate position (1 = innermost rail). Inside draws usually help over short distances.",
    weightTip: "Weight carried by the horse, including jockey and gear. Heavier is a bigger handicap.",
    fundTip: "Model win probability from historical form only (no odds).",
    top2Tip: "Model probability the horse finishes in the top two (quinella).",
    mktTip: "Implied win probability derived from the market odds.",
    coldTip: "Cold score — how undervalued the market has priced this horse; higher means a bigger longshot.",
  },
  zh: {
    live: "即場",
    predictions: "預測",
    backtest: "回測",
    models: "模型",
    liveSub: "即將賽事預測 — 精選、連贏組合、建議注碼",
    noRaces: (d: string) => `${d} 沒有賽事。`,
    seasonNote: "香港馬季為九月至七月，下季九月初開鑼。",
    today: "今日",
    loading: "載入預測中...",
    horseProbs: "馬匹機率",
    combos: "連贏組合 + 建議注碼",
    noCombos: "沒有組合通過期望值篩選。",
    combo: "組合",
    prob: "機率",
    estDiv: "預計派彩",
    ev: "期望值",
    cold: "冷門分",
    stake: "注碼",
    totalStake: "建議總注碼",
    riskCap: (r: number, d: number) => `上限：$${r}/場 · $${d}/日`,
    countdown: "開跑倒數",
    started: "已開跑",
    horseNo: "馬號",
    horse: "馬名",
    jockey: "騎師",
    trainer: "練馬師",
    draw: "檔位",
    weight: "負磅",
    odds: "賠率",
    fund: "基本面",
    top2: "前二",
    mkt: "市場",
    place: "位置",
    actual: "實際",
    selectRace: "選擇歷史賽事，查看模型預測對比實際結果",
    backtestTitle: "回測注項",
    modelsTitle: "模型特徵重要性",
    modelsSub: "4 個 LightGBM 模型 · 日期分組交叉驗證 · Platt 校準",
    date: "日期",
    result: "結果",
    profit: "盈虧",
    all: "全部",
    wins: "勝出",
    losses: "落敗",
    venues: "全部場地",
    searchHorse: "搜尋馬匹...",
    minDiv: "最低派彩",
    prev: "上一頁",
    next: "下一頁",
    page: "頁",
    feature: "特徵",
    importance: "重要性",
    races: "場次",
    distance: "距離",
    going: "場地",
    drawTip: "閘位號碼（1＝最內欄）。短途賽內欄通常較有利。",
    weightTip: "馬匹負載磅數，包括騎師及裝備重量；負磅越重負擔越大。",
    fundTip: "模型根據馬匹歷史表現（不含賠率）計算的贏馬機率。",
    top2Tip: "模型預測馬匹跑入頭兩名（連贏）的機率。",
    mktTip: "由市場賠率推算的隱含贏馬機率。",
    coldTip: "冷門分 — 馬匹被市場低估的程度，越高代表越冷門。",
  },
};

export const CLASS_CN: Record<string, string> = {
  Class1: "第一班", Class2: "第二班", Class3: "第三班",
  Class4: "第四班", Class5: "第五班",
  G1: "一級賽", G2: "二級賽", G3: "三級賽",
};

export const GOING_CN: Record<string, string> = {
  GOOD: "好地", "GOOD TO FIRM": "好至快地", "GOOD TO YIELDING": "好至黏地",
  YIELDING: "黏地", "YIELDING TO SOFT": "黏至軟地",
  SOFT: "軟地", HEAVY: "大爛地", FIRM: "快地",
  AWT: "全天候", STANDARD: "全天候",
};

export const COURSE_CN: Record<string, string> = {
  TURF: "草地", AWT: "全天候", DIRT: "泥地",
};

export function classLabel(c: string, lang: Lang): string {
  if (lang === "zh") return CLASS_CN[c] || c;
  return c;
}

export function goingLabel(g: string, lang: Lang): string {
  if (lang === "zh") return GOING_CN[g] || g;
  return g;
}

export function distLabel(m: number, lang: Lang): string {
  return lang === "zh" ? `${m}米` : `${m}m`;
}

export function venueLabel(v: string, lang: Lang): string {
  if (v === "ST") return lang === "zh" ? "沙田" : "Sha Tin";
  if (v === "HV") return lang === "zh" ? "跑馬地" : "Happy Valley";
  return v; // UK/overseas course names -> raw
}

export function pickName(lang: Lang, en: string, cn: string): string {
  return lang === "zh" && cn ? cn : en;
}
