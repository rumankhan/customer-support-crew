"use client";

import type { FormEvent } from "react";
import { CREW_STATUS_LABEL, type CrewStatus } from "@/lib/crewStatus";
import type { RunPhase } from "@/lib/types";

type Props = {
  query: string;
  requestHuman: boolean;
  phase: RunPhase;
  crewStatus: CrewStatus;
  error: string | null;
  onQueryChange: (value: string) => void;
  onRequestHumanChange: (value: boolean) => void;
  onSubmit: () => void;
};

export function InputsForm({
  query,
  requestHuman,
  phase,
  crewStatus,
  error,
  onQueryChange,
  onRequestHumanChange,
  onSubmit,
}: Props) {
  const disabled = phase === "running";
  const remaining = 4000 - query.length;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!disabled) onSubmit();
  }

  return (
    <section aria-labelledby="inputs-heading" className="rounded-lg border border-line bg-white p-4 shadow-sm">
      <h2 id="inputs-heading" className="font-display text-lg font-semibold">
        Inputs
      </h2>
      <p className="mt-1 text-sm text-muted">
        Describe the research question. The run uses mocked services until Integration
        wires the live crew.
      </p>
      <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
        <label className="block">
          <span className="text-sm font-medium">Research question</span>
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
            rows={4}
            placeholder="How do I reset my Acme Cloud password?"
            className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm disabled:opacity-60"
          />
          <span className="mt-1 block text-xs text-muted">{remaining} characters left</span>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={requestHuman}
            disabled={disabled}
            onChange={(e) => onRequestHumanChange(e.target.checked)}
          />
          Talk to a human (sets request_human for this run)
        </label>
        {error ? (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={disabled}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accentHover disabled:cursor-not-allowed disabled:opacity-60"
        >
          {crewStatus === "running"
            ? CREW_STATUS_LABEL.running
            : "Start research run"}
        </button>
      </form>
    </section>
  );
}
