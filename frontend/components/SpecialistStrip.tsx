"use client";

import { useEffect, useState } from "react";
import { UI, outcomeLabel } from "@/lib/uiCopy";
import type { ChatResponse } from "@/lib/types";

type Props = {
  result: ChatResponse | null;
};

export function SpecialistStrip({ result }: Props) {
  const [stepsOpen, setStepsOpen] = useState(false);

  // When a new ChatResponse lands, show authoritative steps[] (ADR-15).
  useEffect(() => {
    if (result?.steps?.length) {
      setStepsOpen(true);
    } else {
      setStepsOpen(false);
    }
  }, [result?.trace_id, result?.steps?.length]);

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
      {result.approval ? (
        <div className="mt-3 rounded-md border border-line bg-canvas p-3 text-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Manager approval
          </p>
          <p className="mt-1 font-medium">
            {result.approval.status === "pending"
              ? UI.managerReview
              : result.approval.status === "approved"
                ? "Manager approved"
                : "Manager denied"}
          </p>
          <dl className="mt-2 grid gap-1 text-xs">
            <div>
              <dt className="text-muted">Ref</dt>
              <dd className="font-mono">{result.approval.id}</dd>
            </div>
            <div>
              <dt className="text-muted">Action</dt>
              <dd>{result.approval.action_kind}</dd>
            </div>
            <div>
              <dt className="text-muted">Account / order</dt>
              <dd className="font-mono">{result.approval.subject_id}</dd>
            </div>
            {result.approval.amount != null ? (
              <div>
                <dt className="text-muted">Amount</dt>
                <dd>${result.approval.amount.toFixed(2)}</dd>
              </div>
            ) : null}
            {typeof result.approval.context?.lookup_number === "number" ? (
              <div>
                <dt className="text-muted">Lookup #</dt>
                <dd className="font-mono">{String(result.approval.context.lookup_number)}</dd>
              </div>
            ) : null}
            {result.approval.status === "denied" && result.approval.operator_note ? (
              <div className="sm:col-span-2">
                <dt className="text-muted">Deny reason</dt>
                <dd>{result.approval.operator_note}</dd>
              </div>
            ) : null}
          </dl>
          <p className="mt-2 text-xs text-muted">
            Approve or deny in Telegram — this panel is read-only.
          </p>
        </div>
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
