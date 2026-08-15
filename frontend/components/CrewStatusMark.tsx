import {
  CREW_STATUS_DOT,
  CREW_STATUS_LABEL,
  CREW_STATUS_PILL,
  type CrewStatus,
} from "@/lib/crewStatus";

type Props = {
  status: CrewStatus;
};

export function CrewStatusMark({ status }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-semibold ${CREW_STATUS_PILL[status]}`}
    >
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${CREW_STATUS_DOT[status]}`}
        aria-hidden
      />
      {CREW_STATUS_LABEL[status]}
    </span>
  );
}
