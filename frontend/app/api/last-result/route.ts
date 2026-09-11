/**
 * Proxy GET /api/last-result → FastAPI.
 * Injects X-Operator-Key from server-side OPERATOR_API_KEY (never NEXT_PUBLIC).
 */
const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001").replace(
  /\/$/,
  "",
);

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const key = (process.env.OPERATOR_API_KEY ?? "").trim();
  if (!key) {
    return new Response(
      JSON.stringify({
        detail: "OPERATOR_API_KEY is not configured on the Next.js server",
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }

  try {
    const upstream = await fetch(`${apiBase}/api/last-result`, {
      headers: {
        Accept: "application/json",
        "X-Operator-Key": key,
      },
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return new Response("Upstream unavailable", { status: 502 });
  }
}
