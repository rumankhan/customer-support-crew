"use client";

import { CrewStatusMark } from "@/components/CrewStatusMark";
import { formatLastUpdated, type CrewStatus } from "@/lib/crewStatus";
import type { StageLabel } from "@/lib/fsm";
import type { RunPhase } from "@/lib/types";

type Props = {
  phase: RunPhase;
  crewStatus: CrewStatus;
  stageLabel: StageLabel;
  lastUpdated: Date;
  runId: string | null;
  onReset: () => void;
};

export function RunStatus({
  phase,
  crewStatus,
  stageLabel,
  lastUpdated,
  runId,
  onReset,
}: Props) {
  return (
    <section aria-labelledby="run-heading" className="rounded-lg border border-line bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="run-heading" className="font-display text-lg font-semibold">
          Run
        </h2>
        {phase === "done" ? (
          <button
            type="button"
            onClick={onReset}
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas"
          >
            New research
          </button>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <CrewStatusMark status={crewStatus} />
        {crewStatus === "running" ? (
          <span className="text-sm text-ink">— {stageLabel}</span>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-muted" suppressHydrationWarning>
        Last updated: {formatLastUpdated(lastUpdated)}
      </p>
      {runId ? (
        <p className="mt-1 font-mono text-xs text-muted">runId: {runId}</p>
      ) : null}
    </section>
  );
}
