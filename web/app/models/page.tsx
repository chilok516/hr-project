"use client";

import { useEffect, useState } from "react";
import { api, FeatureImportance } from "@/lib/api";

const modelOptions = [
  { value: "fundamental", label: "Fundamental (no odds)" },
  { value: "top2", label: "Top2 (no odds)" },
  { value: "market", label: "Market (with odds)" },
  { value: "place", label: "Place" },
];

export default function Models() {
  const [model, setModel] = useState("top2");
  const [features, setFeatures] = useState<FeatureImportance[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.featureImportance(model)
      .then((d) => setFeatures(d.features))
      .finally(() => setLoading(false));
  }, [model]);

  const maxImp = features.length ? features[0].importance : 1;

  return (
    <div>
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--accent)" }}>
        Model Feature Importance
      </h1>
      <p className="text-xs mb-5" style={{ color: "#666" }}>
        4 LightGBM models · date-grouped CV · Platt calibration
      </p>

      <div className="flex gap-3 mb-5">
        {modelOptions.map((m) => (
          <button
            key={m.value}
            onClick={() => setModel(m.value)}
            className="px-4 py-2 rounded border text-sm"
            style={{
              background: model === m.value ? "var(--accent)" : "transparent",
              color: model === m.value ? "#000" : "#ccc",
              borderColor: model === m.value ? "var(--accent)" : "var(--border)",
              fontWeight: model === m.value ? "bold" : "normal",
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: "#888" }}>Loading...</p>
      ) : (
        <div className="card">
          <div className="table-scroll">
          <table className="data">
            <thead>
              <tr><th>Feature</th><th>Importance</th><th></th></tr>
            </thead>
            <tbody>
              {features.map((f) => (
                <tr key={f.feature}>
                  <td>{f.feature}</td>
                  <td>{f.importance.toFixed(0)}</td>
                  <td style={{ width: "100%" }}>
                    <div style={{ width: "100%", background: "#1a1a2a", borderRadius: 3, height: 8 }}>
                      <div
                        style={{
                          width: `${(f.importance / maxImp) * 100}%`,
                          background: "var(--accent)",
                          height: 8,
                          borderRadius: 3,
                        }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}
