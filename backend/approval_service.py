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
) -> ApprovalRequest:
    """Write a pending approval row and return the ApprovalRequest model."""
    approval_id = f"APR-{uuid.uuid4().hex[:8].upper()}"
    now = _now()

    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO approval_requests
            (id, session_id, trace_id, action_kind, subject_id, amount, reason,
             context_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
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
) -> str:
    n = lookup_number
    if n is not None:
        amt = f"${amount:.0f}" if amount is not None else f"${n}"
        if action_kind == "billing_credit":
            return (
                f"We're looking that up now. Request #{n} ({amt} credit) is with a manager for approval. "
                "Please wait a moment…"
            )
        if action_kind == "etf_waiver":
            return (
                f"We're looking that up now. Request #{n} (waive {amt} fee) is with a manager for approval. "
                "Please wait a moment…"
            )
        return (
            f"We're looking that up now. Request #{n} is with a manager for approval. Please wait a moment…"
        )
    label = ACTION_KIND_LABELS.get(action_kind, action_kind)
    if action_kind == "billing_credit":
        amt = f"${amount:.2f}" if amount else "your credit"
        return (
            f"Your {amt} credit request for account {subject_id} is being reviewed by a manager. "
            "Please wait a moment…"
        )
    if action_kind == "etf_waiver":
        return (
            f"Your ETF waiver request for account {subject_id} is being reviewed by a manager. "
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
    return (
        f"Your {label} request is being reviewed by a manager. Please wait a moment…"
    )


def approved_reply(
    action_kind: str,
    subject_id: str,
    amount: Optional[float],
    note: Optional[str],
    lookup_number: Optional[int] = None,
) -> str:
    n = lookup_number
    if action_kind == "billing_credit":
        amt = f"${amount:.2f}" if amount else "the requested credit"
        if n is not None:
            return f"Request #{n} approved. {amt} credit applied; it will appear on your next bill."
        return f"{amt} credit applied to {subject_id}; it will appear on your next bill."
    if action_kind == "etf_waiver":
        amt = f"${amount:.2f}" if amount else "the fee"
        if n is not None:
            return f"Request #{n} approved. {amt} early termination fee waived; your plan ends at the next cycle."
        return (
            f"Your early termination fee has been waived for account {subject_id}. "
            "Your plan will end at the next cycle."
        )
    if action_kind == "security_override":
        return (
            f"Your PIN reset has been authorised for account {subject_id}. "
            "A secure reset link has been sent to the email address on file."
        )
    if action_kind == "refund":
        amt = f"${amount:.2f}" if amount else "the requested amount"
        return f"Refund of {amt} approved for {subject_id}. It will post in 5–10 business days."
    if n is not None:
        return f"Request #{n} approved."
    return f"Your request for {subject_id} has been approved."


def denied_reply(
    action_kind: str,
    subject_id: str,
    note: Optional[str],
    lookup_number: Optional[int] = None,
) -> str:
    """If the manager supplied a reason, that is the customer-facing explanation."""
    n = lookup_number
    head = (
        f"Request #{n} was not approved."
        if n is not None
        else f"Your request for {subject_id} was not approved."
    )
    if note and note.strip():
        return f"{head} Reason: {note.strip()}"

    if action_kind == "billing_credit":
        return f"{head} Please contact billing for further review."
    if action_kind == "etf_waiver":
        return f"{head} The early termination fee applies per your contract terms."
    if action_kind == "security_override":
        return f"{head} Please visit a B-Mobile store with a valid photo ID."
    if action_kind == "refund":
        return f"{head} Please reply if you'd like to discuss further or speak with a specialist."
    return head


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
        )
    if approval.status == "denied":
        return denied_reply(
            approval.action_kind,
            approval.subject_id,
            approval.operator_note,
            n,
        )
    return pending_reply(
        approval.action_kind,
        approval.subject_id,
        approval.amount,
        n,
    )
