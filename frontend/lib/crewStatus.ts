import type { ChatResponse, RunPhase } from "./types";
import { CREW_STATUS_LABEL } from "./uiCopy";

export type CrewStatus = "idle" | "running" | "done" | "error";

export { CREW_STATUS_LABEL };

/** Pill surface: gray idle, blue running, green done, red error. */
export const CREW_STATUS_PILL: Record<CrewStatus, string> = {
  idle: "bg-stone-200 text-stone-700",
  running: "bg-accent text-white",
  done: "bg-emerald-600 text-white",
  error: "bg-red-600 text-white",
};

export const CREW_STATUS_DOT: Record<CrewStatus, string> = {
  idle: "bg-stone-500",
  running: "bg-white",
  done: "bg-white",
  error: "bg-white",
};

export const CREW_STATUS_BANNER: Record<CrewStatus, string> = {
  idle: "border-stone-300 bg-stone-100",
  running: "border-blue-200 bg-blue-50",
  done: "border-emerald-200 bg-emerald-50",
  error: "border-red-200 bg-red-50",
};

/**
 * Display status from the run FSM. `error` is overlay only (not an FSM state):
 * crew start failure while idle, or a completed ChatResponse with error.
 */
export function deriveCrewStatus(
  phase: RunPhase,
  result: ChatResponse | null,
  crewFault: boolean,
): CrewStatus {
  if (phase === "running") return "running";
  if (phase === "idle") return crewFault ? "error" : "idle";
  return result?.error ? "error" : "done";
}

export function formatLastUpdated(at: Date): string {
  return at.toLocaleString();
}
