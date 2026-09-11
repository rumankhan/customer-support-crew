import type { ChatError, ChatRequest, ChatResponse, EscalationPacket } from "./types";

export const SAFE_REPLY =
  "We could not complete this request. Please talk to a B-Mobile specialist.";

const ERROR_CODES: ChatError["code"][] = [
  "llm_or_timeout",
  "validation_error",
  "kb_unavailable",
  "system_error",
];

function newTraceId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `trace-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function newStubId(): string {
  const hex =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 8).toUpperCase()
      : Date.now().toString(16).slice(-8).toUpperCase();
  return `STUB-${hex}`;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function asSourceList(value: unknown): ChatResponse["sources_used"] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      const title = asString(row.title);
      if (!title) return null;
      return { title, snippet: asString(row.snippet) };
    })
    .filter((item): item is ChatResponse["sources_used"][number] => item !== null);
}

function asSteps(value: unknown): ChatResponse["steps"] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      const agent = asString(row.agent);
      if (!agent) return null;
      return { agent, summary: asString(row.summary) };
    })
    .filter((item): item is ChatResponse["steps"][number] => item !== null);
}

function asErrorCode(value: unknown): ChatError["code"] {
  if (typeof value === "string" && ERROR_CODES.includes(value as ChatError["code"])) {
    return value as ChatError["code"];
  }
  return "system_error";
}

function asSentiment(value: unknown): ChatResponse["sentiment"] {
  return value === "positive" || value === "negative" ? value : "neutral";
}

function asRisk(value: unknown): ChatResponse["risk"] {
  return value === "low" || value === "high" ? value : "medium";
}

function asDecision(value: unknown): ChatResponse["decision"] {
  if (value === "resolve" || value === "pending_approval") return value;
  return "escalate";
}

function asApproval(value: unknown): ChatResponse["approval"] {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const id = asString(row.id);
  if (!id) return null;
  const status = row.status;
  const amount = row.amount;
  return {
    id,
    action_kind: asString(row.action_kind),
    subject_id: asString(row.subject_id),
    amount: typeof amount === "number" ? amount : null,
    reason: asString(row.reason),
    status: status === "approved" || status === "denied" ? status : "pending",
    operator_note: typeof row.operator_note === "string" ? row.operator_note : null,
    context:
      row.context && typeof row.context === "object"
        ? (row.context as Record<string, unknown>)
        : {},
    created_at: asString(row.created_at),
    decided_at: typeof row.decided_at === "string" ? row.decided_at : null,
    decided_by: typeof row.decided_by === "string" ? row.decided_by : null,
    trace_id: typeof row.trace_id === "string" ? row.trace_id : null,
    crew_trace_url:
      typeof row.crew_trace_url === "string" &&
      row.crew_trace_url.startsWith("https://app.crewai.com/")
        ? row.crew_trace_url
        : null,
  };
}

function asPacket(value: unknown): EscalationPacket | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const stub = asString(row.stub_ticket_id);
  if (!stub) return null;
  const urgency = row.urgency;
  return {
    intent: asString(row.intent),
    urgency: urgency === "low" || urgency === "high" ? urgency : "medium",
    customer_message: asString(row.customer_message),
    request_human: Boolean(row.request_human),
    citations_attempted: asSourceList(row.citations_attempted),
    draft_reply: asString(row.draft_reply),
    sentiment: asSentiment(row.sentiment),
    risk: asRisk(row.risk),
    reason_codes: asStringList(row.reason_codes),
    stub_ticket_id: stub,
  };
}

/** Coerce a JSON body into the SAD ChatResponse envelope (ignore extra fields). */
export function normalizeChatResponse(raw: unknown): ChatResponse | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  if (typeof row.reply !== "string" || typeof row.trace_id !== "string") return null;

  const metaRaw =
    row.meta && typeof row.meta === "object" ? (row.meta as Record<string, unknown>) : {};
  const errorRaw =
    row.error && typeof row.error === "object" ? (row.error as Record<string, unknown>) : null;

  return {
    decision: asDecision(row.decision),
    reply: row.reply,
    sources_used: asSourceList(row.sources_used),
    sentiment: asSentiment(row.sentiment),
    risk: asRisk(row.risk),
    reason_codes: asStringList(row.reason_codes),
    steps: asSteps(row.steps),
    trace_id: row.trace_id,
    packet: asPacket(row.packet),
    stub_ticket_id: typeof row.stub_ticket_id === "string" ? row.stub_ticket_id : null,
    approval: asApproval(row.approval),
    crew_trace_url:
      typeof row.crew_trace_url === "string" &&
      row.crew_trace_url.startsWith("https://app.crewai.com/")
        ? row.crew_trace_url
        : null,
    meta: {
      ai_disclosure: true,
      disclosure_acknowledged: Boolean(metaRaw.disclosure_acknowledged),
    },
    error: errorRaw
      ? {
          code: asErrorCode(errorRaw.code),
          message: asString(errorRaw.message, SAFE_REPLY),
        }
      : null,
  };
}

export function failureEnvelope(
  request: ChatRequest,
  code: ChatError["code"],
  message: string,
  reasonCodes: string[],
): ChatResponse {
  const stub = newStubId();
  return {
    decision: "escalate",
    reply: SAFE_REPLY,
    sources_used: [],
    sentiment: "neutral",
    risk: "medium",
    reason_codes: reasonCodes,
    steps: [],
    trace_id: newTraceId(),
    packet: {
      intent: "",
      urgency: "medium",
      customer_message: request.message,
      request_human: request.request_human,
      citations_attempted: [],
      draft_reply: "",
      sentiment: "neutral",
      risk: "medium",
      reason_codes: reasonCodes,
      stub_ticket_id: stub,
    },
    stub_ticket_id: stub,
    approval: null,
    meta: {
      ai_disclosure: true,
      disclosure_acknowledged: Boolean(request.disclosure_acknowledged),
    },
    error: { code, message },
  };
}

export function timeoutEnvelope(request: ChatRequest): ChatResponse {
  return failureEnvelope(
    request,
    "llm_or_timeout",
    "The request took too long. Please talk to a B-Mobile specialist.",
    ["timeout"],
  );
}

export function networkEnvelope(request: ChatRequest, detail: string): ChatResponse {
  return failureEnvelope(
    request,
    "system_error",
    detail || "Could not reach support. Please talk to a B-Mobile specialist.",
    ["system_error"],
  );
}

export function validationEnvelope(request: ChatRequest, detail: string): ChatResponse {
  return failureEnvelope(request, "validation_error", detail, ["system_error"]);
}

export function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

export function formatFastApiValidation(body: unknown): string {
  if (!body || typeof body !== "object") return "The question could not be sent.";
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object") {
    const first = detail[0] as Record<string, unknown>;
    return asString(first.msg, "The question could not be sent.");
  }
  return "The question could not be sent.";
}
