import { loadKbArticles } from "../kb";
import { mockTimeout, selectMockResponse } from "../mockResponse";
import type { RunInput, RunStatusResponse, StartRunResponse } from "../types";

type StubRun = {
  input: RunInput;
  startedAt: number;
  durationMs: number;
  traceId: string;
};

const STUB_STORE = new Map<string, StubRun>();
const STUB_LATENCY_MS = 1800;
const CLIENT_TIMEOUT_MS = 55_000;

function newId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Stub: starts a research run in memory. Integration will replace this
 * with POST /api/chat. Do not fetch a live backend from this module.
 */
export async function startRun(input: RunInput): Promise<StartRunResponse> {
  void loadKbArticles();
  const runId = newId("run");
  STUB_STORE.set(runId, {
    input,
    startedAt: Date.now(),
    durationMs: STUB_LATENCY_MS,
    traceId: newId("trace"),
  });
  return { runId };
}

/**
 * Stub: poll run status. Completes after a short delay with a mock ChatResponse.
 */
export async function getRunStatus(runId: string): Promise<RunStatusResponse> {
  const run = STUB_STORE.get(runId);
  if (!run) {
    return {
      status: "done",
      result: {
        decision: "escalate",
        reply: "We could not complete this request. Please talk to a human.",
        sources_used: [],
        sentiment: "neutral",
        risk: "medium",
        reason_codes: ["system_error"],
        steps: [],
        trace_id: newId("trace"),
        packet: null,
        stub_ticket_id: null,
        meta: { ai_disclosure: true, disclosure_acknowledged: false },
        error: { code: "system_error", message: `Unknown runId: ${runId}` },
      },
    };
  }

  const elapsed = Date.now() - run.startedAt;
  if (elapsed < run.durationMs) {
    return { status: "running" };
  }

  if (elapsed >= CLIENT_TIMEOUT_MS) {
    return { status: "done", result: mockTimeout(run.input, run.traceId) };
  }

  try {
    await loadKbArticles();
  } catch {
    // Path B if the CSV cannot be read; selectMockResponse still runs.
  }

  return {
    status: "done",
    result: selectMockResponse(run.input, run.traceId),
  };
}
