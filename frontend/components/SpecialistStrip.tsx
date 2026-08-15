"use client";

import { useState } from "react";
import { UI, outcomeLabel } from "@/lib/uiCopy";
import type { ChatResponse } from "@/lib/types";

type Props = {
  result: ChatResponse | null;
};

export function SpecialistStrip({ result }: Props) {
  const [stepsOpen, setStepsOpen] = useState(false);
  if (!result) return null;

  return (
    <aside className="rounded-lg border border-line bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">
        For specialists
      </h3>
      <p className="mt-1 text-xs text-muted">
        Outcome, reasons, and handoff notes for grading and live support later.
      </p>
      <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">Outcome</dt>
          <dd className="font-medium">
            {outcomeLabel(result.decision)}{" "}
            <span className="font-normal text-muted">({result.decision})</span>
          </dd>
        </div>
        <div>
          <dt className="text-muted">Trace</dt>
          <dd className="font-mono text-xs">{result.trace_id}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted">Reasons</dt>
          <dd>{result.reason_codes.join(", ") || "—"}</dd>
        </div>
      </dl>
      <button
        type="button"
        className="mt-3 text-sm text-accent underline"
        onClick={() => setStepsOpen((open) => !open)}
      >
        {stepsOpen ? "Hide" : "Show"} how we handled this
      </button>
      {stepsOpen ? (
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
          {result.steps.map((step) => (
            <li key={step.agent}>
              <span className="font-medium">{step.agent}</span>: {step.summary}
            </li>
          ))}
        </ol>
      ) : null}
      {result.packet ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-muted">{UI.specialistNotes}</p>
          <pre className="mt-1 overflow-x-auto rounded-md bg-canvas p-3 text-xs">
            {JSON.stringify(result.packet, null, 2)}
          </pre>
        </div>
      ) : null}
    </aside>
  );
}
