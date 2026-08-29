/**
 * Map backend agent ids to customer-facing StatusLine labels (ADR-15).
 */
import { STAGE_LABELS, type StageLabel } from "./fsm";

const AGENT_STAGE: Record<string, StageLabel> = {
  query_classifier: STAGE_LABELS[0],
  knowledge_retriever: STAGE_LABELS[1],
  response_specialist: STAGE_LABELS[2],
  escalation_manager: STAGE_LABELS[3],
};

export function stageLabelForAgent(agent: string, status: "running" | "completed"): StageLabel {
  const base = AGENT_STAGE[agent] ?? STAGE_LABELS[0];
  if (status === "running") return base;
  return base;
}

/** Advance label when an agent completes (show next stage if known). */
export function stageLabelAfterComplete(agent: string): StageLabel {
  const order = [
    "query_classifier",
    "knowledge_retriever",
    "response_specialist",
    "escalation_manager",
  ];
  const idx = order.indexOf(agent);
  if (idx >= 0 && idx + 1 < order.length) {
    return AGENT_STAGE[order[idx + 1]] ?? STAGE_LABELS[STAGE_LABELS.length - 1];
  }
  return STAGE_LABELS[STAGE_LABELS.length - 1];
}
