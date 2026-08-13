"use client";

import { useEffect, useState, useCallback } from "react";
import { api, LiveRaceSummary, LivePrediction } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { classLabel, goingLabel, distLabel, venueLabel, pickName } from "@/lib/i18n";
import InfoTip from "@/components/InfoTip";
import CollapsibleCard from "@/components/CollapsibleCard";

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

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("live")}</h1>
        <p className="mt-1 text-sm text-muted">{t("liveSub")}</p>
      </div>

      {note && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <span>ℹ️</span>
          <span>{lang === "zh" ? t("seasonNote") : note}</span>
        </div>
      )}

      <div className="card flex flex-wrap items-center gap-3">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input" />
        <button className="btn" onClick={() => setDate(todayStr())}>
          {t("today")}
        </button>
      </div>

      {races.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-muted">{tf("noRaces", date)}</p>
          <p className="mt-2 text-sm text-gray-400">
            {lang === "zh" ? t("seasonNote") : note}
          </p>
        </div>
      ) : (
        <div className="-mx-4 flex gap-2.5 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:overflow-visible md:px-0 md:pb-0">
          {races.map((r) => {
            const active = selected === r;
            return (
              <button
                key={`${r.venue}-${r.race_no}`}
                onClick={() => setSelected(r)}
                className={`flex shrink-0 items-center gap-3 rounded-xl border px-3.5 py-2.5 text-left transition-colors ${
                  active
                    ? "border-accent bg-accent/10"
                    : "border-border bg-white hover:border-gray-300"
                }`}
              >
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-base font-bold tabular-nums ${
                    active ? "bg-accent text-white" : "bg-gray-100 text-foreground"
                  }`}
                >
                  {r.race_no}
                </span>
                <span className="flex flex-col">
                  <span
                    className={`font-mono text-[15px] font-bold leading-none tabular-nums ${
                      active ? "text-accent" : "text-foreground"
                    }`}
                  >
                    {raceTime(r.venue, r.race_no)}
                  </span>
                  <span className={`mt-1 text-xs leading-tight ${active ? "text-accent/80" : "text-muted"}`}>
                    {venueLabel(r.venue, lang)} · {distLabel(r.distance, lang)} · {classLabel(r.race_class, lang)} · {goingLabel(r.going, lang)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {loading && !prediction && <p className="text-muted">{t("loading")}</p>}

      {selected && prediction && (
        <div className="space-y-5">
          <div className="card flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">
                {lang === "zh" ? "第" : "R"}{selected.race_no} · {classLabel(prediction.race_info.race_class, lang)} · {distLabel(prediction.race_info.distance, lang)} · {goingLabel(prediction.race_info.going, lang)}
              </h2>
              <p className="mt-1 text-sm text-muted">
                {prediction.race_info.date} · {venueLabel(prediction.race_info.venue, lang)} · {raceTime(selected.venue, selected.race_no)}
              </p>
            </div>
            <div className="text-right">
              <div className="text-xs uppercase tracking-wide text-muted">{t("countdown")}</div>
              <div className="font-mono text-3xl font-bold tabular-nums text-accent">
                {countdown(selected.venue, selected.race_no)}
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-muted">{t("horseProbs")}</h2>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("horseNo")}</th><th>{t("horse")}</th><th>{t("jockey")}</th>
                    <th><span className="inline-flex items-center">{t("draw")}<InfoTip text={t("drawTip")} /></span></th>
                    <th><span className="inline-flex items-center">{t("weight")}<InfoTip text={t("weightTip")} /></span></th>
                    <th><span className="inline-flex items-center">{t("fund")}<InfoTip text={t("fundTip")} /></span></th>
                    <th><span className="inline-flex items-center">{t("top2")}<InfoTip text={t("top2Tip")} /></span></th>
                    <th><span className="inline-flex items-center">{t("mkt")}<InfoTip text={t("mktTip")} /></span></th>
                    <th><span className="inline-flex items-center">{t("cold")}<InfoTip text={t("coldTip")} /></span></th>
                  </tr>
                </thead>
                <tbody>
                  {prediction.horses.map((h) => (
                    <tr key={h.horse_no}>
                      <td><span className="saddlecloth">{h.horse_no}</span></td>
                      <td className="font-semibold">{pickName(lang, h.horse_name, h.horse_name_cn)}</td>
                      <td className="text-muted">{pickName(lang, h.jockey, h.jockey_cn)}</td>
                      <td className="tabular-nums">{h.draw}</td>
                      <td className="tabular-nums">{h.weight}</td>
                      <td className="font-medium tabular-nums text-accent">{(h.fund_prob * 100).toFixed(1)}%</td>
                      <td className="tabular-nums">{(h.top2_prob * 100).toFixed(1)}%</td>
                      <td className="tabular-nums">{(h.market_prob * 100).toFixed(1)}%</td>
                      <td>
                        <span className={`badge ${h.cold_score >= 4 ? "badge-amber" : "badge-gray"}`}>
                          {h.cold_score.toFixed(1)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-muted">{t("combos")}</h2>
            {prediction.combos.length === 0 ? (
              <p className="text-muted">{t("noCombos")}</p>
            ) : (
              <>
                <div className="hidden md:block">
                  <div className="table-scroll">
                    <table className="data-table">
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
                              <span className="saddlecloth mr-2">{c.horse_i_no}</span>
                              {pickName(lang, c.horse_i, c.horse_i_cn)}
                              <span className="mx-1 text-muted">+</span>
                              <span className="saddlecloth mr-2">{c.horse_j_no}</span>
                              {pickName(lang, c.horse_j, c.horse_j_cn)}
                            </td>
                            <td className="tabular-nums">{(c.prob * 100).toFixed(2)}%</td>
                            <td className="tabular-nums">${c.est_dividend}</td>
                            <td>
                              <span className={`badge ${c.ev > 0.4 ? "badge-green" : "badge-red"}`}>
                                {c.ev.toFixed(3)}
                              </span>
                            </td>
                            <td className="tabular-nums">{c.cold_score.toFixed(1)}</td>
                            <td className="tabular-nums">{c.multiplier}×</td>
                            <td className="font-semibold tabular-nums text-accent">${c.suggested_stake}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="space-y-3 md:hidden">
                  {prediction.combos.map((c, i) => (
                    <CollapsibleCard
                      key={i}
                      header={
                        <span className="flex items-center gap-2">
                          <span className="flex min-w-0 flex-1 items-center gap-2 font-semibold">
                            <span className="saddlecloth">{c.horse_i_no}</span>
                            <span className="truncate">{pickName(lang, c.horse_i, c.horse_i_cn)}</span>
                            <span className="text-muted">+</span>
                            <span className="saddlecloth">{c.horse_j_no}</span>
                            <span className="truncate">{pickName(lang, c.horse_j, c.horse_j_cn)}</span>
                          </span>
                          <span className={`badge shrink-0 ${c.ev > 0.4 ? "badge-green" : "badge-red"}`}>
                            {c.ev.toFixed(3)}
                          </span>
                        </span>
                      }
                    >
                      <div className="grid grid-cols-3 gap-y-2.5 text-xs">
                        <div><div className="text-muted">{t("prob")}</div><div className="mt-0.5 font-medium tabular-nums">{(c.prob * 100).toFixed(2)}%</div></div>
                        <div><div className="text-muted">{t("estDiv")}</div><div className="mt-0.5 font-medium tabular-nums">${c.est_dividend}</div></div>
                        <div><div className="text-muted">{t("cold")}</div><div className="mt-0.5 font-medium tabular-nums">{c.cold_score.toFixed(1)}</div></div>
                        <div><div className="text-muted">×</div><div className="mt-0.5 font-medium tabular-nums">{c.multiplier}×</div></div>
                        <div><div className="text-muted">{t("stake")}</div><div className="mt-0.5 font-semibold tabular-nums text-accent">${c.suggested_stake}</div></div>
                      </div>
                    </CollapsibleCard>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-4 text-sm text-muted">
                  <span>
                    {t("totalStake")}:{" "}
                    <span className="font-semibold text-accent">${prediction.suggested_total_stake}</span>
                  </span>
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
