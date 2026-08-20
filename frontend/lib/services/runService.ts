import { loadKbArticles } from "../kb";
import { mockTimeout, selectMockResponse } from "../mockResponse";
import type { ChatRequest, ChatResponse, RunInput } from "../types";

const STUB_LATENCY_MS = 1800;

function newId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function toRunInput(request: ChatRequest): RunInput {
  return {
    query: request.message,
    requestHuman: request.request_human,
    disclosureAcknowledged: Boolean(request.disclosure_acknowledged),
  };
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * FE-epic mock for the SAD single resolve path: one non-streaming ChatResponse.
 * Demo Path A/B still use `searchKb()` + `articles.csv`. Path C uses `request_human`.
 *
 * Integration replaces this with a real `fetch` to `POST /api/chat` and must not
 * keep a poller or treat client KB / `GET /api/kb` as the live answer source.
 */
export async function mockPostChat(
  request: ChatRequest,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const traceId = newId("trace");
  const input = toRunInput(request);

  try {
    await delay(STUB_LATENCY_MS, signal);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return mockTimeout(input, traceId);
    }
    throw err;
  }

  try {
    await loadKbArticles();
  } catch {
    // Path B if the CSV cannot be read; selectMockResponse still runs.
  }

  return selectMockResponse(input, traceId);
}
