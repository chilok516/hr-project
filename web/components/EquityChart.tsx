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
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="i" tick={{ fill: "#6b7280", fontSize: 11 }} />
        <YAxis
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickFormatter={(v) => `$${v}k`}
        />
        <Tooltip
          contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8 }}
          labelStyle={{ color: "#6b7280" }}
          formatter={(v) => [`$${(Number(v) * 1000).toLocaleString()}`, "Equity"]}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#059669"
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
