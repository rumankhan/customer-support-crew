"use client";

import { useEffect, useRef } from "react";
import { InputsForm } from "@/components/InputsForm";
import type { CrewStatus } from "@/lib/crewStatus";
import { UI } from "@/lib/uiCopy";
import type { ChatResponse, HistoryEntry, RunPhase } from "@/lib/types";

type Props = {
  history: HistoryEntry[];
  lastQuery: string;
  phase: RunPhase;
  stageLabel: string;
  query: string;
  requestHuman: boolean;
  crewStatus: CrewStatus;
  error: string | null;
  onQueryChange: (value: string) => void;
  onRequestHumanChange: (value: boolean) => void;
  onSubmit: () => void;
  onNewConversation?: () => void;
};

function AgentBubble({ result, pendingLabel }: { result?: ChatResponse; pendingLabel?: string }) {
  if (pendingLabel) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-canvas px-3 py-2 text-sm text-muted">
          <p className="text-xs font-medium text-ink">B-Mobile</p>
          <p className="mt-1">{pendingLabel}…</p>
        </div>
      </div>
    );
  }
  if (!result) return null;
  const isEscalate = result.decision === "escalate" || result.error !== null;
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-canvas px-3 py-2 text-sm leading-6 text-ink">
        <p className="text-xs font-medium text-muted">B-Mobile</p>
        <p className="mt-1 whitespace-pre-wrap">{result.reply}</p>
        {result.sources_used.length > 0 ? (
          <div className="mt-2 border-t border-line pt-2">
            <p className="text-xs font-medium text-muted">{UI.sourcesHeading}</p>
            <ul className="mt-1 space-y-1">
              {result.sources_used.map((source) => (
                <li key={source.title} className="text-xs text-muted">
                  <span className="font-medium text-ink">{source.title}</span>
                  {" — "}
                  {source.snippet}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {isEscalate ? (
          <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs">
            {UI.escalateNotice}
            {result.stub_ticket_id ? ` ${UI.reference}: ${result.stub_ticket_id}` : ""}
          </p>
        ) : null}
        {result.error ? (
          <p role="alert" className="mt-2 text-xs text-red-700">
            {result.error.message}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function ChatWindow({
  history,
  lastQuery,
  phase,
  stageLabel,
  query,
  requestHuman,
  crewStatus,
  error,
  onQueryChange,
  onRequestHumanChange,
  onSubmit,
  onNewConversation,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const turns = [...history].reverse();
  const pending =
    phase === "running" && lastQuery
      ? { query: lastQuery, label: stageLabel }
      : null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length, phase, lastQuery, stageLabel]);

  return (
    <section
      aria-labelledby="chat-heading"
      className="flex min-h-[28rem] flex-col overflow-hidden rounded-lg border border-line bg-white shadow-sm"
    >
      <header className="border-b border-line px-4 py-3">
        <h2 id="chat-heading" className="font-display text-lg font-semibold">
          {UI.chatHeading}
        </h2>
        <p className="text-xs text-muted">{UI.chatHelp}</p>
      </header>

      <div className="flex min-h-[16rem] flex-1 flex-col gap-3 overflow-y-auto bg-[#faf8f4] px-4 py-4">
        {turns.length === 0 && !pending ? (
          <p className="m-auto max-w-sm text-center text-sm text-muted">{UI.chatEmpty}</p>
        ) : (
          <>
            {turns.map((entry) => (
              <div key={entry.runId} className="space-y-2">
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-3 py-2 text-sm leading-6 text-white">
                    <p className="text-xs font-medium text-blue-100">You</p>
                    <p className="mt-1 whitespace-pre-wrap">{entry.query}</p>
                  </div>
                </div>
                <AgentBubble result={entry.result} />
              </div>
            ))}
            {pending ? (
              <div className="space-y-2">
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-3 py-2 text-sm leading-6 text-white">
                    <p className="text-xs font-medium text-blue-100">You</p>
                    <p className="mt-1 whitespace-pre-wrap">{pending.query}</p>
                  </div>
                </div>
                <AgentBubble pendingLabel={pending.label} />
              </div>
            ) : null}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      <div className="border-t border-line p-3">
        <InputsForm
          compact
          query={query}
          requestHuman={requestHuman}
          phase={phase}
          crewStatus={crewStatus}
          error={error}
          onQueryChange={onQueryChange}
          onRequestHumanChange={onRequestHumanChange}
          onSubmit={onSubmit}
          onNewConversation={onNewConversation}
          canStartNewConversation={Boolean(onNewConversation && (turns.length > 0 || pending))}
        />
      </div>
    </section>
  );
}
