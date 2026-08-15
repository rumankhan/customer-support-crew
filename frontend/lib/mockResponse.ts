import { searchKb } from "./kb";
import type { ChatResponse, RunInput } from "./types";

const RESEARCH_STEPS: ChatResponse["steps"] = [
  { agent: "query_classifier", summary: "Classified B-Mobile intent and urgency" },
  { agent: "knowledge_retriever", summary: "Searched the B-Mobile help articles" },
  { agent: "response_specialist", summary: "Drafted a grounded reply or refused" },
  { agent: "escalation_manager", summary: "Scored risk and chose resolve vs escalate" },
];

function baseMeta(input: RunInput): ChatResponse["meta"] {
  return {
    ai_disclosure: true,
    disclosure_acknowledged: input.disclosureAcknowledged,
  };
}

export function mockResolveFromKb(input: RunInput, traceId: string): ChatResponse | null {
  const hit = searchKb(input.query);
  if (!hit) return null;
  return {
    decision: "resolve",
    reply: hit.article.body,
    sources_used: [{ title: hit.article.title, snippet: hit.snippet }],
    sentiment: "neutral",
    risk: "low",
    reason_codes: ["grounded_kb_hit"],
    steps: RESEARCH_STEPS,
    trace_id: traceId,
    packet: null,
    stub_ticket_id: null,
    meta: baseMeta(input),
    error: null,
  };
}

export function mockEscalateUnknownTopic(input: RunInput, traceId: string): ChatResponse {
  const stub = `STUB-${traceId.slice(0, 8).toUpperCase()}`;
  return {
    decision: "escalate",
    reply:
      "I don’t have that in the B-Mobile help articles, so I am sending this to a human specialist with the context I collected.",
    sources_used: [],
    sentiment: "neutral",
    risk: "medium",
    reason_codes: ["retrieval_gap", "refused"],
    steps: RESEARCH_STEPS,
    trace_id: traceId,
    packet: {
      intent: "unknown_product_claim",
      urgency: "medium",
      customer_message: input.query,
      request_human: input.requestHuman,
      citations_attempted: [],
      draft_reply: "I don’t have that in the B-Mobile help articles.",
      sentiment: "neutral",
      risk: "medium",
      reason_codes: ["retrieval_gap", "refused"],
      stub_ticket_id: stub,
    },
    stub_ticket_id: stub,
    meta: baseMeta(input),
    error: null,
  };
}

export function mockEscalateRequestHuman(input: RunInput, traceId: string): ChatResponse {
  const stub = `STUB-${traceId.slice(0, 8).toUpperCase()}`;
  return {
    decision: "escalate",
    reply: "Connecting you with a B-Mobile specialist. Your account context is attached.",
    sources_used: [],
    sentiment: "negative",
    risk: "medium",
    reason_codes: ["request_human"],
    steps: RESEARCH_STEPS,
    trace_id: traceId,
    packet: {
      intent: "human_requested",
      urgency: "high",
      customer_message: input.query,
      request_human: true,
      citations_attempted: [],
      draft_reply: "",
      sentiment: "negative",
      risk: "medium",
      reason_codes: ["request_human"],
      stub_ticket_id: stub,
    },
    stub_ticket_id: stub,
    meta: baseMeta(input),
    error: null,
  };
}

export function mockTimeout(input: RunInput, traceId: string): ChatResponse {
  const stub = `STUB-${traceId.slice(0, 8).toUpperCase()}`;
  return {
    decision: "escalate",
    reply: "We could not complete this request. Please talk to a B-Mobile specialist.",
    sources_used: [],
    sentiment: "neutral",
    risk: "medium",
    reason_codes: ["timeout"],
    steps: RESEARCH_STEPS.slice(0, 1),
    trace_id: traceId,
    packet: {
      intent: "",
      urgency: "",
      customer_message: input.query,
      request_human: input.requestHuman,
      citations_attempted: [],
      draft_reply: "",
      sentiment: "neutral",
      risk: "medium",
      reason_codes: ["timeout"],
      stub_ticket_id: stub,
    },
    stub_ticket_id: stub,
    meta: baseMeta(input),
    error: {
      code: "llm_or_timeout",
      message: "Client wait exceeded 55s (stub timeout).",
    },
  };
}

export function selectMockResponse(input: RunInput, traceId: string): ChatResponse {
  if (input.requestHuman) {
    return mockEscalateRequestHuman(input, traceId);
  }
  return mockResolveFromKb(input, traceId) ?? mockEscalateUnknownTopic(input, traceId);
}
