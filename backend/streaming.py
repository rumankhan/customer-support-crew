"""
SSE streaming for POST /api/chat/stream — crew progress + final ChatResponse.
Extends base flow with HITL approval_required / approval_decided events.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import AsyncIterator, Optional

from backend.chat_service import (
    DEFAULT_TIMEOUT_SECONDS,
    error_response,
    map_to_response,
    run_crew_sync,
    write_prompt_trace,
)
from backend.crew import CustomerSupportCrew
from backend.models import ChatRequest

HITL_TIMEOUT_SECONDS = int(os.getenv("HITL_TIMEOUT_SECONDS", "300"))
HITL_POLL_INTERVAL = 2.0


def _sse(event: str, data: dict) -> dict:
    """EventSourceResponse payload (sse-starlette)."""
    return {"event": event, "data": json.dumps(data, default=str)}


async def chat_stream_events(
    crew: CustomerSupportCrew,
    request: ChatRequest,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> AsyncIterator[dict]:
    """
    Async generator yielding SSE events:
      started → stage (×N) → heartbeat → complete | error
      OR
      started → stage (×N) → approval_required → approval_decided | approval_timeout
    """
    trace_id = str(uuid.uuid4())
    start_time = datetime.now()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

    def push(event: str, payload: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"event": event, "payload": payload})

    def progress_callback(stage: dict) -> None:
        push("stage", {"trace_id": trace_id, **stage})

    async def run_crew() -> None:
        try:
            push("started", {"trace_id": trace_id})

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    run_crew_sync,
                    crew,
                    request.message,
                    request.request_human,
                    progress_callback,
                ),
                timeout=timeout_seconds,
            )

            response = map_to_response(result, trace_id, request)
            write_prompt_trace(trace_id, request, response, start_time, crew)

            # ── HITL path ─────────────────────────────────────────────────────
            if response.decision == "pending_approval" and response.approval:
                approval = response.approval
                from backend.telegram_bot import is_enabled, notify_manager, update_notification
                from backend.approval_service import (
                    customer_reply_for,
                    get_approval,
                    register_waiter,
                    remove_waiter,
                )

                if not is_enabled():
                    unavailable = response.model_copy(
                        update={
                            "decision": "resolve",
                            "reply": (
                                "A manager is not available to review this request right now. "
                                "Please contact billing, or set TELEGRAM_ENABLED=true for live approval."
                            ),
                            "reason_codes": ["manager_unavailable"],
                        }
                    )
                    push("complete", {"response": unavailable.model_dump()})
                else:
                    msg_id = await notify_manager(approval)
                    if msg_id:
                        try:
                            from backend.db import get_connection as _gc2
                            _conn = _gc2()
                            with _conn:
                                _conn.execute(
                                    "UPDATE approval_requests SET telegram_message_id=? WHERE id=?",
                                    (msg_id, approval.id),
                                )
                            _conn.close()
                        except Exception:
                            pass
                    push(
                        "approval_required",
                        {
                            "trace_id": trace_id,
                            "approval_id": approval.id,
                            "action_kind": approval.action_kind,
                            "reply_pending": response.reply,
                            "approval": approval.model_dump(),
                            "response": response.model_dump(),
                        },
                    )
                    event = register_waiter(approval.id)
                    try:
                        await asyncio.wait_for(event.wait(), timeout=HITL_TIMEOUT_SECONDS)
                        decided = get_approval(approval.id)
                        if decided and decided.status != "pending":
                            final_reply = customer_reply_for(decided)
                            reason = (
                                ["hitl_approved"]
                                if decided.status == "approved"
                                else ["hitl_denied"]
                            )
                            if msg_id:
                                await update_notification(
                                    msg_id,
                                    approval.id,
                                    decided.status,
                                    decided.operator_note,
                                )
                            final = response.model_copy(
                                update={
                                    "decision": "resolve",
                                    "reply": final_reply,
                                    "reason_codes": reason,
                                    "approval": decided,
                                }
                            )
                            push(
                                "approval_decided",
                                {
                                    "trace_id": trace_id,
                                    "approval_id": approval.id,
                                    "outcome": decided.status,
                                    "reply": final_reply,
                                    "response": final.model_dump(),
                                },
                            )
                            push("complete", {"response": final.model_dump()})
                        else:
                            timeout_reply = (
                                "Your request is still under review. "
                                "We'll follow up once a manager has responded."
                            )
                            timeout_resp = response.model_copy(
                                update={
                                    "decision": "resolve",
                                    "reply": timeout_reply,
                                    "reason_codes": ["hitl_timeout"],
                                }
                            )
                            push(
                                "approval_timeout",
                                {
                                    "trace_id": trace_id,
                                    "approval_id": approval.id,
                                    "reply": timeout_reply,
                                    "response": timeout_resp.model_dump(),
                                },
                            )
                            push("complete", {"response": timeout_resp.model_dump()})
                    except asyncio.TimeoutError:
                        timeout_reply = (
                            "Your request is still under review. "
                            "We'll follow up once a manager has responded."
                        )
                        timeout_resp = response.model_copy(
                            update={
                                "decision": "resolve",
                                "reply": timeout_reply,
                                "reason_codes": ["hitl_timeout"],
                            }
                        )
                        push(
                            "approval_timeout",
                            {
                                "trace_id": trace_id,
                                "approval_id": approval.id,
                                "reply": timeout_reply,
                                "response": timeout_resp.model_dump(),
                            },
                        )
                        push("complete", {"response": timeout_resp.model_dump()})
                    finally:
                        remove_waiter(approval.id)
            else:
                # ── Normal resolve / escalate path ────────────────────────────
                push("complete", {"response": response.model_dump()})

        except asyncio.TimeoutError:
            response = error_response(
                trace_id,
                "llm_or_timeout",
                f"Request timed out after {timeout_seconds}s. Please talk to a human agent.",
                request,
                reason_codes=["timeout"],
            )
            write_prompt_trace(trace_id, request, response, start_time, crew, error="timeout")
            push("error", {"response": response.model_dump()})

        except FileNotFoundError as exc:
            response = error_response(
                trace_id,
                "kb_unavailable",
                "Knowledge base unavailable. Please talk to a human agent.",
                request,
                reason_codes=["system_error"],
            )
            write_prompt_trace(trace_id, request, response, start_time, crew, error=str(exc))
            push("error", {"response": response.model_dump()})

        except Exception as exc:
            print(f"[chat/stream] system_error: {type(exc).__name__}: {exc}")
            response = error_response(
                trace_id,
                "system_error",
                "An unexpected error occurred. Please talk to a human agent.",
                request,
                reason_codes=["system_error"],
            )
            write_prompt_trace(trace_id, request, response, start_time, crew, error=str(exc))
            push("error", {"response": response.model_dump()})

        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    crew_task = asyncio.create_task(run_crew())
    heartbeat_interval = 15.0

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield _sse("heartbeat", {"trace_id": trace_id})
                continue

            if item is None:
                break

            event_name = item["event"]
            payload = item["payload"]
            yield _sse(event_name, payload)

            # Terminal events — stop the generator
            if event_name in ("complete", "error"):
                break

    finally:
        if not crew_task.done():
            crew_task.cancel()
            try:
                await crew_task
            except asyncio.CancelledError:
                pass
