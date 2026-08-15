# Multi-Agent Customer Support Crew

Chat-first MVP that runs four specialized [CrewAI](https://www.crewai.com/) agents so a customer gets either a **knowledge-grounded answer with citations** or a **clean human escalation with a full context packet**.

This is a course/demo orchestration layer — not a CCaaS or live ticketing suite. It is built with the [AAMAD](https://pypi.org/project/aamad/) (AI-Assisted Multi-Agent Application Development) workflow.

**MVP user value:** grounded resolve **or** trustworthy handoff — without a blind queue or a black-box FAQ bot.

---

## Status

| Phase | State |
|-------|--------|
| **Define** | Complete — MRD, PRD, context summary, and SAD reviewed against each other (**PASS**, 2026-08-14) |
| **Build** | Not started — next is `@project.mgr` → `*setup-project` |
| **Deliver** | Not started |

**Runtime:** `crewai` (locked for this course MVP).  
**Window:** 2026-08-01 → 2026-09-12.

Canonical architecture stays in [`project-context/1.define/sad.md`](project-context/1.define/sad.md). Build logs and epic notes will live under `project-context/2.build/`.

---

## What it does

A customer opens a web chat, sees an AI disclosure, and sends a message. The backend runs a sequential crew:

```
query_classifier → knowledge_retriever → response_specialist → escalation_manager
```

The API then returns a single non-streaming JSON `ChatResponse`: resolve with sources, or escalate with a packet and a stub ticket id (`STUB-…`).

| Demo path | Example | Expected |
|-----------|---------|----------|
| **A** — in-KB FAQ | `How do I reset my Acme Cloud password?` | `decision=resolve`, citations, no packet |
| **B** — unknown topic | `What is your quantum warranty for the hardware drone?` | `decision=escalate` (never resolve-only refuse), packet + stub |
| **C** — request human | Billing complaint with `request_human=true` | `decision=escalate`, `reason_codes` include `request_human`, all four steps |

**In MVP:** Next.js chat UI, FastAPI gateway, local Markdown KB (≥10 Acme Cloud FAQs), in-memory ticket stub, operator strip, Prompt Trace files.

**Out of MVP:** live Zendesk/Intercom, streaming tokens, multi-turn clarifier, CSAT dashboard, database, SSO, voice, CRM writes, fifth agent, biometric emotion.

---

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js (App Router) + TypeScript + Tailwind |
| Backend | Python + FastAPI + CrewAI (YAML agents/tasks) |
| Retrieval | TF-IDF / bag-of-words over `backend/kb/` (floor `0.35`) |
| LLM | OpenAI-compatible; tiers `OPENAI_MODEL_LOW` / `OPENAI_MODEL_MID` |
| Transport | Non-streaming JSON — `POST /api/chat`, `GET /health` |

Acceptance criteria for QA: `AC-01` … `AC-06` in the [PRD](project-context/1.define/prd.md).

---

## Repository layout

```
.
├── project-context/
│   ├── 1.define/          # MRD, PRD, SAD, context summary  ← current source of truth
│   ├── 2.build/           # setup / frontend / backend / integration / qa (not yet)
│   └── 3.deliver/         # deploy.md + user-guide (not yet)
├── backend/               # FastAPI + CrewAI (to be implemented)
├── frontend/              # Next.js chat (to be implemented)
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
| Handoff brief | [`project-context/1.define/context-summary.md`](project-context/1.define/context-summary.md) |

---

## How to continue (AAMAD)

Work is persona-driven in Cursor. Do not implement the full stack in one chat.

1. `@project.mgr` — scaffold `frontend/`, `backend/`, `backend/config/`, `backend/kb/`, `.env.example`, `setup.md`
2. `@backend.eng` — YAML crew, named Pydantic outputs, `kb_search` + `ticket_stub`, `POST /api/chat`
3. `@frontend.eng` — chat UI against **mocks** (no live API)
4. `@integration.eng` — wire `NEXT_PUBLIC_API_BASE_URL` to `/api/chat`
5. `@qa.eng` — unit + integration vs `AC-01`…`AC-06`
6. `@devops.eng` — CI, `deploy.md`, user guide (after QA)

Step-by-step commands: [`CHECKLIST.md`](CHECKLIST.md).  
Optional gate: `aamad validate --phase define|build|deliver`.

---

## Local run (after Build)

When Setup and Backend exist:

1. Copy `.env.example` → `.env` and set `OPENAI_API_KEY` (never commit secrets).
2. Backend: `uvicorn` on port **8000** (`GET /health` → `{ "status": "ok" }`).
3. Frontend: Next.js on port **3000**, `NEXT_PUBLIC_API_BASE_URL` pointing at the API.
4. CORS allowlist: `http://localhost:3000` and `http://127.0.0.1:3000`.

Soft timeout is **45s** on the API; the chat client should abort at **50–60s**.

---

## Built with AAMAD

Personas, rules, and templates live under `.cursor/`. Runtime adapters (`crewai`, `claude-agent-sdk`, `cursor-sdk`) only affect the **generated** MVP, not AAMAD’s own Define → Build → Deliver sequence.

Framework version in this repo: **0.7.5** (see [`AGENTS.md`](AGENTS.md)).
