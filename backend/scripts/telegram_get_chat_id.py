"""
Print your Telegram chat ID so you can set TELEGRAM_MANAGER_CHAT_ID.

1. Create a bot with @BotFather and copy the token into TELEGRAM_BOT_TOKEN.
2. Send any message to the bot.
3. Run from project root:

    python -m backend.scripts.telegram_get_chat_id
"""
from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set in .env")
        return 1
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        data = httpx.get(url, timeout=20).json()
    except Exception as exc:
        print(f"Failed to call Telegram: {exc}")
        return 1
    if not data.get("ok"):
        print(f"Telegram error: {data}")
        return 1
    updates = data.get("result") or []
    if not updates:
        print("No updates yet. Open the bot in Telegram, send /start, then run this script again.")
        return 1
    seen: set[str] = set()
    print("Recent chats (use one as TELEGRAM_MANAGER_CHAT_ID):")
    for update in updates:
        msg = update.get("message") or update.get("callback_query", {}).get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None or str(chat_id) in seen:
            continue
        seen.add(str(chat_id))
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "unknown"
        kind = chat.get("type", "unknown")
        print(f"  {chat_id}  ({kind}: {title})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
