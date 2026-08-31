# Multi-Agent Customer Support Crew

Chat-first MVP for **B-Mobile**, a fictional consumer mobile carrier. Four specialized [CrewAI](https://www.crewai.com/) agents give a customer either a **knowledge-grounded answer with citations** or a **clean human escalation with a full context packet**. Policy exceptions (billing credit, ETF waiver) pause the chat until a **manager approves or denies in Telegram**.

This is a course/demo orchestration layer — not a CCaaS or live ticketing suite. It is built with the [AAMAD](https://pypi.org/project/aamad/) (AI-Assisted Multi-Agent Application Development) workflow.

**MVP user value:** grounded resolve, trustworthy handoff, or manager-gated policy action — without a blind queue or a black-box FAQ bot.

Step-by-step local run: [`RUNNING.md`](RUNNING.md).

---

## Status

| Phase | State |
|-------|--------|
| **Define** | Complete — MRD, PRD, SAD, and SFS for SQLite KB + HITL |
| **Build** | Complete for this MVP — live crew, SSE streaming, SQLite FTS5 retrieval, Telegram HITL |
| **Deliver** | Not started (`project-context/3.deliver/`) |

**Runtime:** `crewai` (locked for this course MVP).  
**Window:** 2026-08-01 → 2026-09-12.

Canonical architecture: [`project-context/1.define/sad.md`](project-context/1.define/sad.md) (ADR-20 SQLite FTS5, ADR-21 Telegram HITL).  
Build notes: `project-context/2.build/`. Feature specs: `project-context/1.define/sfs/`.

---

## What it does

A customer opens the web chat, acknowledges the AI disclosure, and sends a message. The backend runs a sequential crew:

```
query_classifier → knowledge_retriever → response_specialist → escalation_manager
```

The browser uses **SSE progress streaming** (`POST /api/chat/stream`). A legacy JSON `POST /api/chat` remains for scripts.

| Demo path | Example | Expected |
|-----------|---------|----------|
| **A** — in-KB FAQ | `How do I reset my B-Mobile My Account PIN?` | `decision=resolve`, citations |
| **B** — unknown in-scope topic | Obscure B-Mobile question not in KB | `decision=resolve` when low urgency + neutral; polite gap reply |
| **B′** — out of scope | `What is the capital of France?` | Scope-only reply; no human-agent pitch |
| **C** — request human | Billing complaint with **I'd rather talk to a person** | `decision=escalate`, packet + stub ticket |
| **G** — greeting | `hello` | Friendly welcome; no specialist banner |
| **HITL** — billing credit | `Apply a $25 credit to ACC-1001 for the outage last week` or `credit for outage` | Chat waits; manager **Approve/Deny** in Telegram |
| **HITL** — ETF waiver | `Cancel my plan and waive the $150 ETF on ACC-2002` or `can you waive my fee` | Same Telegram gate; deny can include a manager reason |

Vague credit/fee requests (no `ACC-*` / dollar amount) still go to HITL with a random **lookup # 1–100** (`REF-{n}`, proposed amount `$n`).

**Guardrails** (greeting resolve, low-urgency calm resolve, out-of-scope copy): [`RUNNING.md`](RUNNING.md#guardrails-2026-08-27) and `project-context/2.build/backend.md`.

**In MVP:** Next.js chat (customer `/` — no specialist strip; use `/operator` for queue), FastAPI gateway, CrewAI YAML crew, **SQLite FTS5** KB (`backend/data/support.db`), stub accounts/orders, in-memory ticket stub, Prompt Trace files, SSE crew progress, **Telegram manager HITL**.

**Out of MVP:** live Zendesk/Intercom, LLM token streaming, multi-turn clarifier, CSAT dashboard, conversation-history DB, SSO, voice, real CRM writes, Approve/Deny on the customer page, fifth agent, biometric emotion.

---

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js (App Router) + TypeScript + Tailwind |
| Backend | Python + FastAPI + CrewAI (`backend/config/agents.yaml` + `tasks.yaml`) |
| Retrieval | **SQLite FTS5** over `backend/data/support.db` (CSV is the canonical seed/export); floor `KB_SIMILARITY_FLOOR=0.35` |
| HITL | Application approval queue + Telegram bot (`TELEGRAM_*`); not CrewAI `human_input` |
| LLM | OpenAI-compatible; `LLM_PROVIDER=openai` (tiered `OPENAI_MODEL_LOW` / `OPENAI_MODEL_MID`) or `ollama` (`OLLAMA_MODEL`) |
| Transport | **SSE** `POST /api/chat/stream` (primary) + JSON `POST /api/chat` (legacy) |

Acceptance criteria: `AC-01` … `AC-06` in the [PRD](project-context/1.define/prd.md).

---

## Repository layout

```
.
├── project-context/
│   ├── 1.define/          # MRD, PRD, SAD, SFS, context summary
│   ├── 2.build/           # backend / frontend / integration / qa
│   └── 3.deliver/         # deploy.md + user-guide (not yet)
├── backend/               # FastAPI + CrewAI
│   ├── config/            # agents.yaml, tasks.yaml
│   ├── kb/articles.csv    # seed FAQs (canonical export)
│   ├── data/support.db    # live FTS5 KB + stubs + approvals (local, not committed)
│   └── scripts/           # migrate KB, Telegram chat id, validators
├── frontend/              # Next.js B-Mobile support UI
├── RUNNING.md             # local run, Telegram setup, demo script
├── .cursor/               # AAMAD personas, rules, templates
├── AGENTS.md
└── CHECKLIST.md
```

### Define artifacts

| Doc | Path |
|-----|------|
| Market research | [`project-context/1.define/mrd.md`](project-context/1.define/mrd.md) |
| Product requirements | [`project-context/1.define/prd.md`](project-context/1.define/prd.md) |
| Architecture (SAD) | [`project-context/1.define/sad.md`](project-context/1.define/sad.md) |
| HITL feature spec | [`project-context/1.define/sfs/hitl-policy-action-approval.md`](project-context/1.define/sfs/hitl-policy-action-approval.md) |
| KB feature spec | [`project-context/1.define/sfs/kb-sqlite-retrieval.md`](project-context/1.define/sfs/kb-sqlite-retrieval.md) |
| Handoff brief | [`project-context/1.define/context-summary.md`](project-context/1.define/context-summary.md) |

---

## How to continue (AAMAD)

Build-phase personas already produced the live MVP. Remaining work is **Deliver** (`@devops.eng`) after QA/security gates, plus any scoped demo polish.

Historical epic order (already executed):

1. `@project.mgr` — scaffold `frontend/`, `backend/`, `.env.example`
2. `@backend.eng` — YAML crew, named Pydantic outputs, `kb_search` + `ticket_stub`, chat API
3. `@frontend.eng` — chat UI
4. `@integration.eng` — SSE stream + `NEXT_PUBLIC_API_BASE_URL`
5. `@qa.eng` — `AC-01`…`AC-06` in `qa.md`
6. `@devops.eng` — CI, `deploy.md`, user guide (after QA)

Step-by-step framework commands: [`CHECKLIST.md`](CHECKLIST.md).  
Optional gate: `aamad validate --phase define|build|deliver`.

---

## Local run

**Do not commit `.env`.** Copy `.env.example` → `.env` at the repo root. Copy `frontend/.env.example` → `frontend/.env.local`.

This machine’s working ports are **frontend 3000** and **backend 8001** (8000 is often taken). Point `NEXT_PUBLIC_API_BASE_URL` at `http://127.0.0.1:8001`.

From the **repo root**:

```bash
# Terminal 1 — backend
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Acknowledge the AI disclosure, then try Path A: `How do I reset my B-Mobile My Account PIN?`

Crew timeout is `CHAT_TIMEOUT_SECONDS` (default **180s**). HITL wait is `HITL_TIMEOUT_SECONDS` (default **300s**); the browser aborts around **500s** so the manager has time to reply. CORS allowlist: `http://localhost:3000` and `http://127.0.0.1:3000`.

Telegram HITL, demo lines, and troubleshooting: [`RUNNING.md`](RUNNING.md). Ollama Cloud: [`OLLAMA_SETUP.md`](OLLAMA_SETUP.md).

---

## Built with AAMAD

Personas, rules, and templates live under `.cursor/`. Runtime adapters (`crewai`, `claude-agent-sdk`, `cursor-sdk`) only affect the **generated** MVP, not AAMAD’s own Define → Build → Deliver sequence.

Framework version in this repo: **0.7.5** (see [`AGENTS.md`](AGENTS.md)).
