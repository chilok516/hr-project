"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import {
  classLabel, distLabel, goingLabel, venueLabel, pickName, signalLabel,
} from "@/lib/i18n";

function RaceBlock({ race, lang }: { race: any; lang: "zh" | "en" }) {
  const ri = race.race_info || {};
  const top4 = (race.horses || []).slice(0, 4);
  const combo = (race.combos || [])[0];
  const L = (zh: string, en: string) => (lang === "zh" ? zh : en);

  return (
    <div className="mb-2 break-inside-avoid rounded border border-gray-300 bg-white p-2">
      <div className="mb-1 flex items-baseline justify-between border-b border-gray-200 pb-1">
        <span className="text-[11px] font-bold text-emerald-700">
          {L("第", "R")}{ri.race_no} · {distLabel(ri.distance, lang)} · {classLabel(ri.race_class, lang)}
        </span>
        <span className="text-[9px] text-gray-500">
          {goingLabel(ri.going, lang)}{ri.post_time ? ` · ${ri.post_time}` : ""}
        </span>
      </div>

      <div className="space-y-[3px]">
        {top4.map((h: any, i: number) => {
          const sigs = (h.cold_signals || []).slice(0, 2);
          return (
            <div key={h.horse_no} className="flex items-center gap-1 text-[9px] leading-tight">
              <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded bg-emerald-600 text-[8px] font-bold text-white tabular-nums">
                {h.horse_no}
              </span>
              <span className="min-w-0 flex-1 truncate font-semibold">
                {pickName(lang, h.horse_name, h.horse_name_cn)}
              </span>
              {sigs.map((s: string) => (
                <span key={s} className="shrink-0 rounded bg-emerald-50 px-1 text-[7px] font-medium text-emerald-700">
                  {signalLabel(s, lang)}
                </span>
              ))}
              <span className="shrink-0 font-bold tabular-nums text-emerald-700">
                {(h.top2_prob * 100).toFixed(1)}%
              </span>
              <span className="w-9 shrink-0 text-right tabular-nums text-gray-500">
                {(h.fund_prob * 100).toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>

      {combo && (
        <div className="mt-1 flex items-center justify-between border-t border-dashed border-gray-200 pt-1 text-[8px] text-gray-600">
          <span className="truncate">
            {L("連贏", "Q")} <b className="text-gray-800">{combo.horse_i_no}+{combo.horse_j_no}</b>{" "}
            {pickName(lang, combo.horse_i, combo.horse_i_cn)}
          </span>
          <span className="shrink-0 tabular-nums">
            EV {combo.ev?.toFixed(2)}
            {combo.suggested_stake ? ` · $${combo.suggested_stake}` : ""}
          </span>
        </div>
      )}
    </div>
  );
}

export default function ExportPage() {
  const { lang, t } = useLang();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const L = (zh: string, en: string) => (lang === "zh" ? zh : en);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const date = p.get("date") || "";
    const region = p.get("region") || "hk";
    if (!date) { setError("no date"); return; }
    api.liveExport(date, region)
      .then((d) => setData(d))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!data) return;
    const timer = setTimeout(() => window.print(), 500);
    return () => clearTimeout(timer);
  }, [data]);

  if (error) return <p className="text-danger">{L("匯出失敗：", "Export failed: ")}{error}</p>;
  if (!data) return <p className="text-muted">{L("正在準備 PDF...", "Preparing PDF...")}</p>;

  const ri = data.races[0]?.race_info || {};
  const venueName = data.venue === "ST" ? venueLabel("ST", lang)
    : data.venue === "HV" ? venueLabel("HV", lang) : (data.venue || "");

  return (
    <div className="print-root">
      <div className="mb-2 flex items-end justify-between border-b-2 border-emerald-600 pb-1.5">
        <div>
          <h1 className="text-base font-bold text-gray-900">
            {L("賽馬預測", "Race Predictions")}
          </h1>
          <p className="text-[10px] text-gray-600">
            {venueName}{venueName ? " · " : ""}{data.date} · {data.races.length} {L("場", "races")}
            {data.region === "uk" ? ` · ${L("越洋轉播", "Simulcast")}` : ""}
          </p>
        </div>
        <div className="text-right text-[9px] text-gray-400">
          <div>{L("產生時間", "generated")} {data.generated_at}</div>
          <div className="no-print mt-1">
            <button className="btn px-2 py-0.5 text-[10px]" onClick={() => window.print()}>
              {L("列印 / 儲存 PDF", "Print / Save PDF")}
            </button>
          </div>
        </div>
      </div>

      <div className="columns-2 gap-3">
        {data.races.map((race: any) => (
          <RaceBlock key={`${race.race_info?.venue}-${race.race_info?.race_no}`} race={race} lang={lang} />
        ))}
      </div>

      <div className="mt-2 border-t border-gray-200 pt-1 text-center text-[8px] text-gray-400">
        {L("模型機率僅供參考，不構成投注建議。", "Model probabilities are for reference only, not betting advice.")}
      </div>
    </div>
  );
}
