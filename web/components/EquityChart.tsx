"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

export default function EquityChart({ data }: { data: number[] }) {
  const chartData = data.map((value, i) => ({
    i,
    value: Math.round(value / 1000), // in thousands
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2a" />
        <XAxis dataKey="i" tick={{ fill: "#666", fontSize: 11 }} />
        <YAxis
          tick={{ fill: "#666", fontSize: 11 }}
          tickFormatter={(v) => `$${v}k`}
        />
        <Tooltip
          contentStyle={{ background: "#141420", border: "1px solid #2a2a3a" }}
          labelStyle={{ color: "#888" }}
          formatter={(v) => [`$${(Number(v) * 1000).toLocaleString()}`, "Equity"]}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#00d4aa"
          strokeWidth={1.5}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
