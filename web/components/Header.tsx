"use client";

import Link from "next/link";
import { useLang } from "@/lib/LanguageContext";

export default function Header() {
  const { lang, toggle, t } = useLang();

  const navItems = [
    { href: "/", label: t("live") },
    { href: "/predictions", label: t("predictions") },
    { href: "/backtest", label: t("backtest") },
    { href: "/models", label: t("models") },
  ];

  return (
    <header className="border-b" style={{ borderColor: "var(--border)" }}>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 sm:px-6 py-3 sm:py-4 max-w-7xl mx-auto">
        <Link href="/" className="font-bold text-lg whitespace-nowrap" style={{ color: "var(--accent)" }}>
          🏇 HKJC Quinella
        </Link>
        <nav className="flex gap-4 text-sm flex-wrap">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="hover:opacity-70 transition-opacity"
              style={{ color: "#bbb" }}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <button
          onClick={toggle}
          className="ml-auto px-3 py-1 rounded border text-sm"
          style={{ borderColor: "var(--border)", color: "#ccc", cursor: "pointer" }}
        >
          {lang === "zh" ? "EN" : "中文"}
        </button>
      </div>
    </header>
  );
}
