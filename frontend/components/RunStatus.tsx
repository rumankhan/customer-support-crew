"use client";

import { CrewStatusMark } from "@/components/CrewStatusMark";
import { formatLastUpdated, type CrewStatus } from "@/lib/crewStatus";
import type { StageLabel } from "@/lib/fsm";
import { UI } from "@/lib/uiCopy";

type Props = {
  crewStatus: CrewStatus;
  stageLabel: StageLabel;
  lastUpdated: Date;
  runId: string | null;
};

export function RunStatus({
  crewStatus,
  stageLabel,
  lastUpdated,
  runId,
}: Props) {
  return (
    <section aria-labelledby="run-heading" className="rounded-lg border border-line bg-white p-4 shadow-sm">
      <h2 id="run-heading" className="font-display text-lg font-semibold">
        {UI.statusHeading}
      </h2>
      <div className="mt-3 flex flex-wrap items-center gap-2" role="status" aria-live="polite">
        <CrewStatusMark status={crewStatus} />
        {crewStatus === "running" ? (
          <span className="text-sm text-ink">— {stageLabel}</span>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-muted" suppressHydrationWarning>
        {UI.lastUpdated}: {formatLastUpdated(lastUpdated)}
      </p>
      {runId ? (
        <p className="mt-1 font-mono text-xs text-muted">
          {UI.reference}: {runId}
        </p>
      ) : null}
    </section>
  );
}
