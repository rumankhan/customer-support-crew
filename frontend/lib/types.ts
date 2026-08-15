export type RunPhase = "idle" | "running" | "done";

export type RunEvent = { type: "START" } | { type: "COMPLETE" } | { type: "RESET" };

export type SourceRef = {
  title: string;
  snippet: string;
};

export type StepSummary = {
  agent: string;
  summary: string;
};

export type EscalationPacket = {
  intent: string;
  urgency: string;
  customer_message: string;
  request_human: boolean;
  citations_attempted: SourceRef[];
  draft_reply: string;
  sentiment: "positive" | "neutral" | "negative";
  risk: "low" | "medium" | "high";
  reason_codes: string[];
  stub_ticket_id: string;
};

export type ChatError = {
  code: "llm_or_timeout" | "validation_error" | "kb_unavailable" | "system_error";
  message: string;
};

export type ChatResponse = {
  decision: "resolve" | "escalate";
  reply: string;
  sources_used: SourceRef[];
  sentiment: "positive" | "neutral" | "negative";
  risk: "low" | "medium" | "high";
  reason_codes: string[];
  steps: StepSummary[];
  trace_id: string;
  packet: EscalationPacket | null;
  stub_ticket_id: string | null;
  meta: {
    ai_disclosure: true;
    disclosure_acknowledged: boolean;
  };
  error: ChatError | null;
};

export type ChatRequest = {
  message: string;
  request_human: boolean;
  session_id?: string;
  disclosure_acknowledged?: boolean;
};

export type RunInput = {
  query: string;
  requestHuman: boolean;
  disclosureAcknowledged: boolean;
};

export type StartRunResponse = {
  runId: string;
};

export type RunStatusResponse = {
  status: "running" | "done";
  result?: ChatResponse;
};

export type HistoryEntry = {
  runId: string;
  query: string;
  decision: ChatResponse["decision"];
  completedAt: string;
  result: ChatResponse;
};
