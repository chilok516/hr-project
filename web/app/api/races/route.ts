import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const date = req.nextUrl.searchParams.get("date") || "";
  return proxyGet(`/races?date=${encodeURIComponent(date)}`);
}
