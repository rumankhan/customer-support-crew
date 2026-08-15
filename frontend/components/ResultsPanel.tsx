"use client";

import { useState } from "react";
import type { ChatResponse } from "@/lib/types";

type Props = {
  result: ChatResponse | null;
  query: string;
};

export function ResultsPanel({ result, query }: Props) {
  const [stepsOpen, setStepsOpen] = useState(false);

  if (!result) {
    return (
      <section aria-labelledby="results-heading" className="rounded-lg border border-dashed border-line bg-white p-4">
        <h2 id="results-heading" className="font-display text-lg font-semibold">
          Results
        </h2>
        <p className="mt-2 text-sm text-muted">No run completed yet.</p>
      </section>
    );
  }

  const isEscalate = result.decision === "escalate" || result.error !== null;

  return (
    <section aria-labelledby="results-heading" className="space-y-3">
      <div className="rounded-lg border border-line bg-white p-4 shadow-sm">
        <h2 id="results-heading" className="font-display text-lg font-semibold">
          Results
        </h2>
        {query ? (
          <p className="mt-1 text-xs text-muted">Question: {query}</p>
        ) : null}
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{result.reply}</p>
        {result.sources_used.length > 0 ? (
          <ul className="mt-3 space-y-2">
            {result.sources_used.map((source) => (
              <li key={source.title} className="rounded-md bg-canvas px-3 py-2 text-sm">
                <strong>{source.title}</strong>
                <span className="mt-0.5 block text-muted">{source.snippet}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {isEscalate ? (
          <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm">
            This run needs a human. Talk-to-human is available (live agent chat is Future
            Work).
            {result.stub_ticket_id ? ` Stub ticket: ${result.stub_ticket_id}` : ""}
          </p>
        ) : null}
        {result.error ? (
          <p role="alert" className="mt-2 text-sm text-red-700">
            {result.error.code}: {result.error.message}
          </p>
        ) : null}
      </div>

      <aside className="rounded-lg border border-line bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Operator strip
        </h3>
        <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted">Decision</dt>
            <dd className="font-medium">{result.decision}</dd>
          </div>
          <div>
            <dt className="text-muted">Trace</dt>
            <dd className="font-mono text-xs">{result.trace_id}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-muted">Reason codes</dt>
            <dd>{result.reason_codes.join(", ") || "—"}</dd>
          </div>
        </dl>
        <button
          type="button"
          className="mt-3 text-sm text-accent underline"
          onClick={() => setStepsOpen((open) => !open)}
        >
          {stepsOpen ? "Hide" : "Show"} step summaries
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
          <pre className="mt-3 overflow-x-auto rounded-md bg-canvas p-3 text-xs">
            {JSON.stringify(result.packet, null, 2)}
          </pre>
        ) : null}
      </aside>
    </section>
  );
}
