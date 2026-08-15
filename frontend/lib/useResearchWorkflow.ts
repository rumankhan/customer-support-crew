"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { startRun, getRunStatus } from "./api";
import { deriveCrewStatus } from "./crewStatus";
import { STAGE_LABELS, transitionRunPhase, type StageLabel } from "./fsm";
import type { ChatResponse, HistoryEntry, RunInput, RunPhase } from "./types";

const POLL_MS = 400;
const STAGE_TICK_MS = 900;
const CLIENT_ABORT_MS = 55_000;

export function useResearchWorkflow() {
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [stageLabel, setStageLabel] = useState<StageLabel>(STAGE_LABELS[0]);
  const [error, setError] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [lastQuery, setLastQuery] = useState("");
  const [lastUpdated, setLastUpdated] = useState(() => new Date());
  const [crewFault, setCrewFault] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stageRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queryRef = useRef("");
  const settledRef = useRef(false);
  const busyRef = useRef(false);

  const touchUpdated = useCallback(() => {
    setLastUpdated(new Date());
  }, []);

  const clearTimers = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (stageRef.current) clearInterval(stageRef.current);
    if (abortRef.current) clearTimeout(abortRef.current);
    pollRef.current = null;
    stageRef.current = null;
    abortRef.current = null;
  }, []);

  useEffect(() => () => clearTimers(), [clearTimers]);

  const completeWith = useCallback(
    (next: ChatResponse, runId: string) => {
      if (settledRef.current) return;
      settledRef.current = true;
      busyRef.current = false;
      clearTimers();
      setResult(next);
      setPhase((p) => transitionRunPhase(p, { type: "COMPLETE" }));
      touchUpdated();
      setHistory((prev) => [
        {
          runId,
          query: queryRef.current,
          decision: next.decision,
          completedAt: new Date().toISOString(),
          result: next,
        },
        ...prev,
      ]);
    },
    [clearTimers, touchUpdated],
  );

  const beginPolling = useCallback(
    (runId: string) => {
      setStageLabel(STAGE_LABELS[0]);
      let stageIndex = 0;
      stageRef.current = setInterval(() => {
        stageIndex = Math.min(stageIndex + 1, STAGE_LABELS.length - 1);
        setStageLabel(STAGE_LABELS[stageIndex]);
        touchUpdated();
      }, STAGE_TICK_MS);

      const check = () => {
        void getRunStatus(runId).then((status) => {
          if (status.status === "done" && status.result) {
            completeWith(status.result, runId);
          }
        });
      };

      check();
      pollRef.current = setInterval(check, POLL_MS);

      abortRef.current = setTimeout(() => {
        void getRunStatus(runId).then((status) => {
          if (status.result) {
            completeWith(status.result, runId);
          }
        });
      }, CLIENT_ABORT_MS);
    },
    [completeWith, touchUpdated],
  );

  const submit = useCallback(
    async (input: RunInput) => {
      if (busyRef.current) return;
      const query = input.query.trim();
      if (!query) {
        setError("Enter a research question to start a run.");
        return;
      }
      if (query.length > 4000) {
        setError("Question must be 4000 characters or fewer.");
        return;
      }

      busyRef.current = true;
      setError(null);
      setCrewFault(false);
      settledRef.current = false;
      queryRef.current = query;
      setLastQuery(query);
      setPhase((p) => transitionRunPhase(p, { type: "START" }));
      touchUpdated();

      try {
        const { runId } = await startRun({ ...input, query });
        setActiveRunId(runId);
        beginPolling(runId);
      } catch (err) {
        busyRef.current = false;
        setCrewFault(true);
        setError(err instanceof Error ? err.message : "Could not start the run.");
        setPhase("idle");
        touchUpdated();
      }
    },
    [beginPolling, touchUpdated],
  );

  const reset = useCallback(() => {
    clearTimers();
    busyRef.current = false;
    setActiveRunId(null);
    setPhase((p) => transitionRunPhase(p, { type: "RESET" }));
    setStageLabel(STAGE_LABELS[0]);
    setError(null);
    setCrewFault(false);
    touchUpdated();
  }, [clearTimers, touchUpdated]);

  const showHistory = useCallback((entry: HistoryEntry) => {
    setResult(entry.result);
    setLastQuery(entry.query);
    setActiveRunId(entry.runId);
    touchUpdated();
  }, [touchUpdated]);

  return {
    phase,
    stageLabel,
    error,
    activeRunId,
    result,
    history,
    lastQuery,
    lastUpdated,
    crewStatus: deriveCrewStatus(phase, result, crewFault),
    submit,
    reset,
    showHistory,
  };
}
