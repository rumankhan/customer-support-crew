"""
FastAPI backend for Multi-Agent Customer Support Crew.
Implements POST /api/chat, POST /api/chat/stream (SSE), HITL approvals, and GET /health.
"""
import os
import uuid
import asyncio
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from backend.models import (
    ApprovalDecisionRequest,
    ApprovalRequest,
    ApprovalStatusResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    MetaInfo,
    EscalationPacket,
    ErrorDetail,
)
from backend.crew import CustomerSupportCrew
from backend.chat_service import (
    DEFAULT_TIMEOUT_SECONDS,
    error_response,
    map_to_response,
    run_crew_sync,
    write_prompt_trace,
)
from backend.streaming import chat_stream_events

crew_instance: Optional[CustomerSupportCrew] = None
last_result: Optional[ChatResponse] = None
_telegram_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global crew_instance, _telegram_task
    from backend.db import ensure_database

    print("Initialising SQLite support database...")
    ensure_database()
    print("Initializing Customer Support Crew...")
    crew_instance = CustomerSupportCrew()
    print("Crew initialized:")
    print(f"  Provider: {crew_instance.llm_provider}")
    print(f"  Model: {crew_instance.model_low}")

    from backend.telegram_bot import is_enabled, run_polling

    if is_enabled():
        _telegram_task = asyncio.create_task(run_polling())
        print("Telegram manager bot: polling started")
    else:
        print("Telegram manager bot: disabled (set TELEGRAM_ENABLED=true to activate)")

    yield

    if _telegram_task:
        _telegram_task.cancel()
        try:
            await _telegram_task
        except asyncio.CancelledError:
            pass
    print("Shutting down...")


app = FastAPI(
    title="Multi-Agent Customer Support API",
    description="B-Mobile customer support crew with grounded answers and escalation",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def chat_validation_handler(request: Request, exc: RequestValidationError):
    raw_message = ""
    request_human = False
    disclosure = None
    body = exc.body
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, str):
            raw_message = msg[:4000]
        request_human = bool(body.get("request_human", False))
        disclosure = body.get("disclosure_acknowledged")
    first_msg = "Invalid chat request."
    if exc.errors():
        first_msg = str(exc.errors()[0].get("msg", first_msg))
    stub = f"STUB-{uuid.uuid4().hex[:8].upper()}"
    envelope = ChatResponse(
        decision="escalate",
        reply="We could not complete this request. Please talk to a human.",
        sources_used=[],
        sentiment="neutral",
        risk="medium",
        reason_codes=["system_error"],
        steps=[],
        trace_id=str(uuid.uuid4()),
        packet=EscalationPacket(
            intent="",
            urgency="medium",
            customer_message=raw_message or "(invalid request)",
            request_human=request_human,
            citations_attempted=[],
            draft_reply="",
            sentiment="neutral",
            risk="medium",
            reason_codes=["system_error"],
            stub_ticket_id=stub,
        ),
        stub_ticket_id=stub,
        meta=MetaInfo(
            ai_disclosure=True,
            disclosure_acknowledged=disclosure if isinstance(disclosure, bool) else None,
        ),
        error=ErrorDetail(code="validation_error", message=first_msg),
    )
    response = JSONResponse(status_code=400, content=envelope.model_dump())
    origin = request.headers.get("origin")
    if origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming chat — full ChatResponse after crew kickoff (legacy / tests)."""
    global crew_instance, last_result

    if not crew_instance:
        return error_response(
            str(uuid.uuid4()),
            "system_error",
            "Crew not initialized",
            request,
        )

    trace_id = str(uuid.uuid4())
    start_time = datetime.now()
    timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                run_crew_sync,
                crew_instance,
                request.message,
                request.request_human,
            ),
            timeout=timeout_seconds,
        )
        response = map_to_response(result, trace_id, request)
        write_prompt_trace(trace_id, request, response, start_time, crew_instance)
        last_result = response
        return response

    except asyncio.TimeoutError:
        response = error_response(
            trace_id,
            "llm_or_timeout",
            f"Request timed out after {timeout_seconds}s. Please talk to a human agent.",
            request,
            reason_codes=["timeout"],
        )
        write_prompt_trace(trace_id, request, response, start_time, crew_instance, error="timeout")
        last_result = response
        return response

    except FileNotFoundError as e:
        response = error_response(
            trace_id,
            "kb_unavailable",
            "Knowledge base unavailable. Please talk to a human agent.",
            request,
            reason_codes=["system_error"],
        )
        write_prompt_trace(trace_id, request, response, start_time, crew_instance, error=str(e))
        last_result = response
        return response

    except Exception as e:
        print(f"[chat] system_error: {type(e).__name__}: {e}")
        response = error_response(
            trace_id,
            "system_error",
            "An unexpected error occurred. Please talk to a human agent.",
            request,
            reason_codes=["system_error"],
        )
        write_prompt_trace(trace_id, request, response, start_time, crew_instance, error=str(e))
        last_result = response
        return response


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    SSE progress stream for crew execution.
    Events: started, stage, heartbeat, complete | error (final ChatResponse in payload).
    """
    if not crew_instance:
        trace_id = str(uuid.uuid4())
        err = error_response(trace_id, "system_error", "Crew not initialized", request)

        async def _err_once():
            import json
            yield {"event": "error", "data": json.dumps({"response": err.model_dump()})}

        return EventSourceResponse(_err_once())

    return EventSourceResponse(chat_stream_events(crew_instance, request))


@app.get("/api/approvals/pending", response_model=List[ApprovalRequest])
async def approvals_pending():
    from backend.approval_service import list_pending
    return list_pending()


@app.get("/api/approvals/history", response_model=List[ApprovalRequest])
async def approvals_history():
    from backend.approval_service import list_history
    return list_history(10)


@app.get("/api/approvals/{approval_id}/status", response_model=ApprovalStatusResponse)
async def approval_status(approval_id: str):
    from backend.approval_service import customer_reply_for, get_approval
    row = get_approval(approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalStatusResponse(
        id=row.id,
        status=row.status,
        operator_note=row.operator_note,
        decided_at=row.decided_at,
        customer_reply=customer_reply_for(row),
    )


@app.post("/api/approvals/{approval_id}/decide", response_model=ApprovalRequest)
async def approval_decide(approval_id: str, body: ApprovalDecisionRequest):
    """Internal/demo decide endpoint (Telegram is the primary manager console)."""
    from backend.approval_service import decide_approval, get_approval
    updated = decide_approval(
        approval_id,
        body.decision,
        operator_note=body.operator_note,
        decided_by="api:operator",
    )
    if not updated:
        row = get_approval(approval_id)
        if not row:
            raise HTTPException(status_code=404, detail="Approval not found")
        raise HTTPException(status_code=409, detail="Approval already decided")
    row = get_approval(approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")
    return row


@app.get("/api/last-result", response_model=ChatResponse)
async def get_last_result():
    global last_result
    if not last_result:
        raise HTTPException(status_code=404, detail="No result available")
    return last_result


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
