import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const region = req.nextUrl.searchParams.get("region") || "hk";
  return proxyGet(`/backtest/summary?region=${region}`);
}
