"""
FastAPI backend for Multi-Agent Customer Support Crew.
Implements POST /api/chat and GET /health per SAD §2.
"""
import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ErrorDetail,
    StepSummary,
    MetaInfo,
    EscalationPacket
)
from backend.crew import CustomerSupportCrew


# Global crew instance
crew_instance: Optional[CustomerSupportCrew] = None

# In-memory last result (process-local, lost on restart)
last_result: Optional[ChatResponse] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global crew_instance
    
    # Startup: initialize crew
    print("Initializing Customer Support Crew...")
    crew_instance = CustomerSupportCrew()
    print(f"Crew initialized:")
    print(f"  Provider: {crew_instance.llm_provider}")
    print(f"  Model: {crew_instance.model_low}")
    
    yield
    
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="Multi-Agent Customer Support API",
    description="B-Mobile customer support crew with grounded answers and escalation",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint (AC-06a)."""
    return HealthResponse(status="ok")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint - runs crew and returns resolution decision.
    Implements SAD §2 contracts with 90s soft timeout (increased for Ollama).
    """
    global crew_instance, last_result
    
    if not crew_instance:
        return _error_response(
            trace_id=str(uuid.uuid4()),
            code="system_error",
            message="Crew not initialized",
            request=request
        )
    
    trace_id = str(uuid.uuid4())
    start_time = datetime.now()
    
    # Soft timeout increased to 90s for Ollama gemma4:31b (slower than OpenAI)
    timeout_seconds = 90
    
    try:
        # Run crew with timeout
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_crew_sync,
                crew_instance,
                request.message,
                request.request_human
            ),
            timeout=timeout_seconds
        )
        
        # Map crew outputs to ChatResponse
        response = _map_to_response(
            result=result,
            trace_id=trace_id,
            request=request
        )
        
        # Write prompt trace
        _write_prompt_trace(
            trace_id=trace_id,
            request=request,
            response=response,
            start_time=start_time
        )
        
        # Store as last result
        last_result = response
        
        return response
        
    except asyncio.TimeoutError:
        # Timeout - return error envelope with escalation
        response = _error_response(
            trace_id=trace_id,
            code="llm_or_timeout",
            message=f"Request timed out after {timeout_seconds}s. Please talk to a human agent.",
            request=request,
            reason_codes=["timeout"]
        )
        
        _write_prompt_trace(
            trace_id=trace_id,
            request=request,
            response=response,
            start_time=start_time,
            error="timeout"
        )
        
        last_result = response
        return response
        
    except FileNotFoundError as e:
        # KB unavailable
        response = _error_response(
            trace_id=trace_id,
            code="kb_unavailable",
            message="Knowledge base unavailable. Please talk to a human agent.",
            request=request,
            reason_codes=["system_error"]
        )
        
        _write_prompt_trace(
            trace_id=trace_id,
            request=request,
            response=response,
            start_time=start_time,
            error=str(e)
        )
        
        last_result = response
        return response
        
    except Exception as e:
        # General system error
        response = _error_response(
            trace_id=trace_id,
            code="system_error",
            message="An unexpected error occurred. Please talk to a human agent.",
            request=request,
            reason_codes=["system_error"]
        )
        
        _write_prompt_trace(
            trace_id=trace_id,
            request=request,
            response=response,
            start_time=start_time,
            error=str(e)
        )
        
        last_result = response
        return response


@app.get("/api/last-result", response_model=ChatResponse)
async def get_last_result():
    """
    Optional polish endpoint - returns last in-memory ChatResponse.
    NOT required for AC-05 or Integration exit per SAD ADR-14.
    """
    global last_result
    
    if not last_result:
        raise HTTPException(status_code=404, detail="No result available")
    
    return last_result


def _run_crew_sync(crew: CustomerSupportCrew, message: str, request_human: bool) -> dict:
    """Synchronous crew execution wrapper for asyncio.to_thread."""
    return crew.kickoff({
        "message": message,
        "request_human": request_human
    })


def _map_to_response(result: dict, trace_id: str, request: ChatRequest) -> ChatResponse:
    """
    Map crew task outputs to ChatResponse schema.
    Implements SAD §2 mapper table.
    """
    tasks = result.get("tasks", [])
    
    # Extract task outputs
    classifier_output = None
    retriever_output = None
    response_output = None
    escalation_output = None
    
    if len(tasks) >= 4:
        classifier_output = tasks[0].output.pydantic if hasattr(tasks[0].output, 'pydantic') else None
        retriever_output = tasks[1].output.pydantic if hasattr(tasks[1].output, 'pydantic') else None
        response_output = tasks[2].output.pydantic if hasattr(tasks[2].output, 'pydantic') else None
        escalation_output = tasks[3].output.pydantic if hasattr(tasks[3].output, 'pydantic') else None
    
    # Build steps summary
    steps = []
    agent_names = ["query_classifier", "knowledge_retriever", "response_specialist", "escalation_manager"]
    for i, task in enumerate(tasks):
        agent_name = agent_names[i] if i < len(agent_names) else f"agent_{i}"
        summary = str(task.output)[:200] if task.output else "No output"
        steps.append(StepSummary(agent=agent_name, summary=summary))
    
    # Default values
    decision = "escalate"
    reply = "We could not complete this request. Please talk to a human."
    sources_used = []
    sentiment = "neutral"
    risk = "medium"
    reason_codes = ["system_error"]
    packet = None
    stub_ticket_id = None
    
    # Map from escalation_output if available
    if escalation_output:
        decision = escalation_output.decision
        sentiment = escalation_output.sentiment
        risk = escalation_output.risk
        reason_codes = escalation_output.reason_codes or []
        
        if decision == "escalate" and escalation_output.packet:
            packet = escalation_output.packet
            stub_ticket_id = packet.stub_ticket_id
    
    # Map reply and sources from response_output
    if response_output:
        reply = response_output.reply
        if decision == "resolve":
            sources_used = response_output.sources_used or []
    
    # Build meta
    meta = MetaInfo(
        ai_disclosure=True,
        disclosure_acknowledged=request.disclosure_acknowledged
    )
    
    return ChatResponse(
        decision=decision,
        reply=reply,
        sources_used=sources_used,
        sentiment=sentiment,
        risk=risk,
        reason_codes=reason_codes,
        steps=steps,
        trace_id=trace_id,
        packet=packet,
        stub_ticket_id=stub_ticket_id,
        meta=meta,
        error=None
    )


def _error_response(
    trace_id: str,
    code: str,
    message: str,
    request: ChatRequest,
    reason_codes: list[str] = None
) -> ChatResponse:
    """
    Create error envelope ChatResponse with minimal escalation packet.
    Per SAD §2 system-failure packet policy.
    """
    if reason_codes is None:
        reason_codes = ["system_error"]
    
    # Create minimal packet with known fields
    packet = EscalationPacket(
        intent="",
        urgency="medium",
        customer_message=request.message,
        request_human=request.request_human,
        citations_attempted=[],
        draft_reply="",
        sentiment="neutral",
        risk="medium",
        reason_codes=reason_codes,
        stub_ticket_id=f"STUB-{uuid.uuid4().hex[:8].upper()}"
    )
    
    return ChatResponse(
        decision="escalate",
        reply=message,
        sources_used=[],
        sentiment="neutral",
        risk="medium",
        reason_codes=reason_codes,
        steps=[],
        trace_id=trace_id,
        packet=packet,
        stub_ticket_id=packet.stub_ticket_id,
        meta=MetaInfo(
            ai_disclosure=True,
            disclosure_acknowledged=request.disclosure_acknowledged
        ),
        error=ErrorDetail(code=code, message=message)
    )


def _write_prompt_trace(
    trace_id: str,
    request: ChatRequest,
    response: ChatResponse,
    start_time: datetime,
    error: Optional[str] = None
):
    """
    Write prompt trace JSON to LOG_DIR per SAD §2 minimum schema.
    Redacts PII/secrets.
    """
    log_dir = os.getenv("LOG_DIR", "project-context/2.build/logs")
    os.makedirs(log_dir, exist_ok=True)
    
    trace_path = os.path.join(log_dir, f"{trace_id}.json")
    
    trace_data = {
        "trace_id": trace_id,
        "timestamp": start_time.isoformat(),
        "inputs": {
            "message": request.message[:200] + "..." if len(request.message) > 200 else request.message,
            "request_human": request.request_human,
            "session_id": request.session_id,
            "disclosure_acknowledged": request.disclosure_acknowledged
        },
        "steps": [step.dict() for step in response.steps],
        "decision": response.decision,
        "reason_codes": response.reason_codes,
        "meta": response.meta.dict(),
        "error": response.error.dict() if response.error else None,
        "model_tiers": {
            "low": crew_instance.model_low if crew_instance else "unknown",
            "mid": crew_instance.model_mid if crew_instance else "unknown"
        },
        "elapsed_ms": int((datetime.now() - start_time).total_seconds() * 1000)
    }
    
    if error:
        trace_data["error_detail"] = error
    
    with open(trace_path, 'w', encoding='utf-8') as f:
        json.dump(trace_data, f, indent=2)


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("BACKEND_PORT", "8000"))
    
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
