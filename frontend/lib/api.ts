/**
 * Live API boundary for B-Mobile support chat.
 *
 * Primary path: SSE POST /api/chat/stream → progress events + final ChatResponse.
 * Legacy: POST /api/chat (non-streaming JSON) for scripts and tests.
 * Retrieval is owned by crew `kb_search` on the backend — do not call
 * mock `GET /api/kb` or `searchKb()` for answers.
 *
 * Browser calls are same-origin (`/api/chat`, `/health`). Next.js rewrites
 * those paths to `NEXT_PUBLIC_API_BASE_URL` (see next.config.ts).
 */
import {
  failureEnvelope,
  formatFastApiValidation,
  isAbortError,
  networkEnvelope,
  normalizeChatResponse,
  timeoutEnvelope,
  validationEnvelope,
} from "./chatEnvelope";
import type { ChatRequest, ChatResponse } from "./types";

const DEFAULT_API_BASE = "http://localhost:8000";

/** Backend origin for docs/server; empty in the browser so fetch stays same-origin. */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return "";
  }
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE;
  return raw.replace(/\/$/, "");
}

export async function getHealth(signal?: AbortSignal): Promise<{ status: string }> {
  const res = await fetch(`${getApiBaseUrl()}/health`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    throw new Error(`Health check failed (${res.status})`);
  }
  const body: unknown = await res.json();
  if (!body || typeof body !== "object" || (body as { status?: unknown }).status !== "ok") {
    throw new Error("Health check returned an unexpected body");
  }
  return { status: "ok" };
}

export async function postChat(
  request: ChatRequest,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/api/chat`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      signal,
    });

    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      parsed = null;
    }

    const envelope = normalizeChatResponse(parsed);
    if (envelope) return envelope;

    if (res.status === 400 || res.status === 422) {
      return validationEnvelope(request, formatFastApiValidation(parsed));
    }

    return failureEnvelope(
      request,
      "system_error",
      `Support is unavailable (HTTP ${res.status}). Please talk to a B-Mobile specialist.`,
      ["system_error"],
    );
  } catch (err) {
    if (isAbortError(err)) {
      return timeoutEnvelope(request);
    }
    const detail =
      err instanceof Error
        ? "Could not reach support. Check that the API is running, then try again or talk to a specialist."
        : "Could not reach support. Please talk to a B-Mobile specialist.";
    return networkEnvelope(request, detail);
  }
}
