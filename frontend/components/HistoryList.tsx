"use client";

import type { HistoryEntry } from "@/lib/types";

type Props = {
  entries: HistoryEntry[];
  activeRunId: string | null;
  onSelect: (entry: HistoryEntry) => void;
};

export function HistoryList({ entries, activeRunId, onSelect }: Props) {
  return (
    <section aria-labelledby="history-heading" className="rounded-lg border border-line bg-white p-4 shadow-sm">
      <h2 id="history-heading" className="font-display text-lg font-semibold">
        History
      </h2>
      <p className="mt-1 text-sm text-muted">
        Session-only. Refreshing the tab clears this list (persisted history is Future Work).
      </p>
      {entries.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No completed runs in this session.</p>
      ) : (
        <ul className="mt-3 divide-y divide-line">
          {entries.map((entry) => (
            <li key={entry.runId}>
              <button
                type="button"
                onClick={() => onSelect(entry)}
                className={`w-full px-1 py-2 text-left text-sm hover:bg-canvas ${
                  activeRunId === entry.runId ? "bg-canvas" : ""
                }`}
              >
                <span className="font-medium">{entry.decision}</span>
                <span className="mt-0.5 block truncate text-muted">{entry.query}</span>
                <span className="mt-0.5 block font-mono text-xs text-muted">
                  {new Date(entry.completedAt).toLocaleString()}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
