"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { pickName } from "@/lib/i18n";

function todayStr(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

interface UkRace {
  meeting: string;
  race_no: number;
  name: string;
  name_ch: string;
  postTime: string;
  venueCode: string;
  country: string;
}

export default function UkLive() {
  const { lang } = useLang();
  const [races, setRaces] = useState<UkRace[]>([]);
  const [selected, setSelected] = useState<UkRace | null>(null);
  const [prediction, setPrediction] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.ukLiveRaces(todayStr()).then((d) => {
      const list: UkRace[] = [];
      for (const m of d.meetings || []) {
        const vc = String(m.venueCode || "");
        const country = (m as any).country_name || "";
        for (const r of (m as any).races || []) {
          list.push({
            meeting: `${todayStr().replace(/-/g, "")}_${vc}`,
            race_no: Number(r.no),
            name: r.raceName_en || "",
            name_ch: r.raceName_ch || "",
            postTime: r.postTime || "",
            venueCode: vc,
            country,
          });
        }
      }
      setRaces(list);
      if (list.length) setSelected(list[0]);
    }).catch((e) => setError("Failed to load simulcast races: " + e.message));
  }, []);

  useEffect(() => {
    if (!selected) { setPrediction(null); return; }
    setLoading(true);
    setError("");
    api.ukLivePredict(selected.meeting, selected.race_no)
      .then((p) => setPrediction(p))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selected]);

  const label = (en: string, zh: string) => (lang === "zh" ? zh : en);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{label("UK Simulcast", "英國越洋轉播")}</h1>
        <p className="mt-1 text-sm text-muted">
          {label("Tonight's HKJC simulcast races — top picks & quinella combos", "今晚 HKJC 越洋轉播賽事 — 精選 + 連贏組合")}
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {races.length === 0 ? (
        <div className="card py-12 text-center">
          <p className="text-muted">{label("No simulcast races today", "今日暫無越洋轉播賽事")}</p>
        </div>
      ) : (
        <div className="-mx-4 flex gap-2.5 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:overflow-visible md:px-0">
          {races.map((r) => {
            const active = selected === r;
            return (
              <button
                key={`${r.meeting}-${r.race_no}`}
                onClick={() => setSelected(r)}
                className={`flex shrink-0 flex-col gap-1 rounded-xl border px-3.5 py-2.5 text-left transition-colors ${
                  active ? "border-accent bg-accent/10" : "border-border bg-white hover:border-gray-300"
                }`}
              >
                <div className={`text-sm font-bold ${active ? "text-accent" : "text-foreground"}`}>
                  {r.venueCode}-{r.race_no} · {r.postTime.slice(11, 16)}
                </div>
                <div className={`text-xs ${active ? "text-accent/80" : "text-muted"}`}>
                  {lang === "zh" && r.name_ch ? r.name_ch : r.name}
                </div>
                <div className={`text-xs ${active ? "text-accent/60" : "text-gray-400"}`}>{r.country}</div>
              </button>
            );
          })}
        </div>
      )}

      {loading && <p className="text-muted">{label("載入預測中...", "Loading prediction...")}</p>}

      {selected && prediction && (
        <div className="space-y-5">
          <div className="card">
            <h2 className="font-semibold">
              {prediction.race_info.venue} R{selected.race_no} · {prediction.race_info.distance}m · {prediction.race_info.race_class}
            </h2>
            <p className="mt-1 text-sm text-muted">
              {lang === "zh" && selected.name_ch ? selected.name_ch : selected.name} · {selected.postTime.slice(11, 16)}
            </p>
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-muted">{label("Top Picks", "精選馬匹")}</h2>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th><th>{label("Horse", "馬名")}</th><th>{label("Trainer", "練馬師")}</th>
                    <th>{label("Top2", "前二")}</th><th>{label("Fund", "基本面")}</th>
                  </tr>
                </thead>
                <tbody>
                  {prediction.horses.map((h: any) => (
                    <tr key={h.horse_no}>
                      <td><span className="saddlecloth">{h.horse_no}</span></td>
                      <td className="font-semibold">{pickName(lang, h.horse_name, h.horse_name_cn)}</td>
                      <td className="text-muted">{h.trainer}</td>
                      <td className="font-bold text-lg tabular-nums text-accent">{(h.top2_prob * 100).toFixed(1)}%</td>
                      <td className="tabular-nums">{(h.fund_prob * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-muted">{label("Quinella Combos", "連贏組合")}</h2>
            {!prediction.combos.length ? (
              <p className="text-muted">{label("No combos", "無組合")}</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr><th>{label("Combo", "組合")}</th><th>{label("Prob", "機率")}</th><th>{label("Est Div", "預計派彩")}</th><th>EV</th></tr>
                  </thead>
                  <tbody>
                    {prediction.combos.map((c: any, i: number) => (
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
                          <span className={`badge ${c.ev > 0.4 ? "badge-green" : "badge-red"}`}>{c.ev.toFixed(3)}</span>
                        </td>
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
