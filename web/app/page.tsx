"use client";

import { useEffect, useState, useCallback } from "react";
import { api, LiveRaceSummary, LivePrediction } from "@/lib/api";

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

  const venueLabel = (v: string) => (v === "ST" ? "Sha Tin" : "Happy Valley");

  function countdown(v: string, rn: number): string {
    const t = raceTime(v, rn);
    const [h, m] = t.split(":").map(Number);
    const target = new Date(`${date}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`);
    const diff = target.getTime() - now;
    if (diff <= 0) return "已開跑";
    const d = Math.floor(diff / 86400000);
    const hrs = Math.floor((diff % 86400000) / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    const secs = Math.floor((diff % 60000) / 1000);
    if (d > 0) return `${d}日 ${hrs}h`;
    return `${String(hrs).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--accent)" }}>
        Live
      </h1>
      <p className="text-xs mb-3" style={{ color: "#666" }}>
        Upcoming race predictions — top picks, quinella combos, suggested stakes
      </p>
      {note && (
        <p className="text-xs mb-3 yellow">{note}</p>
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
          Today
        </button>
      </div>

      {races.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <p style={{ color: "#888" }}>No races for {date}.</p>
          <p className="text-xs mt-2" style={{ color: "#666" }}>
            {note || "HK racing season runs September–July. Next season starts early September."}
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
              <div className="font-bold text-sm">R{r.race_no} · {raceTime(r.venue, r.race_no)}</div>
              <div className="text-xs mt-1">{venueLabel(r.venue)} · {r.distance}m</div>
              <div className="text-xs">{r.race_class} · {r.going}</div>
            </button>
          ))}
        </div>
      )}

      {error && <p className="red mb-3">{error}</p>}
      {loading && !prediction && <p style={{ color: "#888" }}>Loading prediction...</p>}

      {selected && prediction && (
        <div className="space-y-5">
          <div className="card flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">
                R{selected.race_no} · {prediction.race_info.race_class} · {prediction.race_info.distance}m · {prediction.race_info.going}
              </h2>
              <p className="text-xs mt-1" style={{ color: "#666" }}>
                {prediction.race_info.date} · {venueLabel(prediction.race_info.venue)} · {raceTime(selected.venue, selected.race_no)}
              </p>
            </div>
            <div className="text-right">
              <div className="text-xs" style={{ color: "#888" }}>開跑倒數</div>
              <div className="text-2xl font-bold green">{countdown(selected.venue, selected.race_no)}</div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
              Horse Probabilities
            </h2>
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th>#</th><th>Horse</th><th>Jockey</th><th>Draw</th><th>Wt</th>
                    <th>Fund</th><th>Top2</th><th>Mkt</th><th>Cold</th>
                  </tr>
                </thead>
                <tbody>
                  {prediction.horses.map((h) => (
                    <tr key={h.horse_no}>
                      <td>{h.horse_no}</td>
                      <td className="font-semibold">{h.horse_name}</td>
                      <td style={{ color: "#aaa" }}>{h.jockey}</td>
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
              Quinella Combos + Suggested Stakes
            </h2>
            {prediction.combos.length === 0 ? (
              <p style={{ color: "#888" }}>No combos passed the EV filter.</p>
            ) : (
              <>
                <div className="table-scroll">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Combo</th><th>Prob</th><th>Est Div</th><th>EV</th>
                        <th>Cold</th><th>×</th><th>Stake</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prediction.combos.map((c, i) => (
                        <tr key={i}>
                          <td className="font-semibold">{c.horse_i} + {c.horse_j}</td>
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
                  <span>建議總注碼: <span className="green font-bold">${prediction.suggested_total_stake}</span></span>
                  <span>⚠️ Cap: ${prediction.risk_caps.max_per_race}/race · ${prediction.risk_caps.max_per_day}/day</span>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
