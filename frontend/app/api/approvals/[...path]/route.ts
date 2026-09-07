/**
 * Proxy /api/approvals/* → FastAPI (pending, history, status, decide).
 * Injects X-Operator-Key from server-side OPERATOR_API_KEY (never NEXT_PUBLIC).
 */
const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001").replace(
  /\/$/,
  "",
);

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function operatorHeaders(req: Request): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const contentType = req.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;

  const key = (process.env.OPERATOR_API_KEY ?? "").trim();
  if (key) {
    headers["X-Operator-Key"] = key;
  }
  return headers;
}

async function proxy(req: Request, path: string[]) {
  // Reject path traversal segments
  if (path.some((p) => p === ".." || p.includes("\\") || p.includes("\0"))) {
    return new Response(JSON.stringify({ detail: "Invalid path" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const suffix = path.map(encodeURIComponent).join("/");
  const url = new URL(req.url);
  const dest = `${apiBase}/api/approvals/${suffix}${url.search}`;

  if (!(process.env.OPERATOR_API_KEY ?? "").trim()) {
    return new Response(
      JSON.stringify({
        detail: "OPERATOR_API_KEY is not configured on the Next.js server",
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }

  const init: RequestInit = {
    method: req.method,
    headers: operatorHeaders(req),
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  try {
    const upstream = await fetch(dest, init);
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

export async function GET(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function POST(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
