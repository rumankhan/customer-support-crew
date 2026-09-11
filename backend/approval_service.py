"""
Approval service: CRUD for HITL approval requests.
Manages approval_requests table and async waiters so SSE streams can be
woken up when a Telegram callback arrives.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.db import get_connection
from backend.models import ApprovalRequest, ACTION_KIND_LABELS


# ── In-memory waiters ─────────────────────────────────────────────────────────
# Maps approval_id → asyncio.Event so a waiting SSE task can be woken on decision.
_waiters: Dict[str, asyncio.Event] = {}

HITL_TIMEOUT_SECONDS = 300  # 5 minutes


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_crew_trace_url(url: Optional[str]) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    if cleaned.startswith("https://app.crewai.com/"):
        return cleaned
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Policy-action detection
# ─────────────────────────────────────────────────────────────────────────────

_ACC_RE = re.compile(r'\bACC-\d+\b', re.IGNORECASE)
_ORD_RE = re.compile(r'\bORD-\d+\b', re.IGNORECASE)
_AMOUNT_RE = re.compile(r'\$\s*(\d+(?:\.\d{1,2})?)')


def detect_policy_action(
    message: str,
    intent: str,
    entities: List[str],
) -> Optional[Dict[str, Any]]:
    """
    Return a dict with action_kind, subject_id, amount, reason, lookup_number
    if the message is a policy action request, else return None.

    Credit / fee-waiver requests do not require an account ID. When missing,
    we assign a lookup number 1–100 (also used as the proposed dollar amount).
    """
    lower = message.lower()
    intent_lower = (intent or "").lower()
    entities_upper = [e.upper() for e in (entities or [])]

    def find_account() -> Optional[str]:
        m = _ACC_RE.search(message)
        if m:
            return m.group(0).upper()
        for e in entities_upper:
            if _ACC_RE.match(e):
                return e
        return None

    def find_order() -> Optional[str]:
        m = _ORD_RE.search(message)
        if m:
            return m.group(0).upper()
        for e in entities_upper:
            if _ORD_RE.match(e):
                return e
        return None

    def find_amount() -> Optional[float]:
        m = _AMOUNT_RE.search(message)
        return float(m.group(1)) if m else None

    def lookup_bundle(account: Optional[str], amount: Optional[float]) -> Dict[str, Any]:
        if account and amount is not None:
            return {"subject_id": account, "amount": amount}
        n = random.randint(1, 100)
        return {
            "subject_id": account or f"REF-{n}",
            "amount": amount if amount is not None else float(n),
            "lookup_number": n,
        }

    def is_info_question() -> bool:
        if any(
            k in lower
            for k in (
                "credit for",
                "waive",
                "can you",
                "please",
                "apply",
                "give me",
                "outage",
            )
        ):
            return False
        return bool(re.match(r"^(what is|what are|how do i|how can i)\b", lower.strip()))

    if is_info_question():
        return None

    # ── billing_credit ────────────────────────────────────────────────────────
    wants_credit = (
        "credit" in lower
        or "goodwill" in lower
        or "compensation" in lower
        or ("outage" in lower and any(w in lower for w in ("bill", "billing", "credit", "compensat")))
    )
    if wants_credit and "credit card" not in lower:
        bundle = lookup_bundle(find_account(), find_amount())
        return {
            "action_kind": "billing_credit",
            "reason": message[:300],
            **bundle,
        }

    # ── etf_waiver ────────────────────────────────────────────────────────────
    etf_kw = any(kw in lower for kw in ("etf", "early termination", "cancellation fee", "termination fee"))
    cancel_kw = any(kw in lower for kw in ("cancel", "cancelling", "terminate"))
    waive_kw = any(kw in lower for kw in ("waive", "waiver", "remove", "drop"))
    fee_kw = any(kw in lower for kw in ("fee", "etf", "charge", "termination"))
    if (waive_kw and fee_kw) or (etf_kw and waive_kw) or (cancel_kw and waive_kw):
        bundle = lookup_bundle(find_account(), find_amount())
        return {
            "action_kind": "etf_waiver",
            "reason": message[:300],
            **bundle,
        }

    # ── security_override ─────────────────────────────────────────────────────
    pin_kw = "pin" in lower or "password" in lower
    lost_sim_kw = any(kw in lower for kw in ("lost sim", "no sim", "without sms", "can't receive", "cannot receive"))
    if pin_kw and lost_sim_kw and any(kw in lower for kw in ("reset", "bypass", "override", "without")):
        acc = find_account()
        if acc:
            return {
                "action_kind": "security_override",
                "subject_id": acc,
                "amount": None,
                "reason": message[:300],
            }

    # ── refund ────────────────────────────────────────────────────────────────
    refund_kw = any(kw in lower for kw in ("refund", "process return", "return my"))
    action_kw = any(kw in lower for kw in ("process", "issue", "initiate", "start", "submit"))
    if refund_kw and (action_kw or "refund" in intent_lower):
        ord_id = find_order()
        if ord_id:
            return {
                "action_kind": "refund",
                "subject_id": ord_id,
                "amount": find_amount(),
                "reason": message[:300],
            }

    # ── roaming_exception ─────────────────────────────────────────────────────
    roam_kw = any(kw in lower for kw in ("roaming", "roam"))
    free_kw = any(kw in lower for kw in ("free", "no charge", "waive", "exception", "complimentary"))
    if roam_kw and free_kw:
        acc = find_account()
        if acc:
            return {
                "action_kind": "roaming_exception",
                "subject_id": acc,
                "amount": None,
                "reason": message[:300],
            }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

def create_approval(
    *,
    action_kind: str,
    subject_id: str,
    amount: Optional[float],
    reason: str,
    context: Dict[str, Any],
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    crew_trace_url: Optional[str] = None,
) -> ApprovalRequest:
    """Write a pending approval row and return the ApprovalRequest model."""
    approval_id = f"APR-{uuid.uuid4().hex[:8].upper()}"
    now = _now()
    amp_url = _safe_crew_trace_url(crew_trace_url)

    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO approval_requests
            (id, session_id, trace_id, action_kind, subject_id, amount, reason,
             context_json, status, created_at, crew_trace_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                approval_id,
                session_id,
                trace_id,
                action_kind,
                subject_id,
                amount,
                reason,
                json.dumps(context),
                now,
                amp_url,
            ),
        )
    conn.close()

    return ApprovalRequest(
        id=approval_id,
        action_kind=action_kind,
        subject_id=subject_id,
        amount=amount,
        reason=reason,
        status="pending",
        context=context,
        created_at=now,
        trace_id=trace_id,
        crew_trace_url=amp_url,
    )


def decide_approval(
    approval_id: str,
    decision: str,  # "approve" | "deny"
    operator_note: Optional[str] = None,
    decided_by: Optional[str] = None,
    telegram_message_id: Optional[int] = None,
) -> bool:
    """
    Update approval status. Returns True if updated, False if not found / already decided.
    Wakes any SSE waiter registered for this approval_id.
    """
    new_status = "approved" if decision == "approve" else "denied"
    now = _now()

    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            UPDATE approval_requests
            SET status = ?, operator_note = ?, decided_by = ?,
                telegram_message_id = COALESCE(?, telegram_message_id),
                decided_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (new_status, operator_note, decided_by, telegram_message_id, now, approval_id),
        )
        updated = cur.rowcount > 0
    conn.close()

    if updated:
        _wake_waiter(approval_id)
    return updated


def get_approval(approval_id: str) -> Optional[ApprovalRequest]:
    """Fetch one approval request by ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_model(row)


def list_pending() -> List[ApprovalRequest]:
    """Return all pending approvals, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM approval_requests WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_model(r) for r in rows]


def list_history(limit: int = 10) -> List[ApprovalRequest]:
    """Return recent decided approvals, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM approval_requests WHERE status != 'pending' ORDER BY decided_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [_row_to_model(r) for r in rows]


def _row_value(row, key: str, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _row_to_model(row) -> ApprovalRequest:
    ctx = {}
    try:
        if row["context_json"]:
            ctx = json.loads(row["context_json"])
    except (json.JSONDecodeError, TypeError):
        pass
    return ApprovalRequest(
        id=row["id"],
        action_kind=row["action_kind"],
        subject_id=row["subject_id"],
        amount=row["amount"],
        reason=row["reason"] or "",
        status=row["status"],
        operator_note=row["operator_note"],
        context=ctx,
        created_at=row["created_at"],
        decided_at=row["decided_at"],
        decided_by=row["decided_by"],
        trace_id=_row_value(row, "trace_id"),
        crew_trace_url=_safe_crew_trace_url(_row_value(row, "crew_trace_url")),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Async waiter helpers
# ─────────────────────────────────────────────────────────────────────────────

def register_waiter(approval_id: str) -> asyncio.Event:
    """Create and store an asyncio.Event for this approval_id."""
    event = asyncio.Event()
    _waiters[approval_id] = event
    return event


def _wake_waiter(approval_id: str) -> None:
    event = _waiters.get(approval_id)
    if event:
        event.set()


def remove_waiter(approval_id: str) -> None:
    _waiters.pop(approval_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# Stub account context builder (for Telegram notification)
# ─────────────────────────────────────────────────────────────────────────────

def load_subject_context(subject_id: str) -> Dict[str, Any]:
    """Load stub account or order context for notification and approval row."""
    conn = get_connection()
    if subject_id.startswith("ACC-"):
        row = conn.execute(
            "SELECT * FROM stub_accounts WHERE id = ?", (subject_id.upper(),)
        ).fetchone()
        conn.close()
        if row:
            return {
                "type": "account",
                "plan": row["plan"],
                "tenure_years": row["tenure_years"],
                "etf_amount": row["etf_amount"],
                "outage_date": row["outage_date"],
                "security_flag": bool(row["security_flag"]),
                "notes": row["notes"],
            }
    elif subject_id.startswith("ORD-"):
        row = conn.execute(
            "SELECT * FROM stub_orders WHERE id = ?", (subject_id.upper(),)
        ).fetchone()
        conn.close()
        if row:
            return {
                "type": "order",
                "product": row["product"],
                "amount": row["amount"],
                "purchase_date": row["purchase_date"],
                "eligible_for_refund": bool(row["eligible_for_refund"]),
                "notes": row["notes"],
            }
    conn.close()
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Customer-facing copy helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_dollars(amount: Optional[float], fallback: Optional[int] = None) -> Optional[str]:
    value = amount if amount is not None else (float(fallback) if fallback is not None else None)
    if value is None:
        return None
    if abs(value - round(value)) < 1e-9:
        return f"${round(value):.0f}"
    return f"${value:.2f}"


def _reason_clause(reason: Optional[str]) -> str:
    """Short 'for …' clause from the customer's message, e.g. 'the outage last week'."""
    raw = (reason or "").strip()
    if not raw:
        return ""
    match = re.search(r"\bfor\s+(.+)$", raw, re.IGNORECASE)
    clause = match.group(1) if match else ""
    if not clause:
        because = re.search(r"\bbecause(?:\s+of)?\s+(.+)$", raw, re.IGNORECASE)
        clause = because.group(1) if because else ""
    clause = re.sub(r"\b(?:ACC|ORD|REF)-\w+\b", "", clause, flags=re.IGNORECASE)
    clause = re.sub(r"\$\s*\d+(?:\.\d+)?", "", clause)
    clause = re.sub(r"\s+", " ", clause).strip(" \t.,!?;:")
    if not clause:
        return ""
    if re.match(r"^(the|a|an|my|our|this|that|last)\b", clause, re.IGNORECASE):
        return clause
    return f"the {clause}"


def _treat_as_credit(action_kind: str, reason: Optional[str]) -> bool:
    if action_kind == "billing_credit":
        return True
    text = (reason or "").lower()
    return "credit" in text and "credit card" not in text


def _lookup_number(context: Optional[Dict[str, Any]], subject_id: str) -> Optional[int]:
    ctx = context or {}
    raw = ctx.get("lookup_number")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw == int(raw):
        return int(raw)
    if subject_id.startswith("REF-"):
        try:
            return int(subject_id.split("-", 1)[1])
        except ValueError:
            return None
    return None


def pending_reply(
    action_kind: str,
    subject_id: str,
    amount: Optional[float],
    lookup_number: Optional[int] = None,
    reason: Optional[str] = None,
) -> str:
    amt = _format_dollars(amount, lookup_number)
    clause = _reason_clause(reason)
    if _treat_as_credit(action_kind, reason):
        if amt and clause:
            return (
                f"We're looking that up now. A manager is reviewing your request to credit you "
                f"{amt} for {clause}. Please wait a moment…"
            )
        if amt:
            return (
                f"We're looking that up now. A manager is reviewing your {amt} credit request. "
                "Please wait a moment…"
            )
        return (
            "We're looking that up now. A manager is reviewing your credit request. "
            "Please wait a moment…"
        )
    if action_kind == "etf_waiver":
        fee = amt or "the fee"
        return (
            f"We're looking that up now. A manager is reviewing your request to waive {fee}. "
            "Please wait a moment…"
        )
    if action_kind == "security_override":
        return (
            f"Your PIN override request for account {subject_id} is being reviewed. "
            "This requires manager authorisation. Please wait…"
        )
    if action_kind == "refund":
        return (
            f"Your refund request for {subject_id} is being reviewed by a manager. "
            "Please wait a moment…"
        )
    label = ACTION_KIND_LABELS.get(action_kind, action_kind)
    return f"Your {label} request is being reviewed by a manager. Please wait a moment…"


def approved_reply(
    action_kind: str,
    subject_id: str,
    amount: Optional[float],
    note: Optional[str],
    lookup_number: Optional[int] = None,
    reason: Optional[str] = None,
) -> str:
    amt = _format_dollars(amount, lookup_number)
    clause = _reason_clause(reason)
    if _treat_as_credit(action_kind, reason):
        if amt and clause:
            return (
                f"Your request was approved and we are crediting you {amt} for {clause}."
            )
        if amt:
            return f"Your request was approved and we are crediting you {amt}."
        if clause:
            return f"Your request was approved and we are applying a credit for {clause}."
        return "Your request was approved and we are applying the credit."
    if action_kind == "etf_waiver":
        fee = amt or "the early termination fee"
        if clause:
            return (
                f"Your request was approved. We have waived {fee} for {clause}."
            )
        return f"Your request was approved. We have waived {fee}."
    if action_kind == "security_override":
        return (
            f"Your PIN reset has been authorised for account {subject_id}. "
            "A secure reset link has been sent to the email address on file."
        )
    if action_kind == "refund":
        refund_amt = amt or "the requested amount"
        return f"Your request was approved. A refund of {refund_amt} will post for {subject_id} in 5–10 business days."
    return "Your request was approved."


def denied_reply(
    action_kind: str,
    subject_id: str,
    amount: Optional[float],
    note: Optional[str],
    lookup_number: Optional[int] = None,
    reason: Optional[str] = None,
) -> str:
    """Mirror approved copy: amount + customer reason, no request number."""
    amt = _format_dollars(amount, lookup_number)
    clause = _reason_clause(reason)
    manager = f" Reason: {note.strip()}" if note and note.strip() else ""

    if _treat_as_credit(action_kind, reason):
        if amt and clause:
            body = (
                f"Your request was not approved. We are unable to credit you {amt} "
                f"for {clause}."
            )
        elif amt:
            body = f"Your request was not approved. We are unable to credit you {amt}."
        elif clause:
            body = (
                f"Your request was not approved. We are unable to apply a credit for {clause}."
            )
        else:
            body = "Your request was not approved. We are unable to apply the requested credit."
        return body + manager

    if action_kind == "etf_waiver":
        fee = amt or "the early termination fee"
        body = f"Your request was not approved. We are unable to waive {fee}."
        if manager:
            return body + manager
        return f"{body} The early termination fee applies per your contract terms."
    if action_kind == "security_override":
        return (
            "Your request was not approved. Please visit a B-Mobile store with a valid photo ID."
            + manager
        )
    if action_kind == "refund":
        return (
            "Your request was not approved. Please reply if you'd like to discuss further "
            "or speak with a specialist."
            + manager
        )
    return "Your request was not approved." + manager


def customer_reply_for(approval: ApprovalRequest) -> str:
    """Customer-facing copy for pending / approved / denied."""
    n = _lookup_number(approval.context, approval.subject_id)
    if approval.status == "approved":
        return approved_reply(
            approval.action_kind,
            approval.subject_id,
            approval.amount,
            approval.operator_note,
            n,
            approval.reason,
        )
    if approval.status == "denied":
        return denied_reply(
            approval.action_kind,
            approval.subject_id,
            approval.amount,
            approval.operator_note,
            n,
            approval.reason,
        )
    return pending_reply(
        approval.action_kind,
        approval.subject_id,
        approval.amount,
        n,
        approval.reason,
    )
