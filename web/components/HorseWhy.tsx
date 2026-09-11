"use client";

import { LiveHorse } from "@/lib/api";
import { useLang } from "@/lib/LanguageContext";
import { signalLabel } from "@/lib/i18n";

function Chip({ label, tone }: { label: string; tone: "accent" | "amber" | "muted" }) {
  const cls =
    tone === "accent" ? "border-accent/30 bg-accent/10 text-accent"
    : tone === "amber" ? "border-amber-200 bg-amber-50 text-amber-700"
    : "border-border bg-gray-50 text-muted";
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

export function SignalChips({ signals }: { signals: string[] }) {
  const { lang } = useLang();
  if (!signals || signals.length === 0) return null;
  return (
    <span className="flex flex-wrap items-center gap-1">
      {signals.map((s) => (
        <Chip key={s} label={signalLabel(s, lang)} tone={s === "fresh_horse" ? "muted" : "accent"} />
      ))}
    </span>
  );
}

function Row({ label, value, extra }: { label: string; value: string; extra?: string }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 font-medium tabular-nums">
        {value}
        {extra && <span className="text-xs text-muted"> {extra}</span>}
      </div>
    </div>
  );
}

export function HorseMetrics({ h }: { h: LiveHorse }) {
  const { t, lang } = useLang();
  const m = h.metrics || {};
  const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
  const fmtPos = (v: number | null | undefined) => (v == null ? "—" : `${v}`);
  const distStr =
    m.dist_runs == null ? "—" : `${m.dist_runs} ${lang === "zh" ? "場" : "runs"} · ${fmtPos(m.dist_avg_pos)}`;
  const venueStr =
    m.venue_runs == null ? "—" : `${m.venue_runs} ${lang === "zh" ? "場" : "runs"} · ${fmtPos(m.venue_avg_pos)}`;
  const daysStr = m.days_since == null ? "—" : `${m.days_since} ${lang === "zh" ? "日" : "d"}`;

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm sm:grid-cols-4">
      <Row label={t("winRate")} value={fmtPct(m.win_rate)} extra={m.runs != null ? `(${m.runs})` : ""} />
      <Row label={t("top3Rate")} value={fmtPct(m.top3_rate)} />
      <Row label={t("avgPos")} value={fmtPos(m.avg_pos)} />
      <Row label={t("jockeyWin")} value={fmtPct(m.jockey_win_rate)} />
      <Row label={t("trainerWin")} value={fmtPct(m.trainer_win_rate)} />
      <Row label={t("distForm")} value={distStr} />
      <Row label={t("venueForm")} value={venueStr} />
      <Row label={t("daysSince")} value={daysStr} />
    </div>
  );
}
