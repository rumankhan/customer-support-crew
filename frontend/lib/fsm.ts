import type { RunEvent, RunPhase } from "./types";

/**
 * Critical Research Workflow FSM: idle → running → done.
 * Illegal transitions are no-ops so the UI cannot skip states.
 */
export function transitionRunPhase(phase: RunPhase, event: RunEvent): RunPhase {
  switch (phase) {
    case "idle":
      return event.type === "START" ? "running" : phase;
    case "running":
      if (event.type === "COMPLETE") return "done";
      if (event.type === "RESET") return "idle";
      return phase;
    case "done":
      if (event.type === "RESET") return "idle";
      if (event.type === "START") return "running";
      return phase;
    default:
      return phase;
  }
}

export const STAGE_LABELS = [
  "Understanding your question",
  "Searching help articles",
  "Writing a reply",
  "Checking next steps",
] as const;

export type StageLabel = (typeof STAGE_LABELS)[number];
