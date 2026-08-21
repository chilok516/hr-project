import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const date = req.nextUrl.searchParams.get("date") || "";
  const region = req.nextUrl.searchParams.get("region") || "hk";
  return proxyGet(`/races?date=${encodeURIComponent(date)}&region=${region}`);
}
