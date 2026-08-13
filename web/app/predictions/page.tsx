"use client";

import { useEffect, useState } from "react";
import { api, Prediction, RaceSummary } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { classLabel, goingLabel, distLabel, venueLabel, pickName } from "@/lib/i18n";
import CollapsibleCard from "@/components/CollapsibleCard";

export default function Predictions() {
  const { lang, t } = useLang();
  const [dates, setDates] = useState<string[]>([]);
  const [races, setRaces] = useState<RaceSummary[]>([]);
  const [date, setDate] = useState("");
  const [venue, setVenue] = useState("ST");
  const [raceNo, setRaceNo] = useState(1);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.dates().then((d) => {
      setDates(d.dates);
      if (d.dates.length) setDate(d.dates[d.dates.length - 1]);
    }).catch((e) => setError("Failed to load dates: " + e.message));
  }, []);

  useEffect(() => {
    if (!date) return;
    setRaces([]);
    api.races(date).then((r) => {
      setRaces(r.races);
      if (r.races.length) {
        setVenue(r.races[0].venue);
        setRaceNo(r.races[0].race_no);
      }
    }).catch(() => setRaces([]));
  }, [date]);

  useEffect(() => {
    if (!date || !venue) return;
    setLoading(true);
    setError("");
    setPrediction(null);
    api.predict(date, venue, raceNo)
      .then((p) => setPrediction(p))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [date, venue, raceNo]);

  const venues = ["ST", "HV"];
  const venueRaces = races.filter((r) => r.venue === venue);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("predictions")}</h1>
        <p className="mt-1 text-sm text-muted">{t("selectRace")}</p>
      </div>

      <div className="card flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <select value={date} onChange={(e) => setDate(e.target.value)} className="select w-full sm:w-auto">
          {dates.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <select value={venue} onChange={(e) => {
          const v = e.target.value;
          setVenue(v);
          const first = races.find((r) => r.venue === v);
          setRaceNo(first ? first.race_no : 1);
        }} className="select w-full sm:w-auto">
          {venues.map((v) => (
            <option key={v} value={v}>{venueLabel(v, lang)}</option>
          ))}
        </select>

        <select value={raceNo} onChange={(e) => setRaceNo(Number(e.target.value))} className="select w-full sm:w-auto">
          {venueRaces.map((r) => (
            <option key={r.race_no} value={r.race_no}>
              {lang === "zh" ? "第" : "R"}{r.race_no} — {classLabel(r.race_class, lang)} · {distLabel(r.distance, lang)}
            </option>
          ))}
        </select>
      </div>

      {loading && <p className="text-muted">{t("loading")}</p>}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {prediction && (
        <div className="space-y-5">
          <div className="card">
            <h2 className="font-semibold">
              {lang === "zh" ? "第" : "Race"} {prediction.race_info.race_no} · {classLabel(prediction.race_info.race_class, lang)} ·{" "}
              {distLabel(prediction.race_info.distance, lang)} · {goingLabel(prediction.race_info.going, lang)}
            </h2>
            <p className="mt-1 text-sm text-muted">
              {prediction.race_info.date} · {venueLabel(prediction.race_info.venue, lang)}
            </p>
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-muted">{t("horseProbs")}</h2>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("horseNo")}</th><th>{t("horse")}</th><th>{t("jockey")}</th><th>{t("odds")}</th>
                    <th>{t("fund")}</th><th>{t("top2")}</th><th>{t("mkt")}</th><th>{t("place")}</th><th>{t("actual")}</th>
                  </tr>
                </thead>
                <tbody>
                  {prediction.horses.map((h) => (
                    <tr key={h.horse_no} className={h.finish_pos === 1 ? "win" : ""}>
                      <td><span className="saddlecloth">{h.horse_no}</span></td>
                      <td className="font-semibold">{pickName(lang, h.horse_name, h.horse_name_cn)}</td>
                      <td className="text-muted">{pickName(lang, h.jockey, h.jockey_cn)}</td>
                      <td className="tabular-nums">{h.win_odds.toFixed(1)}</td>
                      <td className="font-medium tabular-nums text-accent">{(h.fund_prob * 100).toFixed(1)}%</td>
                      <td className="tabular-nums">{(h.top2_prob * 100).toFixed(1)}%</td>
                      <td className="tabular-nums">{(h.market_prob * 100).toFixed(1)}%</td>
                      <td className="tabular-nums">{(h.place_prob * 100).toFixed(1)}%</td>
                      <td>
                        {h.finish_pos === 1 ? (
                          <span className="badge badge-green">1</span>
                        ) : (
                          <span className="tabular-nums">{h.finish_pos}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-muted">
              {lang === "zh" ? "連贏組合（前三精選）" : "Quinella Combos (top 3 anchors)"}
            </h2>
            {prediction.combos.length === 0 ? (
              <p className="text-muted">{lang === "zh" ? "此場沒有組合通過期望值篩選。" : "No combos passed the EV filter for this race."}</p>
            ) : (
              <>
                <div className="hidden md:block">
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead>
                        <tr><th>{t("combo")}</th><th>{t("prob")}</th><th>{t("estDiv")}</th><th>{t("ev")}</th></tr>
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
                        <div><div className="text-muted">{t("ev")}</div><div className="mt-0.5"><span className={`badge ${c.ev > 0.4 ? "badge-green" : "badge-red"}`}>{c.ev.toFixed(3)}</span></div></div>
                      </div>
                    </CollapsibleCard>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
