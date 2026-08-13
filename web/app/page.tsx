"use client";

import { useEffect, useState, useCallback } from "react";
import { api, LiveRaceSummary, LivePrediction } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { classLabel, goingLabel, distLabel, venueLabel, pickName } from "@/lib/i18n";

function raceTime(venue: string, raceNo: number): string {
  const base = venue === "HV" ? { h: 19, m: 15 } : { h: 13, m: 0 };
  const totalMin = base.h * 60 + base.m + 30 * (raceNo - 1);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function todayStr(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function Live() {
  const { lang, t, tf } = useLang();
  const [date, setDate] = useState(todayStr());
  const [races, setRaces] = useState<LiveRaceSummary[]>([]);
  const [selected, setSelected] = useState<LiveRaceSummary | null>(null);
  const [prediction, setPrediction] = useState<LivePrediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [now, setNow] = useState(Date.now());

  const loadRaces = useCallback((d: string) => {
    setRaces([]);
    setSelected(null);
    setPrediction(null);
    api.liveRaces(d).then((r) => {
      setRaces(r.races);
      if (r.races.length) setSelected(r.races[0]);
    }).catch((e) => setError("Failed to load races: " + e.message));
  }, []);

  useEffect(() => {
    api.liveStatus().then((s) => {
      if (s.season_note) setNote(String(s.season_note));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    loadRaces(date);
  }, [date, loadRaces]);

  useEffect(() => {
    if (!selected) { setPrediction(null); return; }
    let cancelled = false;
    const fetchPred = () => {
      setLoading(true);
      api.livePredict(date, selected.venue, selected.race_no)
        .then((p) => { if (!cancelled) { setPrediction(p); setError(""); } })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    };
    fetchPred();
    const interval = setInterval(fetchPred, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [selected, date]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  function countdown(v: string, rn: number): string {
    const time = raceTime(v, rn);
    const [h, m] = time.split(":").map(Number);
    const target = new Date(`${date}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`);
    const diff = target.getTime() - now;
    if (diff <= 0) return t("started");
    const d = Math.floor(diff / 86400000);
    const hrs = Math.floor((diff % 86400000) / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    const secs = Math.floor((diff % 60000) / 1000);
    if (d > 0) return lang === "zh" ? `${d}日 ${hrs}小時` : `${d}d ${hrs}h`;
    return `${String(hrs).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  const cLabel = (v: string) => classLabel(v, lang);

  return (
    <div>
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--accent)" }}>
        {t("live")}
      </h1>
      <p className="text-xs mb-3" style={{ color: "#666" }}>
        {t("liveSub")}
      </p>
      {note && (
        <p className="text-xs mb-3 yellow">
          {lang === "zh" ? t("seasonNote") : note}
        </p>
      )}

      <div className="flex flex-wrap gap-3 mb-5">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <button
          className="px-3 py-1 rounded border text-sm"
          style={{ borderColor: "var(--border)", color: "#bbb" }}
          onClick={() => { setDate(todayStr()); }}
        >
          {t("today")}
        </button>
      </div>

      {races.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <p style={{ color: "#888" }}>{tf("noRaces", date)}</p>
          <p className="text-xs mt-2" style={{ color: "#666" }}>
            {lang === "zh" ? t("seasonNote") : note}
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3 mb-5">
          {races.map((r) => (
            <button
              key={`${r.venue}-${r.race_no}`}
              onClick={() => setSelected(r)}
              className="text-left px-4 py-3 rounded border"
              style={{
                background: selected === r ? "var(--accent)" : "transparent",
                color: selected === r ? "#000" : "#ccc",
                borderColor: selected === r ? "var(--accent)" : "var(--border)",
              }}
            >
              <div className="font-bold text-sm">{lang === "zh" ? "第" : "R"}{r.race_no} · {raceTime(r.venue, r.race_no)}</div>
              <div className="text-xs mt-1">{venueLabel(r.venue, lang)} · {distLabel(r.distance, lang)}</div>
              <div className="text-xs">{classLabel(r.race_class, lang)} · {goingLabel(r.going, lang)}</div>
            </button>
          ))}
        </div>
      )}

      {error && <p className="red mb-3">{error}</p>}
      {loading && !prediction && <p style={{ color: "#888" }}>{t("loading")}</p>}

      {selected && prediction && (
        <div className="space-y-5">
          <div className="card flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">
                {lang === "zh" ? "第" : "R"}{selected.race_no} · {classLabel(prediction.race_info.race_class, lang)} · {distLabel(prediction.race_info.distance, lang)} · {goingLabel(prediction.race_info.going, lang)}
              </h2>
              <p className="text-xs mt-1" style={{ color: "#666" }}>
                {prediction.race_info.date} · {venueLabel(prediction.race_info.venue, lang)} · {raceTime(selected.venue, selected.race_no)}
              </p>
            </div>
            <div className="text-right">
              <div className="text-xs" style={{ color: "#888" }}>{t("countdown")}</div>
              <div className="text-2xl font-bold green">{countdown(selected.venue, selected.race_no)}</div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
              {t("horseProbs")}
            </h2>
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th>{t("horseNo")}</th><th>{t("horse")}</th><th>{t("jockey")}</th>
                    <th>{t("draw")}</th><th>{t("weight")}</th>
                    <th>{t("fund")}</th><th>{t("top2")}</th><th>{t("mkt")}</th><th>{t("cold")}</th>
                  </tr>
                </thead>
                <tbody>
                  {prediction.horses.map((h) => (
                    <tr key={h.horse_no}>
                      <td>{h.horse_no}</td>
                      <td className="font-semibold">{pickName(lang, h.horse_name, h.horse_name_cn)}</td>
                      <td style={{ color: "#aaa" }}>{pickName(lang, h.jockey, h.jockey_cn)}</td>
                      <td>{h.draw}</td>
                      <td>{h.weight}</td>
                      <td className="green">{(h.fund_prob * 100).toFixed(1)}%</td>
                      <td>{(h.top2_prob * 100).toFixed(1)}%</td>
                      <td>{(h.market_prob * 100).toFixed(1)}%</td>
                      <td className={h.cold_score >= 4 ? "yellow" : ""}>{h.cold_score.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
              {t("combos")}
            </h2>
            {prediction.combos.length === 0 ? (
              <p style={{ color: "#888" }}>{t("noCombos")}</p>
            ) : (
              <>
                <div className="table-scroll">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>{t("combo")}</th><th>{t("prob")}</th><th>{t("estDiv")}</th><th>{t("ev")}</th>
                        <th>{t("cold")}</th><th>×</th><th>{t("stake")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prediction.combos.map((c, i) => (
                        <tr key={i}>
                          <td className="font-semibold">
                            {c.horse_i_no}.{pickName(lang, c.horse_i, c.horse_i_cn)} + {c.horse_j_no}.{pickName(lang, c.horse_j, c.horse_j_cn)}
                          </td>
                          <td>{(c.prob * 100).toFixed(2)}%</td>
                          <td>${c.est_dividend}</td>
                          <td className={c.ev > 0.4 ? "green" : "red"}>{c.ev.toFixed(3)}</td>
                          <td>{c.cold_score.toFixed(1)}</td>
                          <td>{c.multiplier}×</td>
                          <td className="green font-bold">${c.suggested_stake}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex flex-wrap gap-4 mt-3 text-xs" style={{ color: "#aaa" }}>
                  <span>{t("totalStake")}: <span className="green font-bold">${prediction.suggested_total_stake}</span></span>
                  <span>⚠️ {tf("riskCap", prediction.risk_caps.max_per_race, prediction.risk_caps.max_per_day)}</span>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
