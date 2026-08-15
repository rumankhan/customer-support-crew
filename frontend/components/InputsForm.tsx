"use client";

import type { FormEvent } from "react";
import type { CrewStatus } from "@/lib/crewStatus";
import { UI } from "@/lib/uiCopy";
import type { RunPhase } from "@/lib/types";

type Props = {
  query: string;
  requestHuman: boolean;
  phase: RunPhase;
  crewStatus: CrewStatus;
  error: string | null;
  compact?: boolean;
  canStartNewConversation?: boolean;
  onQueryChange: (value: string) => void;
  onRequestHumanChange: (value: boolean) => void;
  onSubmit: () => void;
  onNewConversation?: () => void;
};

export function InputsForm({
  query,
  requestHuman,
  phase,
  crewStatus,
  error,
  compact = false,
  canStartNewConversation = false,
  onQueryChange,
  onRequestHumanChange,
  onSubmit,
  onNewConversation,
}: Props) {
  const disabled = phase === "running";
  const remaining = 4000 - query.length;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!disabled) onSubmit();
  }

  return (
    <div className={compact ? "" : "rounded-lg border border-line bg-white p-4 shadow-sm"}>
      {compact ? null : (
        <>
          <h2 id="inputs-heading" className="font-display text-lg font-semibold">
            {UI.askHeading}
          </h2>
          <p className="mt-1 text-sm text-muted">{UI.askHelp}</p>
        </>
      )}
      <form
        className={compact ? "space-y-3" : "mt-4 space-y-4"}
        onSubmit={handleSubmit}
        aria-labelledby={compact ? undefined : "inputs-heading"}
      >
        <label className="block">
          <span className={compact ? "sr-only" : "text-sm font-medium"}>{UI.questionLabel}</span>
          <textarea
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!disabled) onSubmit();
              }
            }}
            disabled={disabled}
            maxLength={4000}
            rows={compact ? 2 : 4}
            placeholder="How do I reset my B-Mobile My Account PIN?"
            className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm disabled:opacity-60"
          />
          <span className="mt-1 block text-xs text-muted">{remaining} characters left</span>
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={requestHuman}
              disabled={disabled}
              onChange={(e) => onRequestHumanChange(e.target.checked)}
            />
            {UI.talkToHuman}
          </label>
          <div className="flex flex-wrap items-center gap-2">
            {canStartNewConversation && onNewConversation ? (
              <button
                type="button"
                onClick={onNewConversation}
                className="rounded-md border border-line px-3 py-2 text-sm hover:bg-canvas"
              >
                {UI.newConversation}
              </button>
            ) : null}
            <button
              type="submit"
              disabled={disabled}
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accentHover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {crewStatus === "running" ? UI.sending : UI.send}
            </button>
          </div>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        ) : null}
      </form>
    </div>
  );
}
