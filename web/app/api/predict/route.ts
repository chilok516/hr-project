import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;
  const date = p.get("date") || "";
  const venue = p.get("venue") || "ST";
  const race_no = p.get("race_no") || "1";
  return proxyGet(
    `/predict?date=${encodeURIComponent(date)}&venue=${venue}&race_no=${race_no}`,
  );
}
