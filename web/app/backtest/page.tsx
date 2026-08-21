"use client";

import { useEffect, useState } from "react";
import { api, Bet } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { useRegion } from "@/lib/RegionContext";
import { pickName, venueLabel } from "@/lib/i18n";
import CollapsibleCard from "@/components/CollapsibleCard";

export default function Backtest() {
  const { lang, t } = useLang();
  const { region } = useRegion();
  const [bets, setBets] = useState<Bet[]>([]);
  const [total, setTotal] = useState(0);
  const [result, setResult] = useState("all");
  const [venue, setVenue] = useState("all");
  const [search, setSearch] = useState("");
  const [minDiv, setMinDiv] = useState("");
  const [sortCol, setSortCol] = useState("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);

  const limit = 200;

  useEffect(() => {
    setLoading(true);
    api.backtestBets({ result, venue, search, min_div: minDiv || 0, limit, offset }, region)
      .then((d) => { setBets(d.bets); setTotal(d.total); })
      .finally(() => setLoading(false));
  }, [result, venue, search, minDiv, offset, region]);

  const sorted = [...bets].sort((a, b) => {
    let va = (a as any)[sortCol];
    let vb = (b as any)[sortCol];
    if (typeof va === "string") return sortDir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortDir === "asc" ? va - vb : vb - va;
  });

  const wins = bets.filter((b) => b.result === "WIN").length;
  const pnl = bets.reduce((s, b) => s + b.profit, 0);
  const staked = bets.reduce((s, b) => s + b.stake, 0);
  const roi = staked ? (pnl / staked) * 100 : 0;

  function toggleSort(col: string) {
    if (sortCol === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  const stats: { label: string; value: string; tone?: "green" | "red"; sub?: string }[] = [
    { label: t("page"), value: bets.length.toLocaleString(), sub: lang === "zh" ? "注" : "bets" },
    {
      label: t("wins"),
      value: `${wins}`,
      sub: bets.length ? `${(wins / bets.length * 100).toFixed(1)}%` : "—",
      tone: "green",
    },
    { label: t("profit"), value: `${pnl > 0 ? "+" : ""}$${pnl.toLocaleString()}`, tone: pnl > 0 ? "green" : "red" },
    { label: "ROI", value: `${roi > 0 ? "+" : ""}${roi.toFixed(1)}%`, tone: roi > 0 ? "green" : "red" },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("backtestTitle")}</h1>
        <p className="mt-1 text-sm text-muted">
          {total.toLocaleString()} {lang === "zh" ? "注 · 顯示" : "total bets · showing"} {offset + 1}–{Math.min(offset + limit, total)}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="card p-4">
            <div className="text-sm uppercase tracking-wide text-muted">{s.label}</div>
            <div className={`mt-1 text-3xl font-bold tabular-nums ${
              s.tone === "green" ? "text-accent" : s.tone === "red" ? "text-danger" : "text-foreground"
            }`}>
              {s.value}
            </div>
            {s.sub && <div className="text-sm text-muted">{s.sub}</div>}
          </div>
        ))}
      </div>

      <div className="card flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <select value={result} onChange={(e) => { setResult(e.target.value); setOffset(0); }} className="select w-full sm:w-auto">
          <option value="all">{t("all")}</option>
          <option value="WIN">{t("wins")}</option>
          <option value="LOSS">{t("losses")}</option>
        </select>
        <select value={venue} onChange={(e) => { setVenue(e.target.value); setOffset(0); }} className="select w-full sm:w-auto">
          <option value="all">{t("venues")}</option>
          {region === "hk" && (
            <>
              <option value="ST">{venueLabel("ST", lang)}</option>
              <option value="HV">{venueLabel("HV", lang)}</option>
            </>
          )}
        </select>
        <input
          placeholder={t("searchHorse")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input w-full sm:w-auto"
        />
        <input
          type="number"
          placeholder={t("minDiv")}
          value={minDiv}
          onChange={(e) => setMinDiv(e.target.value)}
          className="input w-full sm:w-28"
        />
      </div>

      <div className="card hidden p-0 md:block">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th onClick={() => toggleSort("date")} className="cursor-pointer select-none">{t("date")}</th>
                <th onClick={() => toggleSort("venue")} className="cursor-pointer select-none">V</th>
                <th onClick={() => toggleSort("race_no")} className="cursor-pointer select-none">R#</th>
                <th>{t("combo")}</th>
                <th onClick={() => toggleSort("prob")} className="cursor-pointer select-none">{t("prob")}</th>
                <th onClick={() => toggleSort("est_div")} className="cursor-pointer select-none">{t("estDiv")}</th>
                <th onClick={() => toggleSort("ev")} className="cursor-pointer select-none">{t("ev")}</th>
                <th onClick={() => toggleSort("stake")} className="cursor-pointer select-none">{t("stake")}</th>
                <th onClick={() => toggleSort("result")} className="cursor-pointer select-none">{t("result")}</th>
                <th onClick={() => toggleSort("actual_div")} className="cursor-pointer select-none">{t("actual")}</th>
                <th onClick={() => toggleSort("profit")} className="cursor-pointer select-none">{t("profit")}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={11} className="text-muted">{t("loading")}</td></tr>
              ) : (
                sorted.map((b, i) => (
                  <tr key={i} className={b.result === "WIN" ? "win" : ""}>
                    <td className="tabular-nums">{b.date}</td>
                    <td>{b.venue}</td>
                    <td className="tabular-nums">{b.race_no}</td>
                    <td className="font-semibold">
                      <span className="saddlecloth mr-2">{b.horse_i_no}</span>
                      {pickName(lang, b.horse_i, b.horse_i_cn)}
                      <span className="mx-1 text-muted">+</span>
                      <span className="saddlecloth mr-2">{b.horse_j_no}</span>
                      {pickName(lang, b.horse_j, b.horse_j_cn)}
                    </td>
                    <td className="tabular-nums">{(b.prob * 100).toFixed(2)}%</td>
                    <td className="tabular-nums">${b.est_div}</td>
                    <td className="tabular-nums">{b.ev.toFixed(3)}</td>
                    <td className="tabular-nums">${b.stake}</td>
                    <td>
                      <span className={`badge ${b.result === "WIN" ? "badge-green" : "badge-red"}`}>
                        {b.result === "WIN" ? t("wins") : t("losses")}
                      </span>
                    </td>
                    <td className="tabular-nums">{b.actual_div > 0 ? "$" + b.actual_div : "—"}</td>
                    <td className={`font-semibold tabular-nums ${b.profit > 0 ? "text-accent" : "text-danger"}`}>
                      {b.profit > 0 ? "+" : ""}${b.profit.toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-3 md:hidden">
        {loading ? (
          <p className="text-muted">{t("loading")}</p>
        ) : (
          sorted.map((b, i) => (
            <CollapsibleCard
              key={i}
              header={
                <span className="flex flex-col gap-1.5">
                  <span className="flex items-center justify-between text-sm text-muted">
                    <span>{b.date} · {b.venue} · {lang === "zh" ? "第" : "R"}{b.race_no}</span>
                    <span className={`badge shrink-0 ${b.result === "WIN" ? "badge-green" : "badge-red"}`}>
                      {b.result === "WIN" ? t("wins") : t("losses")}
                    </span>
                  </span>
                  <span className="flex items-center gap-2 font-semibold">
                    <span className="saddlecloth">{b.horse_i_no}</span>
                    <span className="truncate">{pickName(lang, b.horse_i, b.horse_i_cn)}</span>
                    <span className="text-muted">+</span>
                    <span className="saddlecloth">{b.horse_j_no}</span>
                    <span className="truncate">{pickName(lang, b.horse_j, b.horse_j_cn)}</span>
                  </span>
                </span>
              }
            >
              <div className="grid grid-cols-3 gap-y-2.5 text-sm">
                <div><div className="text-muted">{t("prob")}</div><div className="mt-0.5 font-medium tabular-nums">{(b.prob * 100).toFixed(2)}%</div></div>
                <div><div className="text-muted">{t("estDiv")}</div><div className="mt-0.5 font-medium tabular-nums">${b.est_div}</div></div>
                <div><div className="text-muted">{t("ev")}</div><div className="mt-0.5 font-medium tabular-nums">{b.ev.toFixed(3)}</div></div>
                <div><div className="text-muted">{t("stake")}</div><div className="mt-0.5 font-medium tabular-nums">${b.stake}</div></div>
                <div><div className="text-muted">{t("actual")}</div><div className="mt-0.5 font-medium tabular-nums">{b.actual_div > 0 ? "$" + b.actual_div : "—"}</div></div>
                <div><div className="text-muted">{t("profit")}</div><div className={`mt-0.5 font-semibold tabular-nums ${b.profit > 0 ? "text-accent" : "text-danger"}`}>{b.profit > 0 ? "+" : ""}${b.profit.toLocaleString()}</div></div>
              </div>
            </CollapsibleCard>
          ))
        )}
      </div>

      <div className="flex gap-3">
        <button
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={offset === 0}
          className="btn"
        >
          {t("prev")}
        </button>
        <button
          onClick={() => setOffset(offset + limit)}
          disabled={offset + limit >= total}
          className="btn"
        >
          {t("next")}
        </button>
      </div>
    </div>
  );
}
