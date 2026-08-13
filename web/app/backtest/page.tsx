"use client";

import { useEffect, useState } from "react";
import { api, Bet } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { pickName, venueLabel } from "@/lib/i18n";

export default function Backtest() {
  const { lang, t } = useLang();
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
    api.backtestBets({ result, venue, search, min_div: minDiv || 0, limit, offset })
      .then((d) => { setBets(d.bets); setTotal(d.total); })
      .finally(() => setLoading(false));
  }, [result, venue, search, minDiv, offset]);

  const sorted = [...bets].sort((a, b) => {
    let va = (a as any)[sortCol];
    let vb = (b as any)[sortCol];
    if (typeof va === "string") return sortDir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortDir === "asc" ? va - vb : vb - va;
  });

  const wins = bets.filter((b) => b.result === "WIN").length;
  const pnl = bets.reduce((s, b) => s + b.profit, 0);
  const staked = bets.reduce((s, b) => s + b.stake, 0);

  function toggleSort(col: string) {
    if (sortCol === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--accent)" }}>
        {t("backtestTitle")}
      </h1>
      <p className="text-xs mb-5" style={{ color: "#666" }}>
        {total.toLocaleString()} {lang === "zh" ? "注 · 顯示" : "total bets · showing"} {offset + 1}–{Math.min(offset + limit, total)}
      </p>

      <div className="flex flex-wrap gap-3 mb-4">
        <select value={result} onChange={(e) => { setResult(e.target.value); setOffset(0); }}>
          <option value="all">{t("all")}</option>
          <option value="WIN">{t("wins")}</option>
          <option value="LOSS">{t("losses")}</option>
        </select>
        <select value={venue} onChange={(e) => { setVenue(e.target.value); setOffset(0); }}>
          <option value="all">{t("venues")}</option>
          <option value="ST">{venueLabel("ST", lang)}</option>
          <option value="HV">{venueLabel("HV", lang)}</option>
        </select>
        <input
          placeholder={t("searchHorse")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <input
          type="number"
          placeholder={t("minDiv")}
          value={minDiv}
          onChange={(e) => setMinDiv(e.target.value)}
          style={{ width: 120 }}
        />
      </div>

      <div className="flex flex-wrap gap-4 text-xs mb-3" style={{ color: "#aaa" }}>
        <span>{t("page")}: <span className="green">{bets.length}</span></span>
        <span>{t("wins")}: <span className="green">{wins}</span> ({bets.length ? (wins / bets.length * 100).toFixed(1) : 0}%)</span>
        <span>{t("profit")}: <span className={pnl > 0 ? "green" : "red"}>${pnl.toLocaleString()}</span></span>
        <span>ROI: <span className={pnl > 0 ? "green" : "red"}>{staked ? (pnl / staked * 100).toFixed(1) : 0}%</span></span>
      </div>

      <div className="card table-scroll" style={{ padding: 0 }}>
        <table className="data">
          <thead>
            <tr>
              <th onClick={() => toggleSort("date")}>{t("date")}</th>
              <th onClick={() => toggleSort("venue")}>V</th>
              <th onClick={() => toggleSort("race_no")}>R#</th>
              <th>{t("combo")}</th>
              <th onClick={() => toggleSort("prob")}>{t("prob")}</th>
              <th onClick={() => toggleSort("est_div")}>{t("estDiv")}</th>
              <th onClick={() => toggleSort("ev")}>{t("ev")}</th>
              <th onClick={() => toggleSort("stake")}>{t("stake")}</th>
              <th onClick={() => toggleSort("result")}>{t("result")}</th>
              <th onClick={() => toggleSort("actual_div")}>{t("actual")}</th>
              <th onClick={() => toggleSort("profit")}>{t("profit")}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={11} style={{ color: "#888" }}>{t("loading")}</td></tr>
            ) : (
              sorted.map((b, i) => (
                <tr key={i} className={b.result === "WIN" ? "win" : ""}>
                  <td>{b.date}</td>
                  <td>{b.venue}</td>
                  <td>{b.race_no}</td>
                  <td className="font-semibold">
                    {b.horse_i_no}.{pickName(lang, b.horse_i, b.horse_i_cn)} + {b.horse_j_no}.{pickName(lang, b.horse_j, b.horse_j_cn)}
                  </td>
                  <td>{(b.prob * 100).toFixed(2)}%</td>
                  <td>${b.est_div}</td>
                  <td>{b.ev.toFixed(3)}</td>
                  <td>${b.stake}</td>
                  <td>
                    <span style={{ color: b.result === "WIN" ? "var(--accent)" : "var(--red)", fontWeight: "bold" }}>
                      {b.result === "WIN" ? t("wins") : t("losses")}
                    </span>
                  </td>
                  <td>{b.actual_div > 0 ? "$" + b.actual_div : "—"}</td>
                  <td className={b.profit > 0 ? "green" : "red"}>
                    {b.profit > 0 ? "+" : ""}${b.profit.toLocaleString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex gap-3 mt-4">
        <button
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={offset === 0}
          style={{ opacity: offset === 0 ? 0.4 : 1 }}
          className="px-4 py-2 rounded border"
        >
          {t("prev")}
        </button>
        <button
          onClick={() => setOffset(offset + limit)}
          disabled={offset + limit >= total}
          style={{ opacity: offset + limit >= total ? 0.4 : 1 }}
          className="px-4 py-2 rounded border"
        >
          {t("next")}
        </button>
      </div>
    </div>
  );
}
