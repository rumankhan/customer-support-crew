# How to Run the Multi-Agent Support Application

Canonical overview of the product: [`README.md`](README.md).

Run both commands from the **repository root** (the folder that contains `backend/` and `frontend/`). Do not `cd backend` before uvicorn — the module path is `backend.main`.

## Quick Start

### Terminal 1: Backend (FastAPI + CrewAI)
```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

**Expected output:**
```
Initialising SQLite support database...
Initializing Customer Support Crew...
Crew initialized:
  Provider: ollama
  Model: gemma4:31b
Telegram manager bot: disabled (set TELEGRAM_ENABLED=true to activate)
INFO: Application startup complete.
```

**Backend URL:** http://127.0.0.1:8001
**Health check:** http://127.0.0.1:8001/health
**API docs:** http://127.0.0.1:8001/docs

---

### Terminal 2: Frontend (Next.js)
```bash
cd frontend
npm run dev
```

**Expected output:**
```
✓ Ready in 5s
- Local: http://localhost:3000
```

**Frontend URL:** http://localhost:3000

---

## Expected local ports

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend | http://127.0.0.1:8001 |
| Health | http://127.0.0.1:8001/health |
| Operator projector (read-only) | http://localhost:3000/operator |

If port 8000 is free you may use it, but this repo’s working demo uses **8001**. Set `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001` in `frontend/.env.local` and restart `npm run dev`.

## Access the Application

Open your browser and go to: **http://localhost:3000**

1. Click "I understand" to acknowledge the AI disclosure
2. Type your question (e.g., "How do I reset my PIN?")
3. Click "Get help"
4. Watch the 4-agent crew process your request in real time (SSE progress)!

---

## API endpoints

| Endpoint | Transport | Used by |
|----------|-----------|---------|
| `POST /api/chat/stream` | **SSE** (primary) | Browser chat — stage events, HITL wait, final `ChatResponse` |
| `POST /api/chat` | JSON (legacy) | Scripts, tests (`test_ollama_backend.py`) — does **not** wait for Telegram |
| `GET /health` | JSON | Liveness probe |
| `GET /api/approvals/pending` | JSON | Operator projector + Telegram `/pending` |
| `GET /api/approvals/history` | JSON | Recent decided requests |
| `GET /api/approvals/{id}/status` | JSON | Client poll fallback; includes `customer_reply` |
| `POST /api/approvals/{id}/decide` | JSON | Approve/Deny (Telegram bot uses this internally) |

The UI calls **`/api/chat/stream`** via a Next.js streaming proxy at `frontend/app/api/chat/stream/route.ts` (avoids rewrite buffering).

### SSE event types

| Event | Payload | Meaning |
|-------|---------|---------|
| `started` | `{ trace_id }` | Crew kickoff began |
| `stage` | `{ agent, status, summary? }` | Agent running or completed |
| `heartbeat` | `{ trace_id }` | Keep-alive every 15s |
| `approval_required` | `{ approval_id, reply_pending, response }` | HITL wait — manager notified on Telegram |
| `approval_decided` | `{ outcome, reply, response }` | Manager approved or denied |
| `approval_timeout` | `{ reply, response }` | No decision within `HITL_TIMEOUT_SECONDS` |
| `complete` | `{ response: ChatResponse }` | Success — render reply |
| `error` | `{ response: ChatResponse }` | Failure envelope — still a valid `ChatResponse` |

---

## Knowledge base (SQLite)

Live retrieval uses SQLite FTS5 at `backend/data/support.db` (seeded from `backend/kb/articles.csv`).

```bash
python -m backend.scripts.migrate_kb_csv_to_sqlite
```

The database is also created/seeded automatically when the backend starts.

---

## HITL manager approval (Telegram)

Policy actions (billing credit, ETF waiver) pause the customer chat until a manager approves or denies **in Telegram** — not on the customer page.

1. Create a bot with [@BotFather](https://t.me/BotFather) → `/newbot`
2. Put the token in `.env` as `TELEGRAM_BOT_TOKEN`
3. Message the bot, then run:

```bash
python -m backend.scripts.telegram_get_chat_id
```

4. Set `TELEGRAM_MANAGER_CHAT_ID` and `TELEGRAM_ENABLED=true`
5. Restart the backend

**Demo script (laptop = customer, phone = Telegram):**

| You type in chat | Manager does |
|------------------|--------------|
| `Apply a $25 credit to ACC-1001 for the outage last week` | Tap **Approve** |
| `Cancel my plan and waive the $150 ETF on ACC-2002` | Tap **Deny**, then send a reason or `/skip` |
| `credit for outage` | Same HITL path; **lookup #** 1–100 assigned (`REF-{n}`, proposed `$n`) |
| `can you waive my fee` | Same HITL path with lookup # |

After **Deny**, the bot asks for a reason. Type the reason, or `/skip` for contract boilerplate only. If a reason is sent, the customer sees `Request #N was not approved. Reason: {note}` — not extra ETF boilerplate.

Telegram commands: `/pending`, `/history`, `/detail APR-xxxxxxxx`

Read-only projector queue: [http://localhost:3000/operator](http://localhost:3000/operator) — no Approve/Deny buttons on the customer page.

If `TELEGRAM_ENABLED=false`, HITL requests resolve immediately with a “manager unavailable” message (no 300s hang).

---

## Configuration

### Environment Variables
All configuration is in **`.env`** at the project root:

```bash
# LLM Provider (Ollama Cloud or openai)
LLM_PROVIDER=ollama
OLLAMA_API_KEY=your-api-key-here
OLLAMA_MODEL=gemma4:31b

# Frontend → backend (also copy into frontend/.env.local)
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001

# Crew wall-clock timeout (seconds) — SSE stream and POST /api/chat
CHAT_TIMEOUT_SECONDS=180

# SQLite KB + stubs + approval queue (created on backend start)
KB_DB_PATH=backend/data/support.db
KB_SIMILARITY_FLOOR=0.35

# Telegram HITL (see section above)
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_MANAGER_CHAT_ID=
HITL_TIMEOUT_SECONDS=300
```

The browser aborts the SSE request at **~500s** so a 300s HITL wait plus crew time can finish. Restart the backend after changing Telegram env vars.

---

## Guardrails (2026-08-27)

Customer-facing behavior is constrained by **YAML crew rules** plus **deterministic post-processing** in `backend/chat_service.py` and **UI gates** in the frontend. These guardrails prevent unnecessary specialist handoffs and misleading copy.

### When we escalate (specialist handoff)

| Trigger | Example |
|---------|---------|
| Customer checks **I'd rather talk to a person** | Path C — billing complaint + `request_human=true` |
| **Negative** sentiment with risk / gap / refused | Frustrated customer |
| **High** risk | Strong frustration language |
| Hard failures | `timeout`, `system_error`, `kb_unavailable` |

### When we resolve in-chat (no specialist banner)

| Trigger | Example | Backend | UI |
|---------|---------|---------|-----|
| **Greeting** / small talk | `"hello"` | Rule 0 + `apply_greeting_resolve_override()` | No STUB; no specialist banner (neutral) |
| **Low urgency** + neutral/positive + low/medium risk | Calm question, KB gap only | Rule 0b + `apply_low_urgency_resolve_override()` | No specialist banner if sentiment neutral |
| **Out of scope** (not B-Mobile mobile/account) | `"What is the capital of France?"` | Rule 0a + `apply_out_of_scope_reply_policy()` | Scope-only reply; **no** “speak with a human agent” |

### UI guardrails

| Rule | Implementation |
|------|----------------|
| Neutral sentiment → never show “connecting you with a specialist” | `shouldShowEscalateNotice()` in `frontend/lib/uiCopy.ts` |
| SSE must deliver final `complete` event | `frontend/lib/chatStream.ts` — flush final buffer, CRLF-safe parser |

### Key files

| Layer | File |
|-------|------|
| Crew rules | `backend/config/tasks.yaml` |
| Deterministic overrides | `backend/chat_service.py` |
| SSE stream | `backend/streaming.py`, `frontend/lib/chatStream.ts` |
| Specialist banner | `frontend/components/ChatWindow.tsx` |

Full technical detail: [`project-context/2.build/backend.md`](project-context/2.build/backend.md) § Guardrails, [`project-context/2.build/integration.md`](project-context/2.build/integration.md) § Guardrails.

---

## Troubleshooting

### Backend won't start?
- Check Python version: `python --version` (need 3.10+)
- Reinstall dependencies: `pip install -r backend/requirements.txt`
- Check port 8001: `netstat -ano | findstr :8001`
- If port 8000 is in use by Docker/WSL, use 8001 (default in `.env`)

### Frontend won't start?
- Check Node version: `node --version` (need 18+)
- Reinstall dependencies: `npm install` (in frontend/)
- Check port 3000: `netstat -ano | findstr :3000`

### "system_error" in responses?
- Verify `.env` file exists at project root
- Check `OLLAMA_MODEL=gemma4:31b` (must match a model available on your Ollama account)
- Check backend logs for specific errors

### Telegram never pings the manager?
- `TELEGRAM_ENABLED=true` and restart the backend (lifespan starts polling)
- Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_MANAGER_CHAT_ID` (group IDs are often **negative**)
- Run `python -m backend.scripts.telegram_get_chat_id` after messaging the bot
- Customer chat uses **SSE** (`/api/chat/stream`). Legacy `POST /api/chat` does not wait for Telegram

### HITL hangs for five minutes?
- Manager must tap Approve/Deny. On Deny, send a reason or `/skip`
- If Telegram is off, requests should not hang — they resolve as manager unavailable
- Browser abort is ~500s; backend wait is `HITL_TIMEOUT_SECONDS` (default 300)

---

## Stopping the Servers

Press **Ctrl+C** in each terminal window to stop the servers.
