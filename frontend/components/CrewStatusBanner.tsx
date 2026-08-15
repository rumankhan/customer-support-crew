import { CrewStatusMark } from "@/components/CrewStatusMark";
import {
  CREW_STATUS_BANNER,
  formatLastUpdated,
  type CrewStatus,
} from "@/lib/crewStatus";
import type { StageLabel } from "@/lib/fsm";

type Props = {
  status: CrewStatus;
  lastUpdated: Date;
  stageLabel: StageLabel;
};

export function CrewStatusBanner({ status, lastUpdated, stageLabel }: Props) {
  const detail =
    status === "running" ? ` — ${stageLabel}` : null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-3 py-2 ${CREW_STATUS_BANNER[status]}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <CrewStatusMark status={status} />
        {detail ? <span className="text-sm text-ink">{detail}</span> : null}
      </div>
      <p className="text-xs text-muted" suppressHydrationWarning>
        Last updated: {formatLastUpdated(lastUpdated)}
      </p>
    </div>
  );
}
