import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;
  const result = p.get("result") || "all";
  const venue = p.get("venue") || "all";
  const search = p.get("search") || "";
  const min_div = p.get("min_div") || "";
  const limit = p.get("limit") || "500";
  const offset = p.get("offset") || "0";
  const region = p.get("region") || "hk";

  let path = `/backtest/bets?result=${result}&venue=${venue}&limit=${limit}&offset=${offset}&region=${region}`;
  if (search) path += `&search=${encodeURIComponent(search)}`;
  if (min_div) path += `&min_div=${min_div}`;

  return proxyGet(path);
}
