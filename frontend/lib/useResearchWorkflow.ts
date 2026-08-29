"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { postChatStream } from "./chatStream";
import { deriveCrewStatus } from "./crewStatus";
import { STAGE_LABELS, transitionRunPhase, type StageLabel } from "./fsm";
import { stageLabelAfterComplete, stageLabelForAgent } from "./stageFromAgent";
import { UI } from "./uiCopy";
import type { ChatRequest, ChatResponse, HistoryEntry, RunInput, RunPhase } from "./types";

const STAGE_TICK_MS = 900;
/** Crew timeout (180s) + HITL wait (300s) + buffer. */
const CLIENT_ABORT_MS = 500_000;
const HITL_POLL_MS = 2500;

function stageLabelFromSteps(steps: ChatResponse["steps"]): StageLabel {
  if (steps.length <= 0) return STAGE_LABELS[0];
  const index = Math.min(steps.length - 1, STAGE_LABELS.length - 1);
  return STAGE_LABELS[index];
}

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
  const [hitlPendingReply, setHitlPendingReply] = useState<string | null>(null);

  const stageRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const abortTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const queryRef = useRef("");
  const sessionIdRef = useRef<string | null>(null);
  const runGenerationRef = useRef(0);
  const busyRef = useRef(false);
  const sseActiveRef = useRef(false);

  const ensureSessionId = useCallback((): string => {
    if (!sessionIdRef.current) {
      sessionIdRef.current =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `session-${Date.now().toString(36)}`;
    }
    return sessionIdRef.current;
  }, []);

  const touchUpdated = useCallback(() => {
    setLastUpdated(new Date());
  }, []);

  const stopPoll = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }, []);

  const stopStageTimer = useCallback(() => {
    if (stageRef.current) clearInterval(stageRef.current);
    stageRef.current = null;
  }, []);

  const clearAbort = useCallback(() => {
    if (abortTimerRef.current) clearTimeout(abortTimerRef.current);
    abortTimerRef.current = null;
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  useEffect(
    () => () => {
      stopStageTimer();
      stopPoll();
      clearAbort();
    },
    [clearAbort, stopPoll, stopStageTimer],
  );

  /** Fallback optimistic animation until first SSE stage event arrives. */
  const startStageFallback = useCallback(() => {
    if (sseActiveRef.current) return;
    stopStageTimer();
    setStageLabel(STAGE_LABELS[0]);
    let stageIndex = 0;
    stageRef.current = setInterval(() => {
      if (sseActiveRef.current) {
        stopStageTimer();
        return;
      }
      stageIndex = Math.min(stageIndex + 1, STAGE_LABELS.length - 1);
      setStageLabel(STAGE_LABELS[stageIndex]);
      touchUpdated();
    }, STAGE_TICK_MS);
  }, [stopStageTimer, touchUpdated]);

  const completeWith = useCallback(
    (next: ChatResponse, runId: string, generation: number) => {
      if (generation !== runGenerationRef.current) return;
      if (!busyRef.current) return;
      busyRef.current = false;
      sseActiveRef.current = false;
      stopStageTimer();
      stopPoll();
      setHitlPendingReply(null);
      abortRef.current = null;
      if (abortTimerRef.current) clearTimeout(abortTimerRef.current);
      abortTimerRef.current = null;
      setStageLabel(stageLabelFromSteps(next.steps));
      setCrewFault(next.error != null);
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
    [stopPoll, stopStageTimer, touchUpdated],
  );

  const submit = useCallback(
    async (input: RunInput) => {
      if (busyRef.current) return;
      const query = input.query.trim();
      if (!query) {
        setError(UI.emptyError);
        return;
      }
      if (query.length > 4000) {
        setError(UI.tooLongError);
        return;
      }

      busyRef.current = true;
      sseActiveRef.current = false;
      setError(null);
      setCrewFault(false);
      setHitlPendingReply(null);
      setResult(null);
      const generation = ++runGenerationRef.current;
      queryRef.current = query;
      setLastQuery(query);
      setPhase((p) => transitionRunPhase(p, { type: "START" }));
      touchUpdated();
      startStageFallback();

      const controller = new AbortController();
      abortRef.current = controller;
      abortTimerRef.current = setTimeout(() => controller.abort(), CLIENT_ABORT_MS);
      const runId = `run-${Date.now().toString(36)}`;
      setActiveRunId(runId);

      const request: ChatRequest = {
        message: query,
        request_human: input.requestHuman,
        session_id: ensureSessionId(),
        disclosure_acknowledged: input.disclosureAcknowledged,
      };

      await postChatStream(
        request,
        {
          onStarted: () => {
            if (generation !== runGenerationRef.current) return;
            sseActiveRef.current = true;
            stopStageTimer();
          },
          onStage: (stage) => {
            if (generation !== runGenerationRef.current) return;
            sseActiveRef.current = true;
            stopStageTimer();
            if (stage.status === "running") {
              setStageLabel(stageLabelForAgent(stage.agent, "running"));
            } else {
              setStageLabel(stageLabelAfterComplete(stage.agent));
            }
            touchUpdated();
          },
          onApprovalRequired: (payload) => {
            if (generation !== runGenerationRef.current) return;
            stopStageTimer();
            setHitlPendingReply(
              payload.replyPending || UI.managerReview,
            );
            setStageLabel("Checking next steps");
            if (payload.response) {
              setResult(payload.response);
            }
            touchUpdated();
            if (payload.approvalId && !pollRef.current) {
              pollRef.current = setInterval(async () => {
                try {
                  const { fetchApprovalStatus } = await import("./approvals");
                  const status = await fetchApprovalStatus(payload.approvalId);
                  if (status.status === "pending") return;
                  stopPoll();
                  const base = payload.response;
                  if (!base) return;
                  const deniedNote = status.operator_note
                    ? ` Reason: ${status.operator_note}`
                    : "";
                  const fallbackReply =
                    status.status === "approved"
                      ? "Your request was approved by a manager."
                      : `Your request was not approved by a manager.${deniedNote}`;
                  completeWith(
                    {
                      ...base,
                      decision: "resolve",
                      reply: status.customer_reply || fallbackReply,
                      reason_codes:
                        status.status === "approved" ? ["hitl_approved"] : ["hitl_denied"],
                      approval: base.approval
                        ? {
                            ...base.approval,
                            status: status.status,
                            operator_note: status.operator_note,
                          }
                        : null,
                    },
                    runId,
                    generation,
                  );
                } catch {
                  /* keep waiting on SSE */
                }
              }, HITL_POLL_MS);
            }
          },
          onComplete: (response) => {
            completeWith(response, runId, generation);
          },
        },
        controller.signal,
      );
    },
    [completeWith, ensureSessionId, startStageFallback, stopPoll, stopStageTimer, touchUpdated],
  );

  const startNewConversation = useCallback(() => {
    runGenerationRef.current += 1;
    sseActiveRef.current = false;
    stopStageTimer();
    stopPoll();
    clearAbort();
    busyRef.current = false;
    queryRef.current = "";
    sessionIdRef.current = null;
    setActiveRunId(null);
    setResult(null);
    setHistory([]);
    setLastQuery("");
    setHitlPendingReply(null);
    setPhase((p) => (p === "idle" ? p : transitionRunPhase(p, { type: "RESET" })));
    setStageLabel(STAGE_LABELS[0]);
    setError(null);
    setCrewFault(false);
    touchUpdated();
  }, [clearAbort, stopPoll, stopStageTimer, touchUpdated]);

  return {
    phase,
    stageLabel,
    error,
    activeRunId,
    result,
    history,
    lastQuery,
    lastUpdated,
    hitlPendingReply,
    crewStatus: deriveCrewStatus(phase, result, crewFault),
    submit,
    startNewConversation,
  };
}
