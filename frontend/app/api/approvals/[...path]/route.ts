/**
 * Proxy /api/approvals/* → FastAPI (pending, history, status, decide).
 */
const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001").replace(
  /\/$/,
  "",
);

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(req: Request, path: string[]) {
  const suffix = path.join("/");
  const url = new URL(req.url);
  const dest = `${apiBase}/api/approvals/${suffix}${url.search}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  const contentType = req.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  try {
    const upstream = await fetch(dest, init);
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
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
