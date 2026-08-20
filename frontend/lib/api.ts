/**
 * API boundary for B-Mobile support chat.
 *
 * Contract: one non-streaming `POST /api/chat` → JSON `ChatResponse`.
 * FE epic: `mockPostChat` (latency + Path A/B/C via seed CSV).
 * Integration: swap the body below for
 *   fetch(`${NEXT_PUBLIC_API_BASE_URL}/api/chat`, { method: "POST", ... })
 * and drop the client KB / poller. Live answers come from crew `kb_search`.
 */
import { mockPostChat } from "./services/runService";
import type { ChatRequest, ChatResponse } from "./types";

export async function postChat(
  request: ChatRequest,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return mockPostChat(request, signal);
}
