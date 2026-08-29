"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { fetchApprovalHistory, fetchPendingApprovals } from "@/lib/approvals";
import type { ApprovalRequest } from "@/lib/types";

function formatAmount(amount: number | null): string {
  return amount == null ? "—" : `$${amount.toFixed(2)}`;
}

function ApprovalCard({ item }: { item: ApprovalRequest }) {
  const statusLabel =
    item.status === "pending"
      ? "Pending"
      : item.status === "approved"
        ? "Approved"
        : "Denied";
  return (
    <article className="rounded-lg border border-line bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium">
          {item.action_kind.replace(/_/g, " ")}
        </h3>
        <span className="text-xs uppercase tracking-wide text-muted">{statusLabel}</span>
      </div>
      <dl className="mt-2 grid gap-1 text-sm">
        <div>
          <dt className="text-muted">Ref</dt>
          <dd className="font-mono text-xs">{item.id}</dd>
        </div>
        <div>
          <dt className="text-muted">Account / order</dt>
          <dd className="font-mono">{item.subject_id}</dd>
        </div>
        <div>
          <dt className="text-muted">Amount</dt>
          <dd>{formatAmount(item.amount)}</dd>
        </div>
        {item.reason ? (
          <div>
            <dt className="text-muted">Customer</dt>
            <dd className="text-sm">{item.reason}</dd>
          </div>
        ) : null}
        {item.operator_note ? (
          <div>
            <dt className="text-muted">Manager note</dt>
            <dd>{item.operator_note}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}

export default function OperatorPage() {
  const [pending, setPending] = useState<ApprovalRequest[]>([]);
  const [history, setHistory] = useState<ApprovalRequest[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextPending, nextHistory] = await Promise.all([
        fetchPendingApprovals(),
        fetchApprovalHistory(),
      ]);
      setPending(nextPending);
      setHistory(nextHistory);
      setError(null);
    } catch {
      setError("Could not load approvals. Is the backend running?");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => {
      void refresh();
    }, 2500);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          B-Mobile Support
        </p>
        <h1 className="mt-1 font-display text-3xl font-semibold">Manager queue</h1>
        <p className="mt-2 text-sm text-muted">
          Read-only projector view. Approve or deny in Telegram — this page does not
          take actions.
        </p>
        <p className="mt-2 text-sm">
          <Link className="text-accent underline" href="/">
            Back to customer chat
          </Link>
        </p>
      </header>

      {error ? (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
          {error}
        </p>
      ) : null}

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Pending ({pending.length})
        </h2>
        <div className="mt-3 grid gap-3">
          {pending.length === 0 ? (
            <p className="text-sm text-muted">No pending approvals.</p>
          ) : (
            pending.map((item) => <ApprovalCard key={item.id} item={item} />)
          )}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Recent decisions
        </h2>
        <div className="mt-3 grid gap-3">
          {history.length === 0 ? (
            <p className="text-sm text-muted">No decisions yet.</p>
          ) : (
            history.map((item) => <ApprovalCard key={item.id} item={item} />)
          )}
        </div>
      </section>
    </main>
  );
}
