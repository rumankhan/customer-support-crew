# How to Run the Multi-Agent Support Application

Canonical overview of the product: [`README.md`](README.md).  
Full deliver runbook (env matrix, rollback, access control): [`project-context/3.deliver/deploy.md`](project-context/3.deliver/deploy.md).

Run commands from the **repository root** (the folder that contains `backend/` and `frontend/`), unless a step says otherwise. Do not `cd backend` before uvicorn — the module path is `backend.main`.

| Mode | When to use |
|------|-------------|
| **Local (default)** | Day-to-day demo and development — two terminals |
| **Docker Compose** | Packaged demo — `Dockerfile` + `docker-compose.yml` |

Both modes expect ports **3000** (frontend) and **8001** (backend) on localhost.

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Python 3.10+ | 3.11 matches the backend Docker image |
| Node.js ≥ 20 + npm | See `frontend/package.json` `engines` |
| LLM credentials | Fill `.env` for `LLM_PROVIDER` (`ollama` or `openai`) |
| Docker Desktop (optional) | Only for Compose |

### First-time setup (local)

```bash
# From repository root
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

pip install -r backend/requirements.txt
copy .env.example .env
# Edit .env — set OLLAMA_API_KEY or OPENAI_API_KEY, OPERATOR_API_KEY, etc.
# Never commit .env

cd frontend
npm ci
copy .env.example .env.local
# Ensure NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
# Use the same OPERATOR_API_KEY as root .env
cd ..
```

On macOS/Linux use `cp` instead of `copy`.

SQLite KB is created/seeded automatically when the backend starts (from `backend/kb/articles.csv`). Optional explicit migrate:

```bash
python -m backend.scripts.migrate_kb_csv_to_sqlite
```

---

## Quick Start (local)

### Terminal 1: Backend (FastAPI + CrewAI)

```bash
# Activate .venv first if you use one
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

## Quick Start (Docker Compose)

Requires a filled root **`.env`** (from `.env.example`). Compose publishes only on loopback (`127.0.0.1`) to reduce accidental LAN exposure.

Stop any local uvicorn / `npm run dev` on **8001** / **3000** first.

```bash
# From repository root
docker compose up --build
```

| Service | Published URL |
|---------|----------------|
| Frontend | http://127.0.0.1:3000 |
| Backend | http://127.0.0.1:8001 |
| Health | http://127.0.0.1:8001/health |

Inside the Compose network the frontend proxies to `http://backend:8001` (set at image build time). You still open the app in the browser at **http://127.0.0.1:3000**.

Useful commands:

```bash
docker compose up --build -d    # detached
docker compose ps
docker compose logs -f backend
docker compose down             # stop containers
```

Volumes mount Prompt Trace logs (`project-context/2.build/logs`), SQLite data (`backend/data`), and the KB CSV (`backend/kb`, read-only).

---

## Expected local ports

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 (or http://127.0.0.1:3000) |
| Backend | http://127.0.0.1:8001 |
| Health | http://127.0.0.1:8001/health |
| Operator projector (read-only) | http://localhost:3000/operator |

If port 8000 is free you may use it, but this repo’s working demo uses **8001**. For **local** mode, set `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001` in `frontend/.env.local` and restart `npm run dev`. Compose uses `http://backend:8001` for the FE↔BE link automatically.

## Access the Application

Open your browser and go to: **http://localhost:3000** (or **http://127.0.0.1:3000** for Compose)

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
| `GET /api/approvals/pending` | JSON | Operator projector — requires `X-Operator-Key` |
| `GET /api/approvals/history` | JSON | Recent decided requests — requires `X-Operator-Key` |
| `GET /api/approvals/{id}/status` | JSON | Client poll fallback; Next.js proxy injects operator key |
| `POST /api/approvals/{id}/decide` | JSON | Approve/Deny via API — requires `X-Operator-Key` (Telegram bot calls `decide_approval` in-process) |
| `GET /api/last-result` | JSON | Optional polish — requires `X-Operator-Key` |

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

## Knowledge base (two layers — do not confuse)

| Layer | File | Role |
|-------|------|------|
| **Live index (what the crew searches)** | `backend/data/support.db` | **SQLite FTS5** — used by `kb_search` at runtime (ADR-20) |
| **Authoring / seed (what you edit)** | `backend/kb/articles.csv` | Hand-edited FAQs; **not** queried live. Loaded into SQLite on backend start (and via migrate script) |

**Flow:** edit CSV → start backend (or run migrate) → FTS5 index updated → chat retrieval hits SQLite only.

```bash
# Optional explicit re-seed (also happens automatically on startup)
python -m backend.scripts.migrate_kb_csv_to_sqlite
```

TF-IDF-over-CSV (ADR-13) is **historical** — superseded for live retrieval. If a doc still says “search articles.csv at runtime,” it is outdated.

Details: [`backend/kb/README.md`](backend/kb/README.md).

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

**Fail closed:** If `TELEGRAM_ENABLED=true` but token or manager chat id is missing, the bot **will not** start (avoids open approve from any Telegram chat).

**Demo script (laptop = customer, phone = Telegram):**

| You type in chat | Manager does |
|------------------|--------------|
| `Apply a $25 credit to ACC-1001 for the outage last week` | Tap **Approve** |
| `Cancel my plan and waive the $150 ETF on ACC-2002` | Tap **Deny**, then send a reason or `/skip` |
| `credit for outage` | Same HITL path; **lookup #** 1–100 assigned (`REF-{n}`, proposed `$n`) |
| `can you waive my fee` | Same HITL path with lookup # |

After **Deny**, the bot asks for a reason. Type the reason, or `/skip` for contract boilerplate only. Credit denials say `Your request was not approved. We are unable to credit you $X for {their reason}` (plus the manager note when provided) — no request number and no ETF boilerplate.

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

# Gates /api/approvals/* and /api/last-result (same value in frontend/.env.local)
OPERATOR_API_KEY=dev-operator-key

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

## Evals (quality gates)

The eval suite under `evals/` implements SAD §9 criteria (`EC-001`…`EC-019`). Strategy and latest results: [`project-context/2.build/evals.md`](project-context/2.build/evals.md). Criteria contract: [`project-context/1.define/sad.md`](project-context/1.define/sad.md) §9.

Run all commands from the **repository root**.

### What each mode does

| Mode | Command | Needs backend? | What it grades |
|------|---------|----------------|----------------|
| **Static** | `--static` | No | Config/security/cost: `max_iter`, `MAX_RPM`, model tiers, tool allowlist, Prompt Trace redaction |
| **Fixtures** | `--fixtures` | No | Synthetic Path A/B/C + adversarial items against `evals/fixtures/chat_responses.json` |
| **Live** | `--live` | Yes (`:8001`) | Same dataset via real `POST /api/chat` (uses your LLM; can take minutes per item) |
| **All** | `--all` (default) | Live only if healthy | Static + fixtures; adds live when `GET /health` succeeds |

**Profiles** (`--profile` or `EVAL_PROFILE`, default **production**):

| Profile | `course_pass` | `production_ready` |
|---------|---------------|-------------------|
| **mvp** | static + fixtures | false unless live also passed Path A p95 |
| **production** | static + fixtures; live items + Path A p95 **< 30s** when live ran | true only when live ran and passed those gates |

Latency p95 applies to **Path A** only (automated FAQ). Path C HITL wait is excluded. Cost stays control-only. EC-005 judge does not block.

### Quick run (no LLM)

```bash
python -m evals.run --static --fixtures --profile mvp
```

Expected: `course_pass: true`. Default `--profile production` on the same command still passes `course_pass` but sets `production_ready: false` (`live_not_run`).

### Live run (backend must be up)

Start the API via [Quick Start (local)](#quick-start-local) or [Docker Compose](#quick-start-docker-compose), then:

```bash
python -m evals.run --all --profile production --base-url http://127.0.0.1:8001
python -m evals.run --live --base-url http://127.0.0.1:8001
```

Optional flags:

```bash
# Limit items while debugging (e.g. first 2)
python -m evals.run --live --limit 2

# Faithfulness judge for resolve+citations (EC-005). Needs OPENAI_API_KEY or EVAL_JUDGE_API_KEY.
# Judge model defaults to EVAL_JUDGE_MODEL=gpt-4o and must differ from the model under test.
# Uncalibrated — do not treat as a Deliver blocker until a human-labeled set exists.
python -m evals.run --fixtures --judge
python -m evals.run --live --judge
```

### Dataset layout

| Path | Role |
|------|------|
| `evals/dataset/path_a_resolve.jsonl` | In-KB FAQ → resolve + citations |
| `evals/dataset/path_b_gap.jsonl` | Out-of-KB → no fabricated resolve |
| `evals/dataset/path_c_human.jsonl` | `request_human=true` → escalate + packet |
| `evals/dataset/adversarial_edge.jsonl` | Injection / disclosure / discount probe |
| `evals/fixtures/chat_responses.json` | Offline expected-shape responses |
| `evals/checks/` | Code-based graders |
| `evals/judge/` | Optional EC-005 faithfulness judge |
| `evals/results/` | Timestamped JSON + `latest.json` |

### Env vars that affect evals

| Variable | Effect |
|----------|--------|
| `NEXT_PUBLIC_API_BASE_URL` / `--base-url` | Live API target (default `http://127.0.0.1:8001`) |
| `CHAT_TIMEOUT_SECONDS` | Live request timeout budget (+30s headroom in the runner) |
| `MAX_ITER` / `MAX_RPM` | Static cost checks (defaults 12 / 10) |
| `EVAL_PROFILE` | `mvp` or `production` (default `production`) |
| `EVAL_PRODUCTION_P95_MS` | Path A live p95 gate (default `30000`) |
| `EVAL_JUDGE_MODEL` | Judge model for `--judge` (default `gpt-4o`) |
| `OPENAI_API_KEY` or `EVAL_JUDGE_API_KEY` | Required for `--judge` |

After changing crew prompts, KB, or guardrails, re-run **fixtures** always and **live** before treating quality as verified.

---

## Troubleshooting

### Backend won't start?
- Check Python version: `python --version` (need 3.10+)
- Reinstall dependencies: `pip install -r backend/requirements.txt`
- Check port 8001: `netstat -ano | findstr :8001`
- If port 8000 is in use by Docker/WSL, use 8001 (default in `.env`)

### Frontend won't start?
- Check Node version: `node --version` (need **20+**)
- Reinstall dependencies: `npm ci` or `npm install` (in frontend/)
- Check port 3000: `netstat -ano | findstr :3000`

### Docker Compose won't start or FE can't reach API?
- Confirm Docker Desktop is running and `.env` exists at repo root with LLM keys
- Free ports 3000/8001: stop local uvicorn / `npm run dev` before `docker compose up`
- FE image is built with `NEXT_PUBLIC_API_BASE_URL=http://backend:8001` — rebuild after changing that arg: `docker compose up --build`
- Health from host: `curl http://127.0.0.1:8001/health` (or open in a browser)
- Logs: `docker compose logs -f backend` / `docker compose logs -f frontend`
- Approvals **503**: set `OPERATOR_API_KEY` in root `.env` (Compose passes it into the frontend service)

### CrewAI AMP traces not showing?
- Tracing is on when `CREWAI_TRACING_ENABLED=true` (default) and `Crew(tracing=True)`
- Authenticate once: `crewai login`, then run a chat request
- View traces at https://app.crewai.com (Traces tab)
- Local Prompt Trace files under `LOG_DIR` are written even if AMP login is skipped
- Set `CREWAI_TRACING_ENABLED=false` to turn AMP tracing off

### "system_error" in responses?
- Verify `.env` file exists at project root
- Check `OLLAMA_MODEL=gemma4:31b` (must match a model available on your Ollama account)
- Check backend logs for specific errors

### Telegram never pings the manager?
- `TELEGRAM_ENABLED=true` and restart the backend (lifespan starts polling)
- Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_MANAGER_CHAT_ID` (group IDs are often **negative**)
- Both must be set — incomplete config disables the bot
- Run `python -m backend.scripts.telegram_get_chat_id` after messaging the bot
- Customer chat uses **SSE** (`/api/chat/stream`). Legacy `POST /api/chat` does not wait for Telegram

### Operator page / approvals return 401 or 503?
- Set `OPERATOR_API_KEY` in **root** `.env` (backend) and **`frontend/.env.local`** (same value)
- Restart backend and `npm run dev` (Next injects `X-Operator-Key` in the approvals route)
- Direct curls to FastAPI need the header: `-H "X-Operator-Key: $OPERATOR_API_KEY"`
- Chat endpoints (`/api/chat`, `/api/chat/stream`) stay open without the key

### HITL hangs for five minutes?
- Manager must tap Approve/Deny. On Deny, send a reason or `/skip`
- If Telegram is off, requests should not hang — they resolve as manager unavailable
- Browser abort is ~500s; backend wait is `HITL_TIMEOUT_SECONDS` (default 300)

### Evals fail or live section skipped?
- Run from repo root: `python -m evals.run --static --fixtures` (no backend needed)
- Live needs `GET http://127.0.0.1:8001/health` → `{"status":"ok"}` first
- `course_pass: false` on fixtures: inspect `evals/results/latest.json` → `sections.fixtures.items` for failed check ids
- Windows console Unicode errors: set `PYTHONIOENCODING=utf-8` (or rely on ASCII details already in the runner)
- `--judge` skipped: set `OPENAI_API_KEY` or `EVAL_JUDGE_API_KEY`; judge stays uncalibrated until a human-labeled set exists

---

## Stopping the Servers

**Local:** Press **Ctrl+C** in each terminal (backend and frontend). Ensure only one uvicorn is listening on 8001.

**Compose:**

```bash
docker compose down
```
