"use client";

import { useEffect, useState } from "react";
import { api, HorseForm as HorseFormData } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { venueLabel, distLabel, classLabel, goingLabel } from "@/lib/i18n";

export default function HorseForm({
  name,
  date,
  distance,
  venue,
  going,
}: {
  name: string;
  date: string;
  distance: number;
  venue: string;
  going: string;
}) {
  const { lang, t } = useLang();
  const [data, setData] = useState<HorseFormData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .horseForm(name, date, distance, venue, going)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [name, date, distance, venue, going]);

  const L = (zh: string, en: string) => (lang === "zh" ? zh : en);

  if (error) return <p className="text-sm text-muted">{L("無法載入往績", "Failed to load form")}</p>;
  if (!data) return <p className="text-sm text-muted">{L("載入中...", "Loading...")}</p>;
  if (!data.runs) return <p className="text-sm text-muted">{L("暫無往績", "No past races yet")}</p>;

  const trendLabel =
    data.form_trend === "up" ? L("上升", "Improving") : data.form_trend === "down" ? L("下滑", "Declining") : L("平穩", "Flat");
  const trendColor =
    data.form_trend === "up" ? "text-accent" : data.form_trend === "down" ? "text-danger" : "text-muted";

  const condRows = [
    { label: venueLabel("ST", lang), s: data.venue["ST"] },
    { label: venueLabel("HV", lang), s: data.venue["HV"] },
    { label: L("草地", "Turf"), s: data.course["turf"] },
    { label: L("全天候", "AWT/Dirt"), s: data.course["awt"] },
    { label: L("好地", "Good"), s: data.going["good"] },
    { label: L("濕地", "Wet"), s: data.going["wet"] },
  ];
  if (data.dist) {
    condRows.push({ label: L("同路程", "Same dist"), s: data.dist });
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-gray-50 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-semibold text-muted">{L("近6場", "Last 6")}</span>
          <span className="flex flex-wrap items-center gap-1">
            {data.form_string.split("-").map((p, i) => {
              const n = Number(p);
              return (
                <span
                  key={i}
                  className={`inline-flex h-6 w-6 items-center justify-center rounded text-xs font-bold tabular-nums ${
                    n === 1 ? "bg-accent text-white" : n <= 3 ? "bg-amber-100 text-amber-700" : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {n}
                </span>
              );
            })}
          </span>
          <span className={`text-sm font-semibold ${trendColor}`}>
            {trendLabel}
          </span>
        </div>

        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span>{L("勝率", "Win")} <b className="tabular-nums">{(data.win_rate * 100).toFixed(0)}%</b></span>
          <span>{L("上名率", "Top3")} <b className="tabular-nums">{(data.top3_rate * 100).toFixed(0)}%</b></span>
          <span>{L("平均名次", "Avg pos")} <b className="tabular-nums">{data.avg_pos}</b></span>
          <span>{L("上場", "Last")} <b className="tabular-nums">{data.last_pos}</b></span>
          {data.days_since_last != null && (
            <span>{L(`${data.days_since_last}日前`, `${data.days_since_last}d ago`)}</span>
          )}
          {data.streak_top3 >= 2 && (
            <span className="text-accent">{L(`連續${data.streak_top3}場入位`, `${data.streak_top3} top-3 streak`)}</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {condRows.map((c) => (
          <div key={c.label} className="rounded-lg border border-border p-2">
            <div className="text-xs text-muted">{c.label}</div>
            <div className="mt-0.5 text-sm">
              {c.s.runs ? (
                <>
                  <b className="tabular-nums">{c.s.runs}</b> {L("場", "runs")} ·{" "}
                  {L("勝", "win")} <b className="tabular-nums">{(c.s.win_rate * 100).toFixed(0)}%</b> ·{" "}
                  {L("均", "avg")} <b className="tabular-nums">{c.s.avg_pos}</b>
                </>
              ) : (
                <span className="text-gray-400">—</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {data.market.avg_odds != null && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
          <span>{L("平均賠率", "Avg odds")} <b className="text-foreground tabular-nums">{data.market.avg_odds}</b></span>
          {data.market.last_odds != null && (
            <span>{L("上場賠率", "Last odds")} <b className="text-foreground tabular-nums">{data.market.last_odds}</b></span>
          )}
          {data.market.min_odds != null && data.market.max_odds != null && (
            <span>{L("範圍", "Range")} <b className="text-foreground tabular-nums">{data.market.min_odds}–{data.market.max_odds}</b></span>
          )}
        </div>
      )}

      <div>
        <div className="mb-1 text-sm font-semibold text-muted">{L("最近往績", "Recent races")}</div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("date")}</th><th>{L("場", "V")}</th><th>{L("路程", "Dist")}</th>
                <th>{L("班", "Cls")}</th><th>{t("draw")}</th><th>{t("weight")}</th>
                <th>{t("jockey")}</th><th>{t("odds")}</th><th>{t("actual")}</th><th>{L("距離", "Mgn")}</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((r, i) => (
                <tr key={i} className={r.finish_pos === 1 ? "win" : ""}>
                  <td className="tabular-nums">{r.date}</td>
                  <td>{venueLabel(r.venue, lang)}</td>
                  <td className="tabular-nums">{distLabel(r.distance, lang)}</td>
                  <td>{classLabel(r.race_class, lang)}</td>
                  <td className="tabular-nums">{r.draw}</td>
                  <td className="tabular-nums">{r.weight}</td>
                  <td className="text-muted">{lang === "zh" && r.jockey_cn ? r.jockey_cn : r.jockey}</td>
                  <td className="tabular-nums">{r.odds > 0 ? r.odds : "—"}</td>
                  <td>
                    <span className={`inline-flex h-6 w-6 items-center justify-center rounded text-xs font-bold tabular-nums ${
                      r.finish_pos === 1 ? "bg-accent text-white" : r.finish_pos <= 3 ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-500"
                    }`}>
                      {r.finish_pos}
                    </span>
                  </td>
                  <td className="tabular-nums">{r.margin}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
