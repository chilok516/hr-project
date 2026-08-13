"use client";

import { useEffect, useState } from "react";
import { api, BetSummary } from "@/lib/api";
import EquityChart from "@/components/EquityChart";

export default function Dashboard() {
  const [summary, setSummary] = useState<BetSummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.backtestSummary()
      .then(setSummary)
      .catch((e) => setError("Failed to load backtest data: " + e.message));
  }, []);

  if (error) {
    return (
      <div className="card" style={{ borderColor: "var(--red)" }}>
        <p className="red font-bold">Error</p>
        <p style={{ color: "#aaa", marginTop: 8 }}>{error}</p>
      </div>
    );
  }

  if (!summary) {
    return <p style={{ color: "#888" }}>Loading dashboard...</p>;
  }

  const stats = [
    { label: "Total Bets", value: summary.total_bets.toLocaleString(), cls: "" },
    { label: "Wins", value: summary.total_wins.toLocaleString(), cls: "green" },
    { label: "Win Rate", value: (summary.win_rate * 100).toFixed(1) + "%", cls: "green" },
    { label: "ROI", value: (summary.roi * 100).toFixed(1) + "%", cls: summary.roi > 0 ? "green" : "red" },
    { label: "Total Staked", value: "$" + summary.total_staked.toLocaleString(), cls: "" },
    { label: "Total P&L", value: "$" + summary.total_profit.toLocaleString(), cls: summary.total_profit > 0 ? "green" : "red" },
    { label: "Final Bankroll", value: "$" + summary.final_bankroll.toLocaleString(), cls: "green" },
    { label: "Max Drawdown", value: (summary.max_drawdown_pct * 100).toFixed(1) + "%", cls: "yellow" },
  ];

  return (
    <div>
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--accent)" }}>
        Dashboard
      </h1>
      <p className="text-xs mb-5" style={{ color: "#666" }}>
        {summary.total_races.toLocaleString()} races · walk-forward backtest · β=0.855 · EV&gt;0.4
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {stats.map((s) => (
          <div className="card" key={s.label}>
            <div className="text-[10px] uppercase tracking-wider" style={{ color: "#888" }}>
              {s.label}
            </div>
            <div className="text-2xl font-bold mt-1" style={{ color: s.cls || "var(--foreground)" }}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold mb-3" style={{ color: "#888" }}>
          Equity Curve
        </h2>
        <EquityChart data={summary.equity_curve} />
      </div>
    </div>
  );
}
