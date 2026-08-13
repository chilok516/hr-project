"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { Lang, UI } from "@/lib/i18n";

interface LanguageContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  toggle: () => void;
  t: (key: string) => string;
  tf: (key: string, ...args: any[]) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("zh");

  useEffect(() => {
    const saved = localStorage.getItem("lang");
    if (saved === "en" || saved === "zh") setLang(saved);
  }, []);

  useEffect(() => {
    localStorage.setItem("lang", lang);
  }, [lang]);

  const t = (key: string): string => {
    const v = UI[lang][key];
    if (typeof v === "function") return (v as any)();
    return (v as string) ?? key;
  };
  const tf = (key: string, ...args: any[]): string => {
    const v = UI[lang][key];
    return typeof v === "function" ? (v as any)(...args) : ((v as string) ?? key);
  };

  const toggle = () => setLang(lang === "zh" ? "en" : "zh");

  return (
    <LanguageContext.Provider value={{ lang, setLang, toggle, t, tf }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLang() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLang must be used within LanguageProvider");
  return ctx;
}
