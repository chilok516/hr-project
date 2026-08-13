"use client";

import { useEffect, useState } from "react";
import { api, Prediction, RaceSummary } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { classLabel, goingLabel, distLabel, venueLabel, pickName } from "@/lib/i18n";

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
    <div>
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--accent)" }}>
        {t("predictions")}
      </h1>
      <p className="text-xs mb-5" style={{ color: "#666" }}>
        {t("selectRace")}
      </p>

      <div className="flex flex-wrap gap-3 mb-5">
        <select value={date} onChange={(e) => setDate(e.target.value)}>
          {dates.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <select value={venue} onChange={(e) => {
          const v = e.target.value;
          setVenue(v);
          const first = races.find((r) => r.venue === v);
          setRaceNo(first ? first.race_no : 1);
        }}>
          {venues.map((v) => (
            <option key={v} value={v}>{venueLabel(v, lang)}</option>
          ))}
        </select>

        <select value={raceNo} onChange={(e) => setRaceNo(Number(e.target.value))}>
          {venueRaces.map((r) => (
            <option key={r.race_no} value={r.race_no}>
              {lang === "zh" ? "第" : "R"}{r.race_no} — {classLabel(r.race_class, lang)} · {distLabel(r.distance, lang)}
            </option>
          ))}
        </select>
      </div>

      {loading && <p style={{ color: "#888" }}>{t("loading")}</p>}
      {error && <p className="red">{error}</p>}

      {prediction && (
        <div className="space-y-5">
          <div className="card">
            <h2 className="text-sm font-semibold mb-1">
              {lang === "zh" ? "第" : "Race"} {prediction.race_info.race_no} · {classLabel(prediction.race_info.race_class, lang)} ·{" "}
              {distLabel(prediction.race_info.distance, lang)} · {goingLabel(prediction.race_info.going, lang)}
            </h2>
            <p className="text-xs" style={{ color: "#666" }}>
              {prediction.race_info.date} · {venueLabel(prediction.race_info.venue, lang)}
            </p>
          </div>

          <div className="card">
            <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
              {t("horseProbs")}
            </h2>
            <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>{t("horseNo")}</th><th>{t("horse")}</th><th>{t("jockey")}</th><th>{t("odds")}</th>
                  <th>{t("fund")}</th><th>{t("top2")}</th><th>{t("mkt")}</th><th>{t("place")}</th><th>{t("actual")}</th>
                </tr>
              </thead>
              <tbody>
                {prediction.horses.map((h) => (
                  <tr key={h.horse_no} className={h.finish_pos === 1 ? "win" : ""}>
                    <td>{h.horse_no}</td>
                    <td className="font-semibold">{pickName(lang, h.horse_name, h.horse_name_cn)}</td>
                    <td style={{ color: "#aaa" }}>{pickName(lang, h.jockey, h.jockey_cn)}</td>
                    <td>{h.win_odds.toFixed(1)}</td>
                    <td className="green">{(h.fund_prob * 100).toFixed(1)}%</td>
                    <td>{(h.top2_prob * 100).toFixed(1)}%</td>
                    <td>{(h.market_prob * 100).toFixed(1)}%</td>
                    <td>{(h.place_prob * 100).toFixed(1)}%</td>
                    <td className={h.finish_pos === 1 ? "green font-bold" : ""}>{h.finish_pos}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>

          <div className="card">
            <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
              {lang === "zh" ? "連贏組合（前三精選）" : "Quinella Combos (top 3 anchors)"}
            </h2>
            {prediction.combos.length === 0 ? (
              <p style={{ color: "#888" }}>{lang === "zh" ? "此場沒有組合通過期望值篩選。" : "No combos passed the EV filter for this race."}</p>
            ) : (
              <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr><th>{t("combo")}</th><th>{t("prob")}</th><th>{t("estDiv")}</th><th>{t("ev")}</th></tr>
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
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
