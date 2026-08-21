"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/LanguageContext";
import { useRegion } from "@/lib/RegionContext";

export default function Header() {
  const { lang, toggle, t } = useLang();
  const { region, toggle: toggleRegion } = useRegion();
  const pathname = usePathname();

  const navItems = [
    { href: "/", label: t("live") },
    { href: "/predictions", label: t("predictions") },
    { href: "/backtest", label: t("backtest") },
    { href: "/models", label: t("models") },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-white/80 backdrop-blur">
      <div className="flex w-full items-center gap-2 px-4 sm:px-6 lg:px-10 py-3">
        <Link
          href="/"
          className="flex items-center gap-2 whitespace-nowrap text-lg font-bold text-accent"
        >
          <span className="text-xl">🏇</span>
          <span>HKJC Quinella</span>
        </Link>

        <nav className="ml-4 hidden items-center gap-1 sm:ml-6 md:flex">
          {navItems.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-accent/10 text-accent"
                    : "text-muted hover:bg-gray-100 hover:text-foreground"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={toggleRegion}
            className="rounded-lg border border-border bg-white px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-gray-50"
            aria-label="Region"
          >
            {region === "hk" ? "🇭🇰 HK" : "🇬🇧 UK"}
          </button>
          <button
            onClick={toggle}
            className="rounded-lg border border-border bg-white px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-gray-50"
          >
            {lang === "zh" ? "EN" : "中文"}
          </button>
        </div>
      </div>
    </header>
  );
}
