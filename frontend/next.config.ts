import type { NextConfig } from "next";

// Use 127.0.0.1 explicitly in rewrites to avoid IPv6 resolution issues.
// Frontend client-side calls use relative paths (same-origin via rewrites).
const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Same-origin proxy so the browser never has to call :8000 directly
    // (CORS + private-network blocks in some embedded browsers).
    return [
      { source: "/api/chat", destination: `${apiBase}/api/chat` },
      // /api/approvals/* handled by app/api/approvals/[...path]/route.ts
      // (injects X-Operator-Key — do not rewrite directly to FastAPI)
      { source: "/health", destination: `${apiBase}/health` },
    ];
  },
};

export default nextConfig;
