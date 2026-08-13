import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const model = req.nextUrl.searchParams.get("model") || "top2";
  return proxyGet(`/models/importance?model=${model}`);
}
