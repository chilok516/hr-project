// Server-side proxy helper — forwards requests to the FastAPI service.

const API_URL = process.env.API_URL || "http://localhost:8000";

export async function proxyGet(path: string) {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    return new Response(JSON.stringify({ error: `upstream ${res.status}` }), {
      status: res.status,
      headers: { "content-type": "application/json" },
    });
  }
  const data = await res.json();
  return new Response(JSON.stringify(data), {
    headers: { "content-type": "application/json" },
  });
}
