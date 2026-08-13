"use client";

import { useEffect, useState } from "react";
import { api, Prediction, RaceSummary } from "@/lib/api";

export default function Predictions() {
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
        Predictions
      </h1>
      <p className="text-xs mb-5" style={{ color: "#666" }}>
        Select a historical race to view model predictions vs actual results
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
            <option key={v} value={v}>{v === "ST" ? "Sha Tin" : "Happy Valley"}</option>
          ))}
        </select>

        <select value={raceNo} onChange={(e) => setRaceNo(Number(e.target.value))}>
          {venueRaces.map((r) => (
            <option key={r.race_no} value={r.race_no}>
              R{r.race_no} — {r.race_class} · {r.distance}m
            </option>
          ))}
        </select>
      </div>

      {loading && <p style={{ color: "#888" }}>Loading prediction...</p>}
      {error && <p className="red">{error}</p>}

      {prediction && (
        <div className="space-y-5">
          <div className="card">
            <h2 className="text-sm font-semibold mb-1">
              Race {prediction.race_info.race_no} · {prediction.race_info.race_class} ·{" "}
              {prediction.race_info.distance}m · {prediction.race_info.going}
            </h2>
            <p className="text-xs" style={{ color: "#666" }}>
              {prediction.race_info.date} · {prediction.race_info.venue === "ST" ? "Sha Tin" : "Happy Valley"}
            </p>
          </div>

          <div className="card">
            <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
              Horse Probabilities (sorted by fundamental)
            </h2>
            <table className="data">
              <thead>
                <tr>
                  <th>#</th><th>Horse</th><th>Jockey</th><th>Odds</th>
                  <th>Fund</th><th>Top2</th><th>Market</th><th>Place</th><th>Actual</th>
                </tr>
              </thead>
              <tbody>
                {prediction.horses.map((h) => (
                  <tr key={h.horse_no} className={h.finish_pos === 1 ? "win" : ""}>
                    <td>{h.horse_no}</td>
                    <td className="font-semibold">{h.horse_name}</td>
                    <td style={{ color: "#aaa" }}>{h.jockey}</td>
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

          <div className="card">
            <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
              Quinella Combos (top 3 anchors)
            </h2>
            {prediction.combos.length === 0 ? (
              <p style={{ color: "#888" }}>No combos passed the EV filter for this race.</p>
            ) : (
              <table className="data">
                <thead>
                  <tr><th>Combo</th><th>Prob</th><th>Est Dividend</th><th>EV</th></tr>
                </thead>
                <tbody>
                  {prediction.combos.map((c, i) => (
                    <tr key={i}>
                      <td className="font-semibold">{c.horse_i} + {c.horse_j}</td>
                      <td>{(c.prob * 100).toFixed(2)}%</td>
                      <td>${c.est_dividend}</td>
                      <td className={c.ev > 0.4 ? "green" : "red"}>{c.ev.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
