import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "HKJC Quinella Prediction",
  description: "Systematic HKJC quinella betting prediction system",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

const navItems = [
  { href: "/", label: "Predictions" },
  { href: "/backtest", label: "Backtest" },
  { href: "/models", label: "Models" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
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
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-6">{children}</main>
      </body>
    </html>
  );
}
