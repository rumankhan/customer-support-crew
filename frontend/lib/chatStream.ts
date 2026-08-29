/**
 * SSE client for POST /api/chat/stream — crew progress + final ChatResponse.
 * Uses fetch + ReadableStream (EventSource is GET-only).
 */
import {
  failureEnvelope,
  isAbortError,
  normalizeChatResponse,
  timeoutEnvelope,
} from "./chatEnvelope";
import type { ChatRequest, ChatResponse } from "./types";

export type StreamStageEvent = {
  trace_id: string;
  agent: string;
  status: "running" | "completed";
  summary?: string;
};

export type StreamHandlers = {
  onStarted?: (traceId: string) => void;
  onStage?: (stage: StreamStageEvent) => void;
  onHeartbeat?: () => void;
  onApprovalRequired?: (payload: {
    approvalId: string;
    replyPending: string;
    response: ChatResponse | null;
  }) => void;
  onComplete: (response: ChatResponse) => void;
};

function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/** Split buffered SSE text into complete event blocks (handles CRLF from sse-starlette). */
function splitSseBlocks(buffer: string): { blocks: string[]; remainder: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const remainder = parts.pop() ?? "";
  return { blocks: parts.filter((part) => part.trim()), remainder };
}

function dispatchSseBlock(
  block: string,
  request: ChatRequest,
  handlers: StreamHandlers,
): boolean {
  const parsed = parseSseBlock(block.trim());
  if (!parsed) return false;

  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(parsed.data) as Record<string, unknown>;
  } catch {
    return false;
  }

  switch (parsed.event) {
    case "started":
      handlers.onStarted?.(String(payload.trace_id ?? ""));
      return false;
    case "stage":
      handlers.onStage?.({
        trace_id: String(payload.trace_id ?? ""),
        agent: String(payload.agent ?? ""),
        status: payload.status === "completed" ? "completed" : "running",
        summary: typeof payload.summary === "string" ? payload.summary : undefined,
      });
      return false;
    case "heartbeat":
      handlers.onHeartbeat?.();
      return false;
    case "approval_required": {
      const pending = normalizeChatResponse(payload.response);
      handlers.onApprovalRequired?.({
        approvalId: String(payload.approval_id ?? ""),
        replyPending: String(payload.reply_pending ?? ""),
        response: pending,
      });
      return false;
    }
    case "approval_decided":
    case "approval_timeout": {
      const envelope = normalizeChatResponse(payload.response);
      if (envelope) {
        handlers.onComplete(envelope);
        return true;
      }
      return false;
    }
    case "complete":
    case "error": {
      const raw = payload.response;
      const envelope = normalizeChatResponse(raw);
      if (envelope) {
        handlers.onComplete(envelope);
      } else {
        handlers.onComplete(
          failureEnvelope(
            request,
            "system_error",
            "Support returned an unexpected response. Please talk to a B-Mobile specialist.",
            ["system_error"],
          ),
        );
      }
      return true;
    }
    default:
      return false;
  }
}

export async function postChatStream(
  request: ChatRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      signal,
    });

    if (!res.ok || !res.body) {
      handlers.onComplete(
        failureEnvelope(
          request,
          "system_error",
          `Support is unavailable (HTTP ${res.status}). Please talk to a B-Mobile specialist.`,
          ["system_error"],
        ),
      );
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: !done });
      }

      const { blocks, remainder } = splitSseBlocks(buffer);
      buffer = remainder;

      for (const block of blocks) {
        if (dispatchSseBlock(block, request, handlers)) return;
      }

      if (done) {
        // Final chunk may omit trailing \n\n — parse any remaining event.
        if (buffer.trim() && dispatchSseBlock(buffer, request, handlers)) return;
        break;
      }
    }

    handlers.onComplete(
      failureEnvelope(
        request,
        "system_error",
        "Support ended the stream before a reply was ready. Please try again.",
        ["system_error"],
      ),
    );
  } catch (err) {
    if (isAbortError(err)) {
      handlers.onComplete(timeoutEnvelope(request));
      return;
    }
    handlers.onComplete(
      failureEnvelope(
        request,
        "system_error",
        "Could not reach support. Check that the API is running, then try again.",
        ["system_error"],
      ),
    );
  }
}
