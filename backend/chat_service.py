"""
Shared chat orchestration: crew kickoff, ChatResponse mapping, prompt traces.
Used by POST /api/chat (JSON) and POST /api/chat/stream (SSE).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from backend.crew import CustomerSupportCrew
from backend.models import (
    ApprovalRequest,
    ChatRequest,
    ChatResponse,
    Citation,
    ErrorDetail,
    EscalationPacket,
    MetaInfo,
    StepSummary,
)

ProgressCallback = Callable[[dict[str, Any]], None]

AGENT_IDS = [
    "query_classifier",
    "knowledge_retriever",
    "response_specialist",
    "escalation_manager",
]

DEFAULT_TIMEOUT_SECONDS = int(os.getenv("CHAT_TIMEOUT_SECONDS", "180"))

GREETING_REPLY = (
    "Hello! Thank you for contacting B-Mobile. How can I help you today?"
)

# Intent strings from query_classifier that should resolve without escalation.
_GREETING_INTENT_EXACT = frozenset(
    {
        "greeting",
        "hello",
        "hi",
        "hey",
        "small_talk",
        "small talk",
        "chitchat",
        "thanks",
        "thank you",
        "farewell",
        "goodbye",
    }
)
_GREETING_INTENT_SUBSTRINGS = ("greeting", "small_talk", "small talk", "chitchat")

_SOFT_ESCALATE_REASONS = frozenset({"retrieval_gap", "refused", "low_confidence"})
_HARD_ESCALATE_REASONS = frozenset(
    {"request_human", "high_risk_sentiment", "timeout", "system_error"}
)

LOW_URGENCY_GAP_REPLY = (
    "I don't have that in our B-Mobile help articles yet. "
    "Feel free to ask another B-Mobile question."
)

OUT_OF_SCOPE_REPLY = (
    "I can only help with B-Mobile mobile service and account questions "
    "(plans, billing, devices, PIN, voicemail, and similar topics). "
    "I don't have information on that subject."
)

_OUT_OF_SCOPE_INTENT_EXACT = frozenset(
    {
        "out_of_scope",
        "out of scope",
        "off_topic",
        "off topic",
        "off-topic",
        "unrelated",
        "general_knowledge",
        "non_bmobile",
        "not_bmobile",
    }
)
_OUT_OF_SCOPE_INTENT_SUBSTRINGS = (
    "out_of_scope",
    "out of scope",
    "off_topic",
    "off topic",
    "off-topic",
    "unrelated",
    "non_bmobile",
    "not b-mobile",
    "outside scope",
    "outside b-mobile",
)

# ticket_stub returns STUB- + 8 hex chars. Reject LLM-invented TICKET-/TKT- ids.
_STUB_TICKET_RE = re.compile(r"^STUB-[0-9A-F]{8}$", re.IGNORECASE)


def issue_stub_ticket_id() -> str:
    """Canonical stub id — same shape as TicketStubTool."""
    return f"STUB-{uuid.uuid4().hex[:8].upper()}"


def is_valid_stub_ticket_id(value: str | None) -> bool:
    return isinstance(value, str) and bool(_STUB_TICKET_RE.match(value.strip()))


def sanitize_stub_ticket_id(value: str | None) -> str:
    """Keep a well-formed STUB-* id; otherwise mint one from the stub contract."""
    if is_valid_stub_ticket_id(value):
        return str(value).strip().upper()
    return issue_stub_ticket_id()


def _citation_title(src: Any) -> str:
    if isinstance(src, Citation):
        return (src.title or "").strip()
    if isinstance(src, dict):
        return str(src.get("title") or "").strip()
    return ""


def lookup_kb_allowed_titles(query: str) -> tuple[bool, set[str]]:
    """
    Re-run FTS against the customer message.
    Returns (gap, allowed_titles). On tool/DB failure, treat as gap so we never
    attach invented citations (fail-closed on grounding, fail-open on chat).
    """
    if not query or not query.strip():
        return True, set()
    try:
        from backend.tools import kb_search_tool

        raw = kb_search_tool._run(query)
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 — missing DB / FTS errors must not leak citations
        return True, set()
    titles: set[str] = set()
    for item in (data.get("citations") or []) + (data.get("passages") or []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip().lower()
        if title:
            titles.add(title)
    gap = bool(data.get("gap", True)) or not titles
    return gap, titles


def filter_grounded_sources(
    claimed: list[Any] | None,
    *,
    kb_gap: bool,
    allowed_titles: set[str],
) -> list[Citation]:
    """Drop citations that did not come from a live KB hit on the customer message."""
    if kb_gap or not claimed:
        return []
    kept: list[Citation] = []
    for src in claimed:
        title = _citation_title(src)
        if title.lower() in allowed_titles:
            kept.append(src if isinstance(src, Citation) else Citation.model_validate(src))
    return kept


def ensure_escalation_artifacts(
    *,
    packet: EscalationPacket | None,
    stub_ticket_id: str | None,
    request: ChatRequest,
    classifier_intent: str | None,
    classifier_urgency: str | None,
    sentiment: str,
    risk: str,
    reason_codes: list[str],
    reply: str,
    citations_attempted: list[Citation],
) -> tuple[EscalationPacket, str]:
    """Escalate responses always carry a packet and a freshly issued STUB-* id.

    Never copy the model-supplied ticket id — LLMs reuse example values such as
    STUB-A1B2C3D4 that happen to match the regex.
    """
    stub = issue_stub_ticket_id()
    urgency = classifier_urgency if classifier_urgency in ("low", "medium", "high") else "medium"
    if packet is None:
        packet = EscalationPacket(
            intent=classifier_intent or "",
            urgency=urgency,  # type: ignore[arg-type]
            customer_message=request.message,
            request_human=request.request_human,
            citations_attempted=citations_attempted,
            draft_reply=reply or "",
            sentiment=sentiment,  # type: ignore[arg-type]
            risk=risk,  # type: ignore[arg-type]
            reason_codes=reason_codes,
            stub_ticket_id=stub,
        )
    else:
        packet = packet.model_copy(update={"stub_ticket_id": stub})
    return packet, stub


_HUMAN_HANDOFF_PHRASES = (
    "human agent",
    "human specialist",
    "talk to a person",
    "talk to a human",
    "speak with a human",
    "speaking with a human",
    "speak to a human",
    "connect you with a specialist",
    "connecting you with a",
    "route you to a specialist",
    "personalized support from a human",
    "recommend speaking with",
    "recommend talking to",
)


def _strip_soft_escalate_reasons(reason_codes: list[str]) -> list[str]:
    return [code for code in reason_codes if code not in _SOFT_ESCALATE_REASONS]


def _pick_reply(reply: str, draft_reply: str | None, fallback: str) -> str:
    next_reply = reply.strip()
    if (not next_reply or next_reply.startswith("We could not complete")) and draft_reply:
        next_reply = draft_reply.strip()
    if not next_reply or next_reply.startswith("We could not complete"):
        next_reply = fallback
    return next_reply


def mentions_human_handoff(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _HUMAN_HANDOFF_PHRASES)


def _strip_human_handoff_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [part for part in parts if part and not mentions_human_handoff(part)]
    return " ".join(kept).strip()


def is_out_of_scope_intent(intent: str | None) -> bool:
    """True when the question is outside B-Mobile mobile/account support."""
    if not intent:
        return False
    normalized = intent.strip().lower().replace("-", " ")
    normalized_us = normalized.replace(" ", "_")
    if normalized in _OUT_OF_SCOPE_INTENT_EXACT or normalized_us in _OUT_OF_SCOPE_INTENT_EXACT:
        return True
    return any(
        token in normalized or token.replace("_", " ") in normalized
        for token in _OUT_OF_SCOPE_INTENT_SUBSTRINGS
    )


def sanitize_out_of_scope_reply(reply: str) -> str:
    """Remove human-agent handoff language for off-topic questions."""
    cleaned = _strip_human_handoff_sentences(reply)
    if not cleaned or mentions_human_handoff(cleaned):
        return OUT_OF_SCOPE_REPLY
    return cleaned


def apply_out_of_scope_reply_policy(
    *,
    classifier_intent: str | None,
    request_human: bool,
    decision: str,
    reply: str,
    reason_codes: list[str],
) -> tuple[str, str, list[str], bool]:
    """Off-topic questions resolve in-chat without suggesting a human agent."""
    if not is_out_of_scope_intent(classifier_intent) or request_human:
        return decision, reply, reason_codes, False

    cleaned_reply = sanitize_out_of_scope_reply(reply)
    cleaned_codes = _strip_soft_escalate_reasons(reason_codes)
    return "resolve", cleaned_reply, cleaned_codes, True


def is_greeting_intent(intent: str | None) -> bool:
    """True when classifier intent is a pure greeting / small-talk (no KB required)."""
    if not intent:
        return False
    normalized = intent.strip().lower()
    if normalized in _GREETING_INTENT_EXACT:
        return True
    return any(token in normalized for token in _GREETING_INTENT_SUBSTRINGS)


def apply_greeting_resolve_override(
    *,
    classifier_intent: str | None,
    request_human: bool,
    decision: str,
    reply: str,
    reason_codes: list[str],
) -> tuple[str, str, list[str], bool]:
    """
    Pure greetings resolve locally — no specialist handoff when customer did not ask for a human.
    Returns (decision, reply, reason_codes, override_applied).
    """
    if not is_greeting_intent(classifier_intent) or request_human:
        return decision, reply, reason_codes, False
    if "request_human" in reason_codes:
        return decision, reply, reason_codes, False

    cleaned_codes = _strip_soft_escalate_reasons(reason_codes)
    next_reply = _pick_reply(reply, None, GREETING_REPLY)
    return "resolve", next_reply, cleaned_codes, True


def apply_low_urgency_resolve_override(
    *,
    urgency: str | None,
    sentiment: str,
    risk: str,
    request_human: bool,
    decision: str,
    reply: str,
    reason_codes: list[str],
    draft_reply: str | None,
) -> tuple[str, str, list[str], bool]:
    """
    Low-urgency, calm interactions resolve in-chat — no specialist routing for KB gaps alone.
    Returns (decision, reply, reason_codes, override_applied).
    """
    if decision != "escalate":
        return decision, reply, reason_codes, False
    if request_human or "request_human" in reason_codes:
        return decision, reply, reason_codes, False
    if urgency != "low":
        return decision, reply, reason_codes, False
    if sentiment == "negative":
        return decision, reply, reason_codes, False
    if risk == "high":
        return decision, reply, reason_codes, False
    if any(code in _HARD_ESCALATE_REASONS for code in reason_codes):
        return decision, reply, reason_codes, False

    cleaned_codes = _strip_soft_escalate_reasons(reason_codes)
    next_reply = _pick_reply(reply, draft_reply, LOW_URGENCY_GAP_REPLY)
    return "resolve", next_reply, cleaned_codes, True


def run_crew_sync(
    crew: CustomerSupportCrew,
    message: str,
    request_human: bool,
    progress: Optional[ProgressCallback] = None,
) -> dict:
    """Run crew synchronously; optional progress callback for SSE stage events."""
    return crew.kickoff(
        {"message": message, "request_human": request_human},
        progress_callback=progress,
    )


def map_to_response(result: dict, trace_id: str, request: ChatRequest) -> ChatResponse:
    """Map crew task outputs to ChatResponse schema (SAD §2)."""
    tasks = result.get("tasks", [])

    classifier_output = None
    retriever_output = None
    response_output = None
    escalation_output = None

    if len(tasks) >= 4:
        classifier_output = tasks[0].output.pydantic if hasattr(tasks[0].output, "pydantic") else None
        retriever_output = tasks[1].output.pydantic if hasattr(tasks[1].output, "pydantic") else None
        response_output = tasks[2].output.pydantic if hasattr(tasks[2].output, "pydantic") else None
        escalation_output = tasks[3].output.pydantic if hasattr(tasks[3].output, "pydantic") else None

    steps: list[StepSummary] = []
    for i, task in enumerate(tasks):
        agent_name = AGENT_IDS[i] if i < len(AGENT_IDS) else f"agent_{i}"
        summary = str(task.output)[:200] if task.output else "No output"
        steps.append(StepSummary(agent=agent_name, summary=summary))

    decision = "escalate"
    reply = "We could not complete this request. Please talk to a human."
    sources_used = []
    sentiment = "neutral"
    risk = "medium"
    reason_codes = ["system_error"]
    packet = None
    stub_ticket_id = None

    if escalation_output:
        decision = escalation_output.decision
        sentiment = escalation_output.sentiment
        risk = escalation_output.risk
        reason_codes = escalation_output.reason_codes or []

        if decision == "escalate" and escalation_output.packet:
            packet = escalation_output.packet
            stub_ticket_id = packet.stub_ticket_id

    if response_output:
        reply = response_output.reply
        if decision == "resolve":
            sources_used = response_output.sources_used or []
        elif response_output.sources_used:
            sources_used = response_output.sources_used

    kb_gap, allowed_titles = lookup_kb_allowed_titles(request.message)
    sources_used = filter_grounded_sources(
        sources_used,
        kb_gap=kb_gap,
        allowed_titles=allowed_titles,
    )

    if (not reply or reply.startswith("We could not complete")) and packet and packet.draft_reply:
        reply = packet.draft_reply

    classifier_intent = classifier_output.intent if classifier_output else None
    classifier_urgency = classifier_output.urgency if classifier_output else None
    draft_reply = packet.draft_reply if packet else None

    decision, reply, reason_codes, greeting_override = apply_greeting_resolve_override(
        classifier_intent=classifier_intent,
        request_human=request.request_human,
        decision=decision,
        reply=reply,
        reason_codes=reason_codes,
    )
    resolve_override = greeting_override
    if not greeting_override:
        decision, reply, reason_codes, resolve_override = apply_low_urgency_resolve_override(
            urgency=classifier_urgency,
            sentiment=sentiment,
            risk=risk,
            request_human=request.request_human,
            decision=decision,
            reply=reply,
            reason_codes=reason_codes,
            draft_reply=draft_reply,
        )
    if resolve_override:
        packet = None
        stub_ticket_id = None
        sources_used = []

    decision, reply, reason_codes, out_of_scope_override = apply_out_of_scope_reply_policy(
        classifier_intent=classifier_intent,
        request_human=request.request_human,
        decision=decision,
        reply=reply,
        reason_codes=reason_codes,
    )
    if out_of_scope_override:
        packet = None
        stub_ticket_id = None
        sources_used = []

    if request.request_human:
        decision = "escalate"
        if "request_human" not in reason_codes:
            reason_codes = ["request_human", *reason_codes]
        resolve_override = False
        out_of_scope_override = False

    if decision == "escalate":
        packet, stub_ticket_id = ensure_escalation_artifacts(
            packet=packet,
            stub_ticket_id=stub_ticket_id,
            request=request,
            classifier_intent=classifier_intent,
            classifier_urgency=classifier_urgency,
            sentiment=sentiment,
            risk=risk,
            reason_codes=reason_codes,
            reply=reply,
            citations_attempted=list(sources_used),
        )
        sources_used = []

    # ── HITL policy-action detection ──────────────────────────────────────────
    # Only attempt after normal pipeline completes (non-escalate, non-override).
    approval: ApprovalRequest | None = None
    if (
        not request.request_human
        and not resolve_override
        and not out_of_scope_override
        and classifier_output is not None
    ):
        from backend.approval_service import (
            create_approval,
            detect_policy_action,
            load_subject_context,
            pending_reply as hitl_pending_reply,
        )
        action = detect_policy_action(
            message=request.message,
            intent=classifier_output.intent,
            entities=classifier_output.entities,
        )
        if action:
            context = load_subject_context(action["subject_id"])
            if action.get("lookup_number") is not None:
                context["lookup_number"] = action["lookup_number"]
            approval = create_approval(
                action_kind=action["action_kind"],
                subject_id=action["subject_id"],
                amount=action.get("amount"),
                reason=action["reason"],
                context=context,
                session_id=request.session_id,
                trace_id=trace_id,
            )
            # Telegram notification happens in the async streaming path
            # (streaming.py sends it after receiving pending_approval response)

            pending_msg = hitl_pending_reply(
                approval.action_kind,
                approval.subject_id,
                approval.amount,
                (approval.context or {}).get("lookup_number"),
                approval.reason,
            )
            decision = "pending_approval"
            reply = pending_msg
            reason_codes = ["hitl_pending"]
            packet = None
            stub_ticket_id = None

    meta = MetaInfo(
        ai_disclosure=True,
        disclosure_acknowledged=request.disclosure_acknowledged,
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
        approval=approval,
        meta=meta,
        error=None,
    )


def error_response(
    trace_id: str,
    code: str,
    message: str,
    request: ChatRequest,
    reason_codes: list[str] | None = None,
    steps: list[StepSummary] | None = None,
) -> ChatResponse:
    """Error envelope ChatResponse with minimal escalation packet."""
    if reason_codes is None:
        reason_codes = ["system_error"]

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
        stub_ticket_id=issue_stub_ticket_id(),
    )

    return ChatResponse(
        decision="escalate",
        reply=message,
        sources_used=[],
        sentiment="neutral",
        risk="medium",
        reason_codes=reason_codes,
        steps=steps or [],
        trace_id=trace_id,
        packet=packet,
        stub_ticket_id=packet.stub_ticket_id,
        meta=MetaInfo(
            ai_disclosure=True,
            disclosure_acknowledged=request.disclosure_acknowledged,
        ),
        error=ErrorDetail(code=code, message=message),
    )


def write_prompt_trace(
    trace_id: str,
    request: ChatRequest,
    response: ChatResponse,
    start_time: datetime,
    crew: Optional[CustomerSupportCrew],
    error: Optional[str] = None,
) -> None:
    """Write prompt trace JSON to LOG_DIR per SAD §2."""
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
            "disclosure_acknowledged": request.disclosure_acknowledged,
        },
        "steps": [step.model_dump() for step in response.steps],
        "decision": response.decision,
        "reason_codes": response.reason_codes,
        "meta": response.meta.model_dump(),
        "error": response.error.model_dump() if response.error else None,
        "model_tiers": {
            "low": crew.model_low if crew else "unknown",
            "mid": crew.model_mid if crew else "unknown",
        },
        "elapsed_ms": int((datetime.now() - start_time).total_seconds() * 1000),
    }

    if error:
        # SEC-08: store a short sanitized detail — no multi-line traces / paths dump
        safe = str(error).replace("\n", " ").strip()
        if len(safe) > 120:
            safe = safe[:117] + "..."
        # Drop obvious secret-looking substrings
        for marker in ("api_key", "API_KEY", "Bearer ", "sk-", "token="):
            if marker.lower() in safe.lower():
                safe = "redacted_error"
                break
        trace_data["error_detail"] = safe

    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, indent=2)
