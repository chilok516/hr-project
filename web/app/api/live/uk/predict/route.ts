import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;
  const meeting = p.get("meeting") || "";
  const race_no = p.get("race_no") || "1";
  return proxyGet(`/live/uk/predict?meeting=${encodeURIComponent(meeting)}&race_no=${race_no}`);
}
