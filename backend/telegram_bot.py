"""
Telegram bot for manager approval notifications.
- Sends inline Approve/Deny buttons on each new HITL request
- Handles /pending, /history, /detail commands
- Long-polls Telegram API (no public URL needed for local dev)

Set env vars:
  TELEGRAM_BOT_TOKEN       - from @BotFather
  TELEGRAM_MANAGER_CHAT_ID - manager DM or group chat ID
  TELEGRAM_ENABLED         - "true" to activate (default: false)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from backend.models import ACTION_KIND_LABELS, ApprovalRequest

logger = logging.getLogger(__name__)

# chat_id → {approval_id, message_id, user_id} while waiting for a deny reason
_pending_deny_note: Dict[str, Dict[str, Any]] = {}

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT = 30  # long-poll timeout in seconds


def is_enabled() -> bool:
    return os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"


def _is_enabled() -> bool:
    return is_enabled()


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _manager_chat_id() -> str:
    return os.getenv("TELEGRAM_MANAGER_CHAT_ID", "")


def _url(method: str) -> str:
    return TELEGRAM_API.format(token=_token(), method=method)


# ─────────────────────────────────────────────────────────────────────────────
# Low-level Telegram HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _post(method: str, payload: Dict[str, Any]) -> Optional[Dict]:
    if not _token():
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping %s", method)
        return None
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            r = await client.post(_url(method), json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.error("Telegram %s failed: %s", method, exc)
        return None


async def _get(method: str, params: Dict[str, Any] | None = None) -> Optional[Dict]:
    if not _token():
        return None
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            r = await client.get(_url(method), params=params or {})
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.error("Telegram %s failed: %s", method, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Notification sender
# ─────────────────────────────────────────────────────────────────────────────

def _build_notification_text(approval: ApprovalRequest) -> str:
    label = ACTION_KIND_LABELS.get(approval.action_kind, approval.action_kind)
    ctx = approval.context or {}

    lines = [
        f"🔔 *Approval required — {label}*",
        "",
    ]
    lookup = ctx.get("lookup_number")
    if lookup is not None:
        lines.append(f"*Lookup #:* `{lookup}`  ← approve/deny this number")
        lines.append("")
    lines.append(f"*Account/Order:* `{approval.subject_id}`")
    if approval.amount is not None:
        lines.append(f"*Amount:* ${approval.amount:.2f}")
    if approval.reason:
        lines.append(f"*Reason:* {approval.reason[:200]}")

    # Context flags
    if ctx:
        lines.append("\n*Context:*")
        if ctx.get("tenure_years"):
            lines.append(f"• Tenure: {ctx['tenure_years']} year(s)")
        if ctx.get("outage_date"):
            lines.append(f"• Outage logged: {ctx['outage_date']}")
        if ctx.get("etf_amount"):
            lines.append(f"• ETF: ${ctx['etf_amount']:.2f}")
        if ctx.get("security_flag"):
            lines.append("• ⚠️ Security flag active")
        if ctx.get("eligible_for_refund") is False:
            lines.append("• ⚠️ Order may be outside return window")
        if ctx.get("notes"):
            lines.append(f"• {ctx['notes'][:100]}")

    lines.append(f"\n`Ref: {approval.id}`")
    return "\n".join(lines)


def _build_inline_keyboard(approval_id: str) -> Dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"approve:{approval_id}"},
                {"text": "❌ Deny", "callback_data": f"deny:{approval_id}"},
            ]
        ]
    }


async def notify_manager(approval: ApprovalRequest) -> Optional[int]:
    """
    Send approval request notification to manager chat.
    Returns the Telegram message_id on success, None on failure.
    """
    if not _is_enabled():
        logger.info(
            "Telegram disabled — approval %s would notify manager (mock mode)",
            approval.id,
        )
        return None

    chat_id = _manager_chat_id()
    if not chat_id:
        logger.warning("TELEGRAM_MANAGER_CHAT_ID not set — cannot notify manager")
        return None

    text = _build_notification_text(approval)
    result = await _post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": _build_inline_keyboard(approval.id),
        },
    )
    if result and result.get("ok"):
        msg_id = result["result"]["message_id"]
        logger.info("Telegram: notified manager for %s (msg_id=%s)", approval.id, msg_id)
        return msg_id
    return None


async def update_notification(message_id: int, approval_id: str, outcome: str, note: Optional[str]) -> None:
    """Edit the Telegram notification message to show the outcome."""
    if not _is_enabled():
        return
    chat_id = _manager_chat_id()
    if not chat_id or not message_id:
        return

    icon = "✅" if outcome == "approved" else "❌"
    caption = f"{icon} *{outcome.upper()}*"
    if note:
        caption += f"\nNote: _{note}_"
    caption += f"\n`{approval_id}`"

    await _post(
        "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": caption,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": []},
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Command responses
# ─────────────────────────────────────────────────────────────────────────────

async def _send_text(chat_id: str, text: str) -> None:
    await _post("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})


async def _handle_pending(chat_id: str) -> None:
    from backend.approval_service import list_pending
    items = list_pending()
    if not items:
        await _send_text(chat_id, "✅ No pending approvals.")
        return
    lines = [f"*{len(items)} pending approval(s):*\n"]
    for a in items:
        label = ACTION_KIND_LABELS.get(a.action_kind, a.action_kind)
        amt = f" ${a.amount:.2f}" if a.amount else ""
        lines.append(f"• `{a.id}` — {label}{amt} for `{a.subject_id}`")
    await _send_text(chat_id, "\n".join(lines))


async def _handle_history(chat_id: str) -> None:
    from backend.approval_service import list_history
    items = list_history(10)
    if not items:
        await _send_text(chat_id, "No recent decisions.")
        return
    lines = ["*Last 10 decisions:*\n"]
    for a in items:
        icon = "✅" if a.status == "approved" else "❌"
        label = ACTION_KIND_LABELS.get(a.action_kind, a.action_kind)
        ts = (a.decided_at or "")[:16]
        lines.append(f"{icon} `{a.id}` — {label} / `{a.subject_id}` @ {ts}")
    await _send_text(chat_id, "\n".join(lines))


async def _handle_detail(chat_id: str, approval_id: str) -> None:
    from backend.approval_service import get_approval
    a = get_approval(approval_id.upper())
    if not a:
        await _send_text(chat_id, f"❓ Approval `{approval_id}` not found.")
        return
    text = _build_notification_text(a)
    if a.status == "pending":
        await _post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": _build_inline_keyboard(a.id),
            },
        )
    else:
        icon = "✅" if a.status == "approved" else "❌"
        await _send_text(chat_id, f"{text}\n\nStatus: {icon} {a.status.upper()}")


# ─────────────────────────────────────────────────────────────────────────────
# Callback / message handler
# ─────────────────────────────────────────────────────────────────────────────

async def handle_update(update: Dict[str, Any]) -> None:
    """Dispatch a single Telegram update (message or callback_query)."""
    manager_id = _manager_chat_id()

    # ── Inline keyboard callback ──────────────────────────────────────────────
    if "callback_query" in update:
        cq = update["callback_query"]
        sender_chat = str(cq.get("message", {}).get("chat", {}).get("id", ""))
        sender_user = str(cq.get("from", {}).get("id", ""))

        # Acknowledge the callback
        await _post("answerCallbackQuery", {"callback_query_id": cq["id"]})

        if manager_id and sender_chat != manager_id:
            logger.warning("Ignoring callback from unauthorized chat %s", sender_chat)
            return

        data = cq.get("data", "")
        msg_id = cq.get("message", {}).get("message_id")

        if data.startswith("approve:") or data.startswith("deny:"):
            action, approval_id = data.split(":", 1)
            if action == "deny":
                _pending_deny_note[sender_chat] = {
                    "approval_id": approval_id,
                    "message_id": msg_id,
                    "user_id": sender_user,
                }
                await _send_text(
                    sender_chat,
                    f"Reply with a deny reason for `{approval_id}`, or send /skip to deny without a note.",
                )
                return

            from backend.approval_service import decide_approval
            updated = decide_approval(
                approval_id,
                action,
                decided_by=f"telegram:{sender_user}",
                telegram_message_id=msg_id,
            )
            if updated:
                await update_notification(msg_id, approval_id, "approved", None)
                logger.info("Approval %s approved by telegram:%s", approval_id, sender_user)
            else:
                await _send_text(sender_chat, f"⚠️ Approval `{approval_id}` already decided or not found.")
        return

    # ── Text command ──────────────────────────────────────────────────────────
    if "message" in update:
        msg = update["message"]
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()

        if manager_id and chat_id != manager_id:
            return  # ignore messages from non-manager chats

        pending_note = _pending_deny_note.get(chat_id)
        if pending_note and not text.startswith("/pending") and not text.startswith("/history") and not text.startswith("/detail") and not text.startswith("/start") and not text.startswith("/help"):
            from backend.approval_service import decide_approval
            note = None if text == "/skip" else text[:400]
            updated = decide_approval(
                pending_note["approval_id"],
                "deny",
                operator_note=note,
                decided_by=f"telegram:{pending_note['user_id']}",
                telegram_message_id=pending_note.get("message_id"),
            )
            _pending_deny_note.pop(chat_id, None)
            if updated:
                msg_id = pending_note.get("message_id")
                if msg_id:
                    await update_notification(
                        int(msg_id),
                        pending_note["approval_id"],
                        "denied",
                        note,
                    )
                await _send_text(chat_id, f"❌ Denied `{pending_note['approval_id']}`.")
            else:
                await _send_text(chat_id, f"⚠️ Approval `{pending_note['approval_id']}` already decided or not found.")
            return

        if text == "/pending":
            await _handle_pending(chat_id)
        elif text == "/history":
            await _handle_history(chat_id)
        elif text.startswith("/detail"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                await _handle_detail(chat_id, parts[1].strip())
            else:
                await _send_text(chat_id, "Usage: /detail APR-XXXXXXXX")
        elif text == "/start" or text == "/help":
            await _send_text(
                chat_id,
                "🤖 *B-Mobile Manager Bot*\n\n"
                "Commands:\n"
                "• /pending — pending approvals\n"
                "• /history — last 10 decisions\n"
                "• /detail APR-xxx — request details\n\n"
                "Tap ✅ or ❌ buttons on notifications to approve/deny.",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Long-polling loop (runs in FastAPI lifespan)
# ─────────────────────────────────────────────────────────────────────────────

async def run_polling() -> None:
    """
    Long-poll the Telegram getUpdates endpoint indefinitely.
    Call this as a background asyncio task during app lifespan.
    """
    if not _is_enabled():
        logger.info("Telegram bot disabled (TELEGRAM_ENABLED != true). Skipping polling.")
        return

    if not _token():
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot will not start.")
        return

    logger.info("Starting Telegram long-polling…")
    offset = 0

    while True:
        try:
            result = await _get(
                "getUpdates",
                {"timeout": POLL_TIMEOUT, "offset": offset, "allowed_updates": ["message", "callback_query"]},
            )
            if result and result.get("ok"):
                for update in result.get("result", []):
                    offset = update["update_id"] + 1
                    try:
                        await handle_update(update)
                    except Exception as exc:
                        logger.error("Error handling update %s: %s", update.get("update_id"), exc)
        except asyncio.CancelledError:
            logger.info("Telegram polling cancelled.")
            break
        except Exception as exc:
            logger.error("Telegram polling error: %s — retrying in 5s", exc)
            await asyncio.sleep(5)
