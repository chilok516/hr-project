import type { Metadata, Viewport } from "next";
import "./globals.css";
import { LanguageProvider } from "@/lib/LanguageContext";
import Header from "@/components/Header";

export const metadata: Metadata = {
  title: "HKJC Quinella Prediction",
  description: "Systematic HKJC quinella betting prediction system",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-HK">
      <body className="font-sans">
        <LanguageProvider>
          <Header />
          <main className="px-4 sm:px-6 lg:px-10 py-6 sm:py-8">{children}</main>
        </LanguageProvider>
      </body>
    </html>
  );
}
