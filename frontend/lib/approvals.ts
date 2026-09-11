import { normalizeChatResponse } from "./chatEnvelope";
import type { ApprovalRequest, ChatResponse } from "./types";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export async function fetchPendingApprovals(): Promise<ApprovalRequest[]> {
  return getJson("/api/approvals/pending");
}

export async function fetchApprovalHistory(): Promise<ApprovalRequest[]> {
  return getJson("/api/approvals/history");
}

export async function fetchLastResult(): Promise<ChatResponse | null> {
  const res = await fetch("/api/last-result", {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  const body: unknown = await res.json();
  return normalizeChatResponse(body);
}

export async function fetchApprovalStatus(
  approvalId: string,
): Promise<{
  id: string;
  status: "pending" | "approved" | "denied";
  operator_note: string | null;
  customer_reply: string | null;
}> {
  return getJson(`/api/approvals/${encodeURIComponent(approvalId)}/status`);
}
