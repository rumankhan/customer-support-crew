/**
 * API boundary for the B-Mobile support run (Critical Research Workflow).
 *
 * FE epic: re-export stubs. Integration epic: swap implementations to
 * fetch(`${NEXT_PUBLIC_API_BASE_URL}/api/chat`) — do not do that here.
 */
export { getRunStatus, startRun } from "./services/runService";
