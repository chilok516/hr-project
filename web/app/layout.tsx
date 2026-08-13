import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "HKJC Quinella Prediction",
  description: "Systematic HKJC quinella betting prediction system",
};

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/predictions", label: "Predictions" },
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
          <div className="flex items-center gap-6 px-6 py-4 max-w-7xl mx-auto">
            <Link href="/" className="font-bold text-lg" style={{ color: "var(--accent)" }}>
              🏇 HKJC Quinella
            </Link>
            <nav className="flex gap-4 text-sm">
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
        <main className="max-w-7xl mx-auto px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
