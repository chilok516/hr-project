import { proxyGet } from "@/lib/proxy";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;
  const name = p.get("name") || "";
  const date = p.get("date") || "";
  const distance = p.get("distance") || "0";
  const venue = p.get("venue") || "";
  const going = p.get("going") || "";
  const region = p.get("region") || "hk";
  return proxyGet(
    `/horse/form?name=${encodeURIComponent(name)}&date=${encodeURIComponent(date)}&distance=${distance}&venue=${venue}&going=${encodeURIComponent(going)}&region=${region}`,
  );
}
