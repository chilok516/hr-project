import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;
  const model = p.get("model") || "top2";
  const region = p.get("region") || "hk";
  return proxyGet(`/models/importance?model=${model}&region=${region}`);
}
