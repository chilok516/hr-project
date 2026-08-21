"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

export type Region = "hk" | "uk";

interface RegionContextValue {
  region: Region;
  setRegion: (r: Region) => void;
  toggle: () => void;
}

const RegionContext = createContext<RegionContextValue | null>(null);

export function RegionProvider({ children }: { children: ReactNode }) {
  const [region, setRegion] = useState<Region>("hk");

  useEffect(() => {
    const saved = localStorage.getItem("region");
    if (saved === "hk" || saved === "uk") setRegion(saved);
  }, []);

  useEffect(() => {
    localStorage.setItem("region", region);
  }, [region]);

  const toggle = () => setRegion(region === "hk" ? "uk" : "hk");

  return (
    <RegionContext.Provider value={{ region, setRegion, toggle }}>
      {children}
    </RegionContext.Provider>
  );
}

export function useRegion() {
  const ctx = useContext(RegionContext);
  if (!ctx) throw new Error("useRegion must be used within RegionProvider");
  return ctx;
}
