"use client";

import { useEffect, useState } from "react";
import { api, FeatureImportance } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { useRegion } from "@/lib/RegionContext";

const modelOptions = [
  { value: "fundamental", label_en: "Fundamental (no odds)", label_zh: "基本面（無賠率）" },
  { value: "top2", label_en: "Top2 (no odds)", label_zh: "前二（無賠率）" },
  { value: "market", label_en: "Market (with odds)", label_zh: "市場（含賠率）" },
  { value: "place", label_en: "Place", label_zh: "位置" },
];

export default function Models() {
  const { lang, t } = useLang();
  const { region } = useRegion();
  const [model, setModel] = useState("top2");
  const [features, setFeatures] = useState<FeatureImportance[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.featureImportance(model, region)
      .then((d) => setFeatures(d.features))
      .finally(() => setLoading(false));
  }, [model, region]);

  const maxImp = features.length ? features[0].importance : 1;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t("modelsTitle")}</h1>
        <p className="mt-1 text-sm text-muted">{t("modelsSub")}</p>
      </div>

      <div className="card flex flex-wrap gap-2">
        {modelOptions.map((m) => (
          <button
            key={m.value}
            onClick={() => setModel(m.value)}
            className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
              model === m.value
                ? "border-accent bg-accent text-white"
                : "border-border bg-white text-foreground hover:border-gray-300"
            }`}
          >
            {lang === "zh" ? m.label_zh : m.label_en}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-muted">{t("loading")}</p>
      ) : (
        <div className="card">
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th>{t("feature")}</th><th>{t("importance")}</th><th></th></tr>
              </thead>
              <tbody>
                {features.map((f) => (
                  <tr key={f.feature}>
                    <td className="font-medium">{f.feature}</td>
                    <td className="tabular-nums">{f.importance.toFixed(0)}</td>
                    <td className="w-full">
                      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                        <div
                          className="h-2 rounded-full bg-accent"
                          style={{ width: `${(f.importance / maxImp) * 100}%` }}
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
