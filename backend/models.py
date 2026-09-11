"""
Pydantic models for Multi-Agent Customer Support Crew structured outputs.
Aligns with SAD §2 contracts.
"""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ========== Agent Task Output Models ==========

class ClassifierOutput(BaseModel):
    """Output from query_classifier agent."""
    intent: str = Field(..., description="Open string describing customer intent")
    urgency: Literal["low", "medium", "high"] = Field(..., description="Urgency level")
    entities: List[str] = Field(default_factory=list, description="Extracted entities (e.g., account, plan, device)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence score")


class PassageResult(BaseModel):
    """A single passage from knowledge base retrieval."""
    title: str = Field(..., description="Article title")
    snippet: str = Field(..., description="Relevant passage text")
    score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")


class Citation(BaseModel):
    """Citation for grounded response."""
    title: str = Field(..., description="Article title")
    snippet: str = Field(..., description="Relevant excerpt")


class RetrieverOutput(BaseModel):
    """Output from knowledge_retriever agent."""
    passages: List[PassageResult] = Field(default_factory=list, description="Retrieved passages with scores")
    citations: List[Citation] = Field(default_factory=list, description="Citations for response composition")
    gap: bool = Field(default=False, description="True if no passage above similarity floor")


class ResponseOutput(BaseModel):
    """Output from response_specialist agent."""
    reply: str = Field(..., description="Customer-facing reply text")
    sources_used: List[Citation] = Field(default_factory=list, description="Sources cited in reply")
    refused: bool = Field(default=False, description="True if unable to provide grounded answer")


class EscalationPacket(BaseModel):
    """Context packet for human agent when escalating."""
    intent: str = Field(default="", description="Classified intent")
    urgency: Literal["low", "medium", "high"] = Field(default="medium", description="Urgency level")
    customer_message: str = Field(..., description="Original customer message")
    request_human: bool = Field(default=False, description="Customer explicitly requested human")
    citations_attempted: List[Citation] = Field(default_factory=list, description="KB articles attempted")
    draft_reply: str = Field(default="", description="Draft reply (may be refusal text)")
    sentiment: Literal["positive", "neutral", "negative"] = Field(default="neutral", description="Text sentiment")
    risk: Literal["low", "medium", "high"] = Field(default="medium", description="Risk level")
    reason_codes: List[str] = Field(default_factory=list, description="Escalation reason codes")
    stub_ticket_id: str = Field(..., description="Stub ticket identifier")


class EscalationOutput(BaseModel):
    """Output from escalation_manager agent."""
    decision: Literal["resolve", "escalate"] = Field(..., description="Final resolution decision")
    sentiment: Literal["positive", "neutral", "negative"] = Field(default="neutral", description="Text sentiment")
    risk: Literal["low", "medium", "high"] = Field(default="medium", description="Risk assessment")
    reason_codes: List[str] = Field(default_factory=list, description="Decision reason codes")
    packet: Optional[EscalationPacket] = Field(default=None, description="Escalation packet (null on resolve)")


# ========== HITL Approval Models ==========

ACTION_KIND = Literal[
    "billing_credit",
    "etf_waiver",
    "security_override",
    "refund",
    "roaming_exception",
]

ACTION_KIND_LABELS: Dict[str, str] = {
    "billing_credit": "Billing Credit",
    "etf_waiver": "ETF / Cancellation Waiver",
    "security_override": "Account Security Override",
    "refund": "Refund / Return Processing",
    "roaming_exception": "Roaming Exception",
}


class ApprovalRequest(BaseModel):
    """HITL approval proposal — surfaced to manager via Telegram."""
    id: str = Field(..., description="Unique approval ID (APR-xxxx)")
    action_kind: str = Field(..., description="Type of policy action")
    subject_id: str = Field(..., description="Account ID (ACC-*) or Order ID (ORD-*)")
    amount: Optional[float] = Field(default=None, description="Dollar amount for credit/refund/ETF")
    reason: str = Field(default="", description="Customer reason for the request")
    status: Literal["pending", "approved", "denied"] = Field(default="pending")
    operator_note: Optional[str] = Field(default=None, description="Manager note (on deny)")
    context: Dict[str, Any] = Field(default_factory=dict, description="Stub account/order context")
    created_at: str = Field(default="", description="ISO timestamp")
    decided_at: Optional[str] = Field(default=None)
    decided_by: Optional[str] = Field(default=None, description="telegram:{user_id}")
    trace_id: Optional[str] = Field(default=None, description="Local prompt-trace identifier")
    crew_trace_url: Optional[str] = Field(
        default=None, description="CrewAI AMP dashboard URL for this crew run"
    )


class ApprovalDecisionRequest(BaseModel):
    """Body for POST /api/approvals/{id}/decide."""
    decision: Literal["approve", "deny"] = Field(..., description="Manager decision")
    operator_note: Optional[str] = Field(default=None, description="Optional reason on deny")


class ApprovalStatusResponse(BaseModel):
    """Response for GET /api/approvals/{id}/status."""
    id: str
    status: Literal["pending", "approved", "denied"]
    operator_note: Optional[str] = None
    decided_at: Optional[str] = None
    customer_reply: Optional[str] = None


# ========== API Request/Response Models ==========

class ChatRequest(BaseModel):
    """Request schema for POST /api/chat."""
    message: str = Field(..., min_length=1, max_length=4000, description="Customer message")
    request_human: bool = Field(default=False, description="Customer requested human agent")
    session_id: Optional[str] = Field(default=None, description="Opaque session identifier (optional)")
    disclosure_acknowledged: Optional[bool] = Field(default=None, description="AI disclosure acknowledged flag")


class MetaInfo(BaseModel):
    """Metadata for API response (AC-01b)."""
    ai_disclosure: bool = Field(default=True, description="Always true - AI disclosure policy")
    disclosure_acknowledged: Optional[bool] = Field(default=None, description="Echoed from request")


class ErrorDetail(BaseModel):
    """Error information in response envelope."""
    code: str = Field(..., description="Error code: llm_or_timeout, validation_error, kb_unavailable, system_error")
    message: str = Field(..., description="Human-readable error message")


class StepSummary(BaseModel):
    """Summary of one agent step."""
    agent: str = Field(..., description="Agent name")
    summary: str = Field(..., description="Brief step summary")


class ChatResponse(BaseModel):
    """Response schema for POST /api/chat."""
    decision: Literal["resolve", "escalate", "pending_approval"] = Field(..., description="Resolution decision")
    reply: str = Field(..., description="Customer-facing reply or error message")
    sources_used: List[Citation] = Field(default_factory=list, description="Sources cited (empty on escalate/error)")
    sentiment: Literal["positive", "neutral", "negative"] = Field(default="neutral", description="Text sentiment")
    risk: Literal["low", "medium", "high"] = Field(default="medium", description="Risk assessment")
    reason_codes: List[str] = Field(default_factory=list, description="Decision/escalation reason codes")
    steps: List[StepSummary] = Field(default_factory=list, description="Agent step summaries (partial on timeout)")
    trace_id: str = Field(..., description="Unique trace identifier")
    packet: Optional[EscalationPacket] = Field(default=None, description="Escalation packet (null on resolve)")
    stub_ticket_id: Optional[str] = Field(default=None, description="Stub ticket ID (null on resolve)")
    approval: Optional[ApprovalRequest] = Field(default=None, description="Approval proposal (on pending_approval)")
    crew_trace_url: Optional[str] = Field(
        default=None, description="CrewAI AMP dashboard URL for this crew run"
    )
    meta: MetaInfo = Field(default_factory=MetaInfo, description="Metadata (AC-01b)")
    error: Optional[ErrorDetail] = Field(default=None, description="Error details (null on success)")


class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: Literal["ok"] = Field(default="ok", description="Health status")
