# System Architecture Document (SAD): Multi-Agent Customer Support Crew

**PRD Document**: `project-context/1.define/prd.md`  
**MRD**: `project-context/1.define/mrd.md`  
**User Stories**: N/A (not yet authored; trace to PRD `AC-01`…`AC-06`)  
**Context Summary**: `project-context/1.define/context-summary.md`  
**MVP Scope**: Grounded chat resolve **or** clean human escalate with context packet  
**Selected Runtime**: `crewai` (locked per PRD; `AAMAD_TARGET_RUNTIME` unset → default)

---

## 1. Architecture Overview

### System description

The Multi-Agent Customer Support Crew is a chat-first MVP that runs four specialized CrewAI agents in a sequential pipeline so a customer receives either a **knowledge-grounded answer with citations** or a **clean human escalation with a full context packet**. It is an orchestration layer for demo/course delivery—not a CCaaS or live ticketing suite replacement (MRD/PRD).

**MVP user value:** grounded resolve **or** trustworthy handoff—without a blind queue or black-box FAQ bot.

### Main functions

| Function | Behavior | AC |
|----------|----------|-----|
| AI-disclosed chat intake | Show AI disclosure; accept message; optional request-human | AC-01, AC-01a, AC-01b |
| Multi-agent resolution | Classify → retrieve → compose → triage (4 steps, auditable) | AC-02 |
| Grounded answer / refuse | Answer only from KB evidence; refuse or escalate on gap | AC-03 |
| Sentiment-aware escalation | Text-only risk/sentiment; escalate with packet + stub ticket | AC-04 |
| Operator visibility | Decision, reason_codes, step summaries from last `ChatResponse` in UI state (`/api/last-result` optional polish) | AC-05 |
| Health & failure path | Liveness probe; structured error + escalate CTA on LLM/KB failure | AC-06 |

**Demo paths:** (A) in-KB FAQ → resolve + sources; (B) unknown topic → escalate with refuse-style reply + packet (never resolve-only refuse); (C) request human / high risk → escalate with packet.

### Main interfaces

| Interface | Direction | Contract |
|-----------|-----------|----------|
| Web chat UI (`/`) | Customer ↔ Frontend | Disclosure, composer, stage labels, result/escalate card, operator strip |
| `POST /api/chat` | Frontend ↔ Backend | Non-streaming JSON request/response (primary resolve path) |
| `GET /health` | Ops / CI ↔ Backend | `{ "status": "ok" }` |
| `GET /api/last-result` | Operator UI ↔ Backend (optional polish) | Last in-memory `ChatResponse`; **not** required for AC-05 |
| CrewAI `kickoff` | FastAPI ↔ Runtime | Inputs `{message, request_human}`; sequential task outputs |
| `kb_search` | Retriever ↔ Local KB files | Query → passages / gap |
| `ticket_stub` | Escalation ↔ In-memory stub | Packet → `{ticket_id: "STUB-…"}` |
| LLM provider API | CrewAI ↔ External | Completions via env-configured key/model |

```
Browser (Next.js) ──POST /api/chat──► FastAPI ──kickoff──► CrewAI (4 agents)
                                              │                 ├─ kb_search (local)
                                              │                 └─ ticket_stub
                                              ▼
                                    ChatResponse + Prompt Trace
                                              │
                                              ▼
                                    Chat UI + OperatorStrip
```

### MVP vs Future Work

| Tier | In scope |
|------|----------|
| **MVP** | Next.js chat + disclosure; FastAPI; CrewAI sequential crew; local KB; ticket stub; operator strip; non-streaming JSON |
| **Future (P1/P2)** | Live ticketing, streaming UI, multi-turn clarifier, CSAT dashboard, DB/history, SSO, voice, CRM writes, cloud vector DB, 5th agent, Ollama / OpenAI-compatible local base URL, `high` model tier, API rate limiting |

**Explicit exclusions (MVP):** persistent database, Zendesk/Intercom live APIs, biometric emotion, horizontal autoscaling, MCP servers, hierarchical CrewAI process, Ollama as a required runtime path, per-agent model env vars, API rate limiting.

### Stakeholders (concern → architecture)

| Stakeholder | Concern | Primary section |
|-------------|---------|-----------------|
| End-customer | Fast grounded answer or human path | §1 interfaces, §2 FE |
| Support agent | Escalation packet quality | §2 agents / packet |
| Support manager | Auditability | §4 observability |
| Build personas | Clear contracts | §2–§3, Appendix A |
| Course operator | 6-week fit | §5 constraints / ADRs |

---

## 2. Logical Architecture

### Key services and components

| Component | Responsibility | Owner epic |
|-----------|----------------|------------|
| Chat UI (Next.js) | Disclosure, composer, stage labels, result/escalate card, operator strip, Future Work stubs | Frontend |
| API client (`lib/api.ts`) | Mock in FE epic; live `fetch` to `/api/chat` in Integration | FE → Integration |
| FastAPI gateway | Validate request; CORS; invoke crew; map response; health; optional last-result | Backend |
| CrewAI runtime (`customer_support_crew`) | Sequential 4-agent pipeline from YAML | Backend |
| `kb_search` | Local file retrieval over `backend/kb/` (≥10 seed FAQs) | Backend |
| `ticket_stub` | In-memory stub ticket id for escalate path | Backend |
| Prompt Trace store | `{LOG_DIR}/{trace_id}.json` (redact secrets/PII) | Backend |
| LLM provider | Model completion via CrewAI / OpenAI SDK | External |

**Data (MVP):** no persistent DB. Seed KB = files under `backend/kb/`. Optional process-local `last_result` (lost on restart). `session_id` opaque/optional only.

### Frontend logical structure

- **Stack:** Next.js App Router, TypeScript, Tailwind; React local state (no Redux).
- **Types:** `ChatRequest` / `ChatResponse` mirroring backend schema (incl. optional `meta` for AC-01b).
- **Boundary:** `@frontend.eng` uses **mock** responses; `@integration.eng` wires `NEXT_PUBLIC_API_BASE_URL`.

```
frontend/
  app/page.tsx                 # Chat + disclosure + operator strip
  components/                  # DisclosureBanner, ChatMessageList, ChatComposer,
                               # StatusLine, ResultCard, OperatorStrip, FutureWorkStubs
  lib/types.ts, api.ts, mockResponse.ts
```

**UI requirements:** sources on resolve; escalate CTA on error; Talk-to-human always available; responsive 375px / 1280px. Accessibility from PRD: keyboard send (Enter), focusable controls, adequate contrast for demo.

**Visual direction (from PRD §6):** light color theme; modern fonts (e.g. via `next/font`); MVP defaults to light mode. SAD owns behavior contracts only — detailed styling belongs in `frontend.md`.

**StatusLine UX contract (non-streaming MVP):** API returns one JSON after full `kickoff` — do **not** invent SSE/WebSocket/streaming.

| Event | Behavior |
|-------|----------|
| On send | Optimistic/local stage animation cycles Classifying → Retrieving → Composing → Triaging on a client timer |
| First stage | UI must show the first stage label within **10s of send** (local), not “first agent finished &lt;10s” |
| On response | Stop animation; render reply + authoritative `steps[]` |
| On error/timeout | Stop animation; safe message + Talk-to-human CTA (FE abort **50–60s**) |

**Operator strip:** bind from the **last `ChatResponse` in FE UI state** (mock in FE epic; live response after Integration). `/api/last-result` is optional polish only.

### Backend API contracts

**Base:** FastAPI in `backend/main.py` (or `backend/app/main.py`). CORS allowlist for local Next: **`http://localhost:3000`** and **`http://127.0.0.1:3000`** (both — browsers treat them as different origins).

| Method | Path | Purpose | AC |
|--------|------|---------|-----|
| GET | `/health` | Liveness `{ "status": "ok" }` | AC-06a |
| POST | `/api/chat` | Run crew; return decision | AC-02…05, AC-01b |
| GET | `/api/last-result` | Optional polish only (not AC-05 exit) | — |

**Request**

```json
{
  "message": "string",
  "request_human": false,
  "session_id": "optional-string",
  "disclosure_acknowledged": true
}
```

**Validation:** `message` required, non-empty, max **4000** chars; `request_human` default false; `disclosure_acknowledged` optional (AC-01b). Missing or `false` disclosure does **not** block chat — disclosure is a UI/AC-01 duty; API still echoes when provided.

**HTTP status contract**

| Outcome | Status | Body |
|---------|--------|------|
| Success (resolve or escalate) | **200** | `ChatResponse` with `error=null` |
| Soft timeout / LLM / unexpected after kickoff starts | **200** | Error envelope `ChatResponse` (`error` set; never invent an answer) |
| Invalid `ChatRequest` | **400** | Error envelope or FastAPI validation detail; prefer same `ChatResponse` shape with `error.code=validation_error` when practical |
| Route/method not found | 404 / 405 | Framework default (out of chat contract) |

FE treats **any** `ChatResponse` with `error != null` or `decision=escalate` + Talk-to-human CTA as the safe failure UX. Prefer **200 + error object** for kickoff failures so Integration maps one schema.

**FE client timeout:** `fetch` / abort after **50–60s** (slightly above API soft timeout **45s**). On abort: stop StatusLine; show safe message + Talk-to-human CTA (same as AC-06b).

**Success response (non-streaming) — `ChatResponse`**

```json
{
  "decision": "resolve|escalate",
  "reply": "string",
  "sources_used": [{"title": "string", "snippet": "string"}],
  "sentiment": "positive|neutral|negative",
  "risk": "low|medium|high",
  "reason_codes": ["string"],
  "steps": [{"agent": "string", "summary": "string"}],
  "trace_id": "string",
  "packet": null,
  "stub_ticket_id": null,
  "meta": {
    "ai_disclosure": true,
    "disclosure_acknowledged": true
  },
  "error": null
}
```

**Escalate path:** set `packet` to the full `EscalationPacket` object and `stub_ticket_id` to the stub id (e.g. `"STUB-…"`); on resolve, both are `null`. Operator strip and ResultCard read `packet` from this same `ChatResponse` (ADR-14).

**AC-01b:** Always set `meta.ai_disclosure=true`; echo `disclosure_acknowledged` when provided; record both in Prompt Trace.

**Error envelope (`AC-06b`)** — still a `ChatResponse` (prefer HTTP **200**); never invent an answer.

**System-failure packet policy:** On timeout / LLM / unexpected failure, still attach a **minimal** `EscalationPacket` + `stub_ticket_id` when possible so operators are not blind. Populate known fields (`customer_message`, `request_human`, partial `intent`/`urgency`/`citations_attempted`/`draft_reply` from completed tasks); set missing agent fields to `""` / `[]` / defaults; include `reason_codes` with `timeout` or `system_error`. If kickoff never started (validation) or stub tool itself fails, `packet` / `stub_ticket_id` may remain `null`.

```json
{
  "decision": "escalate",
  "reply": "We could not complete this request. Please talk to a human.",
  "sources_used": [],
  "sentiment": "neutral",
  "risk": "medium",
  "reason_codes": ["system_error"],
  "steps": [{"agent": "string", "summary": "string"}],
  "trace_id": "string",
  "packet": {
    "intent": "",
    "urgency": "",
    "customer_message": "string",
    "request_human": false,
    "citations_attempted": [],
    "draft_reply": "",
    "sentiment": "neutral",
    "risk": "medium",
    "reason_codes": ["system_error"],
    "stub_ticket_id": "STUB-…"
  },
  "stub_ticket_id": "STUB-…",
  "meta": { "ai_disclosure": true, "disclosure_acknowledged": true },
  "error": {
    "code": "llm_or_timeout",
    "message": "string"
  }
}
```

| `error.code` | When |
|--------------|------|
| `llm_or_timeout` | LLM failure or API soft timeout (45s) |
| `validation_error` | Invalid `ChatRequest` (400 before kickoff) |
| `kb_unavailable` | KB path missing / unreadable (may also continue with `gap=true` when partial) |
| `system_error` | Unexpected exception |

On timeout/system failure: include **partial** `steps[]` for any agents that finished before the halt; prefer `reason_codes` including `timeout` or `system_error`. UI shows `reply` + Talk-to-human CTA.

### Multi-agent coordination

**Pattern:** sequential pipeline; each task consumes prior output via CrewAI `Task.context`. No peer delegation (`allow_delegation=false`). `memory=False`.

```
classify_inquiry → retrieve_knowledge → compose_response → triage_and_escalate
```

**`request_human` short-circuit (locked):** When `request_human=true`, still run the **full** 4-task chain (no skip). Rationale: packet quality needs classify + retrieve attempt + draft for the human; Path C demos must show all four `steps[]`. Cost/latency accepted for MVP; short-circuit-after-classify = Future Work.

| Agent id | Role | Goal | Tools | Model tier |
|----------|------|------|-------|------------|
| `query_classifier` | Inquiry Classification Specialist | Intent, entities, urgency | none | **low** |
| `knowledge_retriever` | Knowledge Base Research Specialist | Grounded passages + citations | `kb_search` | **low** |
| `response_specialist` | Customer Response Composer | Draft from evidence only or refuse | none | **mid** |
| `escalation_manager` | Sentiment, Risk & Escalation Coordinator | Text sentiment/risk; resolve vs escalate; packet | `ticket_stub` | **low** |

**Named structured outputs (`output_pydantic`)**

API envelopes remain `ChatRequest` / `ChatResponse`. Each crew task binds a named Pydantic model so field names stay stable across agents and the FastAPI mapper. Tune retrieval scores later without renaming these models.

| Model | Fields (stable) |
|-------|-----------------|
| `ClassifierOutput` | `intent: str` (open string; no closed taxonomy in MVP), `urgency: low\|medium\|high`, `entities: list[str]`, `confidence: float` |
| `RetrieverOutput` | `passages: list[{title, snippet, score}]`, `citations: list[{title, snippet}]`, `gap: bool` |
| `ResponseOutput` | `reply: str`, `sources_used: list[{title, snippet}]`, `refused: bool` |
| `EscalationOutput` | `decision: resolve\|escalate`, `sentiment: positive\|neutral\|negative`, `risk: low\|medium\|high`, `reason_codes: list[str]`, `packet: EscalationPacket \| null` |
| `EscalationPacket` | see packet schema below (`AC-04a`) |
| `ChatRequest` / `ChatResponse` | API envelopes (§2 Backend API contracts); include `packet` / `stub_ticket_id` / `error` |

**Refuse vs escalate (locked — Path B):** `refused=true` on `ResponseOutput` is an **internal** composer signal (no grounded answer). Final API `decision` is **always `escalate`** when `gap=true` or `refused=true` — never `decision=resolve` with a refuse-only reply. Customer-facing `reply` may still be a polite “I don’t have that in my knowledge base…” text; `sources_used` is empty; `packet` + `stub_ticket_id` required.

**`agents.yaml` sketch (illustrative — `model_tier` consumed by `crew.py`, not by CrewAI itself)**

```yaml
query_classifier:
  role: Inquiry Classification Specialist
  goal: Classify customer intent, entities, and urgency for routing
  model_tier: low          # → OPENAI_MODEL_LOW
  allow_delegation: false
knowledge_retriever:
  role: Knowledge Base Research Specialist
  goal: Retrieve grounded passages with citations for the classified intent
  model_tier: low
  allow_delegation: false
response_specialist:
  role: Customer Response Composer
  goal: Draft clear replies using only grounded evidence or refuse
  model_tier: mid          # → OPENAI_MODEL_MID
  allow_delegation: false
escalation_manager:
  role: Sentiment, Risk & Escalation Coordinator
  goal: Score text sentiment/risk; decide resolve vs escalate; package context
  model_tier: low
  allow_delegation: false
```

**`tasks.yaml` sketch (illustrative)**

```yaml
classify_inquiry:
  agent: query_classifier
  expected_output: ClassifierOutput
  # CrewAI: output_pydantic: ClassifierOutput (or equivalent structured output)
retrieve_knowledge:
  agent: knowledge_retriever
  context: [classify_inquiry]
  expected_output: RetrieverOutput
compose_response:
  agent: response_specialist
  context: [classify_inquiry, retrieve_knowledge]
  expected_output: ResponseOutput
triage_and_escalate:
  agent: escalation_manager
  context: [classify_inquiry, retrieve_knowledge, compose_response]
  expected_output: EscalationOutput
```

| Task id | Agent | Context from | `output_pydantic` | Suggest `max_execution_time` |
|---------|-------|--------------|-------------------|------------------------------|
| `classify_inquiry` | query_classifier | user message | `ClassifierOutput` | 12s |
| `retrieve_knowledge` | knowledge_retriever | classify_inquiry | `RetrieverOutput` | 12s |
| `compose_response` | response_specialist | classify + retrieve | `ResponseOutput` | 15s |
| `triage_and_escalate` | escalation_manager | all prior + `request_human` | `EscalationOutput` | 12s |

**Wall-clock vs per-task (locked):** API soft timeout **45s** is authoritative. Per-task caps are guidance and may sum above 45s; when wall-clock fires, **stop further agent work**, keep partial `steps[]`, write Prompt Trace, return error envelope (minimal packet when possible). Do not wait for remaining tasks.

**Escalation packet (`EscalationPacket` / `AC-04a`)**

```json
{
  "intent": "string",
  "urgency": "low|medium|high",
  "customer_message": "string",
  "request_human": false,
  "citations_attempted": [{"title": "string", "snippet": "string"}],
  "draft_reply": "string",
  "sentiment": "positive|neutral|negative",
  "risk": "low|medium|high",
  "reason_codes": ["string"],
  "stub_ticket_id": "STUB-…"
}
```

On **resolve**, `EscalationOutput.packet` is `null` (or omitted) and mapper sets `ChatResponse.packet` / `stub_ticket_id` to `null`. On **escalate**, packet is required and includes `stub_ticket_id`.

**Reason codes:** `request_human` | `retrieval_gap` | `refused` | `low_confidence` | `high_risk_sentiment` | `timeout` | `system_error`

**Escalation gates:** escalate if any of:
- `request_human=true` → `reason_codes` include `request_human`
- `gap=true` or `refused=true` → `retrieval_gap` / `refused` (final `decision` **must** be `escalate`; never resolve-only refuse)
- `confidence` &lt; `CLASSIFIER_CONFIDENCE_MIN` (default **0.55**) → `low_confidence`
- `risk=high` → `high_risk_sentiment`
- `sentiment=negative` **and** (`risk=medium` **or** `risk=high` **or** `request_human` **or** `gap` **or** `refused` **or** low confidence) → `high_risk_sentiment`
- else **resolve** when grounded reply exists, `refused=false`, and `sources_used` non-empty

**Path A stability:** Mild negative wording alone does **not** escalate. Demo Path A messages should stay neutral/factual (canonical query below). Path C uses `request_human=true` and/or high risk.
**FastAPI mapper (task outputs → `ChatResponse`)**

| Source | Maps to `ChatResponse` field(s) |
|--------|----------------------------------|
| `ResponseOutput.reply` | `reply` |
| `ResponseOutput.sources_used` | `sources_used` (empty if refused / escalate) |
| `EscalationOutput.decision` | `decision` |
| `EscalationOutput.sentiment` | `sentiment` |
| `EscalationOutput.risk` | `risk` |
| `EscalationOutput.reason_codes` | `reason_codes` |
| `EscalationOutput.packet` | `packet` (full object on escalate; `null` on resolve) |
| `EscalationPacket.stub_ticket_id` | `stub_ticket_id` (also inside `packet`; `null` on resolve) |
| Each completed task | `steps[]` entry `{agent, summary}` (four on success; **partial OK** on timeout/error) |
| New UUID / ULID | `trace_id` |
| Request disclosure fields | `meta` |
| Exception / timeout path | `error` + escalate envelope; **minimal packet** when possible (see AC-06b policy) |

**Retrieval default (MVP locked — ADR-13):** **TF-IDF / bag-of-words cosine** (or equivalent keyword overlap) over `backend/kb/` — **no embedding dependency required** for Week 2–3 vertical slice. Floor **`KB_SIMILARITY_FLOOR=0.35`** (env override). No passage above floor → `gap=true` on `RetrieverOutput`. Optional hybrid embedding may be added later **without** changing crew topology; record algorithm + floor in `backend.md` Audit.

**Prompt Trace minimum schema (`AC-02c`)** — write `{LOG_DIR}/{trace_id}.json` (redact secrets/PII; never store API keys):

| Field | Required |
|-------|----------|
| `trace_id` | yes |
| `timestamp` | yes (ISO-8601) |
| `inputs` | yes — `{message, request_human, session_id?, disclosure_acknowledged?}` (message may be truncated/redacted per Backend policy) |
| `steps` | yes — same shape as API `steps[]` (partial allowed) |
| `decision` | yes when known |
| `reason_codes` | yes (may be empty list) |
| `meta` | yes — `{ai_disclosure, disclosure_acknowledged}` |
| `error` | yes when failure — `{code, message}` or `null` on success |
| `model` / tier map | recommended — resolved `{low, mid}` model ids |
| Raw LLM prompts | optional; redact if present |
**Seed KB contract (`backend/kb/`)**

| Rule | Value |
|------|--------|
| Count | ≥ **10** FAQ files |
| Format | One FAQ per file; Markdown (`.md`); first `#` heading = title; body = answer text |
| Naming | `NN-slug.md` (e.g. `01-password-reset.md`) |
| Domain | Fictional product **“Acme Cloud”** (SaaS) — English only |
| Path A (hit) | FAQs must cover password reset, billing/invoice, shipping/delivery ETA, returns/refunds, plan upgrade, account email change |
| Path B (miss) | No FAQ for demo query about **quantum warranty on physical hardware** (or equivalent out-of-corpus topic) |
| Path C | Driven by `request_human=true` (primary); high risk optional — do not rely on negative-only |

**Canonical demo queries (QA / Integration)**

| Path | Example user message | Expected |
|------|----------------------|----------|
| A | `How do I reset my Acme Cloud password?` (keep **neutral**; avoid angry wording) | `decision=resolve`, non-empty `sources_used`, `packet=null` |
| B | `What is your quantum warranty for the hardware drone?` | `decision=escalate` (never resolve-only refuse), `reason_codes` include `retrieval_gap` and/or `refused`, `packet` + `stub_ticket_id` present |
| C | `I want to talk to a human now — this billing charge is ridiculous!` with `request_human=true` | `decision=escalate`, `reason_codes` include `request_human`, full `steps[]` (4), `packet` + `stub_ticket_id` |

### Runtime integration (crewai)

1. FastAPI receives `ChatRequest` → validate → start **45s** wall-clock timeout guard.  
2. Build/cached crew from `backend/config/agents.yaml` + `tasks.yaml` + tool bindings.  
3. `crew.kickoff(inputs={"message": ..., "request_human": ...})` with `Process.sequential` (always full chain, including when `request_human=true`).  
4. Map task outputs → `ChatResponse` per mapper table (include `packet` / `stub_ticket_id` on escalate); write Prompt Trace (min schema above); update optional `last_result`.  
5. Return JSON (**200** for success and post-kickoff error envelopes).

**Controls:** `max_iter ≤ 12`; `max_retry_limit ≥ 2`; crew `max_rpm` suggest **10**; wall-clock API soft timeout **45s** (wins over per-task sum). Suggest temperature **0.2** (low-tier agents), **0.4** (`response_specialist`).

**LLM model tiers (ADR-19):** Do **not** set a separate model env per agent. Map each agent to a **tier**; resolve tier → model name from env.

| Tier | Env var | Default model | Used by |
|------|---------|---------------|---------|
| `low` | `OPENAI_MODEL_LOW` | `gpt-4.1-nano` | `query_classifier`, `knowledge_retriever`, `escalation_manager` |
| `mid` | `OPENAI_MODEL_MID` | `gpt-4.1-mini` | `response_specialist` only |
| *(fallback)* | `OPENAI_MODEL` | `gpt-4o-mini` | If a tier env is unset, fall back here then to that tier’s default above |

Backend binds CrewAI agent LLMs from tier at crew build time (e.g. in `crew.py`). Record resolved tier→model map in Prompt Trace / `backend.md` Audit. No `high` tier in MVP (Future Work). Enforce escalation gates in code so low-tier triage cannot freestyle resolve/escalate.

**Concurrency (MVP):** Single backend process; CrewAI `kickoff` may **block** the request worker. Target ≥5 concurrent demo sessions is **best-effort** on one machine — use enough uvicorn workers/threads for the course demo, or accept serial queueing under load. No shared session store; `last_result` is process-local and racy under concurrency (optional polish only). Horizontal scale / async job queue = Future Work. Do **not** fail QA solely because concurrent kicks serialize.

**Not used in MVP:** hierarchical process, `kickoff_for_each`, MCP, memory storage dir, embedding hard-dependency. *(claude-agent-sdk / cursor-sdk: N/A — runtime locked to crewai.)*

### Failure / degrade path

```
LLM/KB/tool failure OR wall-clock timeout (45s)
  → stop further agent work
  → keep partial steps[]
  → Prompt Trace + Diagnostic reason
  → error envelope (decision=escalate; minimal packet + stub when possible)
  → FE safe message + “Talk to a human” (AC-06b); client abort at 50–60s
```

Tool failure on `kb_search` → treat as `gap=true` and continue (prefer escalate over invent). Client disconnect: abandon wait; no session resume. `ticket_stub` may issue a new `STUB-*` per escalate (idempotency = Future Work).
---

## 3. Physical / Deployment Architecture

### Environments

| Environment | Topology | Purpose |
|-------------|----------|---------|
| Local dev (MVP default) | Dual process on one workstation | Day-to-day Build |
| Optional compose (Week 6) | Two containers: `frontend`, `backend` | Demo packaging |
| Public host | Single VM or equivalent (TBD) | Deliver only if authorized |

| Node | Process | Port | Health |
|------|---------|------|--------|
| Backend host | `uvicorn` FastAPI + CrewAI | `BACKEND_PORT` (8000) | `GET /health` → `{status: ok}` |
| Frontend host | `next dev` / `next start` | 3000 | Load `/` |
| Optional compose | services `frontend`, `backend` | published 3000/8000 | same |

**Local run:** Terminal A = uvicorn; Terminal B = Next.js. Seed KB ≥10 `NN-slug.md` FAQs under `backend/kb/` (Acme Cloud; demo queries A/B/C) by Week 2 exit.

### External systems and integration points

| System | MVP role | Notes |
|--------|----------|-------|
| LLM provider (OpenAI-compatible) | Required | HTTPS via CrewAI; `OPENAI_API_KEY` |
| Local filesystem KB | Required | `KB_DIR` / `backend/kb/` |
| Prompt Trace directory | Required | `LOG_DIR` → `project-context/2.build/logs` |
| Zendesk / Intercom / CRM | **Out** | Stub only (`ticket_stub`) |
| Managed vector DB / email / voice | **Out** | Future Work |

### CI/CD and hosting

- **CI (Deliver):** lint/typecheck FE; pytest BE; build Next.js. Config only—no auto-deploy without operator authorization.
- **Hosting:** smallest MVP target = local or single VM/compose. IaC, multi-region, APM = Future Work.
- **TLS:** localhost HTTP OK for course; HTTPS required for any public host.

### Repo / config layout

```
frontend/          # Next.js
backend/           # FastAPI + CrewAI
  config/          # agents.yaml, tasks.yaml
  kb/              # seed FAQs
  crew.py          # kickoff entrypoint
  main.py          # HTTP API
.env.example       # secret names only
project-context/2.build/logs/   # Prompt Trace (runtime)
```

### Environment variables (names only)

| Env var | Purpose |
|---------|---------|
| `OPENAI_API_KEY` | LLM provider key |
| `OPENAI_MODEL_LOW` | Low-tier model (default `gpt-4.1-nano`) — classify, retrieve, escalate |
| `OPENAI_MODEL_MID` | Mid-tier model (default `gpt-4.1-mini`) — response specialist only |
| `OPENAI_MODEL` | Fallback if a tier env is unset (default `gpt-4o-mini`) |
| `AAMAD_TARGET_RUNTIME` | `crewai` |
| `BACKEND_PORT` | Default `8000` |
| `NEXT_PUBLIC_API_BASE_URL` | FE → API base |
| `OPERATOR_API_KEY` | Optional gate for `/api/last-result` (`X-Operator-Key`) |
| `LOG_DIR` | Default `project-context/2.build/logs` |
| `KB_DIR` | Default `backend/kb` |
| `CLASSIFIER_CONFIDENCE_MIN` | Default `0.55` |
| `KB_SIMILARITY_FLOOR` | Default `0.35` (TF-IDF / keyword retrieval gap floor) |

Chat endpoint is **open for demo**. Optional operator key applies to last-result polish only. **Do not** add per-agent model env vars (`OPENAI_MODEL_CLASSIFIER`, etc.) — tiers only (ADR-19).

---

## 4. Quality Attributes

### Scalability

| Metric | MVP target |
|--------|------------|
| Concurrent demo sessions | ≥ 5 (10 aspirational) |
| Horizontal scale | **Deferred** — single backend instance |
| Cost / token control | Tiered models (3× low + 1× mid); `max_rpm`; short prompts; early refuse on gap |

Scale-out (replicas, shared session store, managed vector DB) is Future Work; MVP optimizes for course-demo concurrency, not production load.

### Reliability

| Concern | Architectural response |
|---------|------------------------|
| End-to-end latency | p95 `/api/chat` < **30s**; FE first StatusLine label within **10s of send** (local optimistic animation per ADR-15 — not streaming); FE fetch abort **50–60s** |
| Timeouts | Per-task caps (guidance) + API soft timeout **45s** (authoritative) → escalate envelope + partial `steps[]` + minimal packet when possible |
| LLM / KB outage | Fail-open to human (ADR-11); never invent after tool failure |
| Agent loops / cost overrun | `max_iter ≤ 12`, `max_retry_limit ≥ 2`, crew `max_rpm` |
| Concurrent demos | Best-effort single process; serial kickoff OK; do not treat queueing as AC failure |
| Ticket side-effects | Stub only; live connector idempotency deferred |

### Observability

| Signal | Mechanism |
|--------|-----------|
| Liveness | `GET /health` |
| Per-run audit | `trace_id` + Prompt Trace JSON under `LOG_DIR` (minimum schema §2) |
| Pipeline visibility | `steps[]` in API; optimistic local StatusLine (ADR-15); operator strip from last ChatResponse |
| Escalation rationale | `reason_codes` + packet |
| Application logs | Structured stdout |
| Advanced APM / cost dashboards | Deferred (MRD KPIs inform Future Work) |

### Security (multi-agent AI)

| Topic | MVP posture |
|-------|-------------|
| AuthN/AuthZ | Open chat demo; optional `OPERATOR_API_KEY` for last-result |
| Secrets | Env only; never in YAML, traces, or git |
| Input validation | Message length cap; JSON schema |
| PII | Minimize raw messages in shared artifacts; redact keys from traces |
| AI transparency | Disclosure banner (AC-01); `meta.ai_disclosure` (AC-01b); Art. 50-style |
| Sentiment | Text-only; **no** biometric emotion (ADR-12) |
| Tool least privilege | Only `kb_search` + `ticket_stub`; no MCP / shell / broad tools |
| Grounding / hallucination | Citations required on resolve; gap → refuse/escalate |
| Compliance | GDPR retention / DPIA = Open Questions; `@security.eng` before Deliver when required |

### Related quality attributes

| Attribute | Target | Response |
|-----------|--------|----------|
| Groundedness | No fabricated policy/pricing | RAG + refuse |
| Escalation quality | Context packet every escalate | Packet schema + stub |
| Reproducibility | Deterministic crew config | YAML; `memory=False` |

### Testing expectations (for QA epic)

| Stage | Scope |
|-------|-------|
| Unit | Classification parse; gap→refuse; `request_human`→escalate; packet fields; health |
| Integration | FE↔API↔crew; error path; `meta.ai_disclosure` |
| Smoke / AC | `AC-01`…`AC-06` (incl. a/b); demo paths A/B/C |

Runtime checks: YAML loads; four step summaries; Prompt Trace for `trace_id`; escalate includes packet + `stub_ticket_id`. Recommend `@security.eng` → `security.md` before Deliver (`require_security_assessment: true` in example config).

### Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Hallucination | gap/refuse; citations on resolve |
| LLM outage / slow | timeout + error envelope + escalate CTA |
| Escalation UX / CSAT drop | Context-rich packet; early human exit (MRD ~22% CSAT risk) |
| Scope creep | Exclusions; 4-agent hard cap |
| Trace leaks secrets / PII | Redaction; env-only keys |
| Compliance (Art. 50 / emotion) | Disclosure P0; text-only sentiment |
| Schedule slip | Cut P1 before slipping past 2026-09-12 |

---

## 5. Technical Constraints and Key Design Decisions

### Technical constraints

| Constraint | Source |
|------------|--------|
| Runtime locked to **`crewai`** (YAML agents/tasks) | PRD; `AAMAD_TARGET_RUNTIME` unset → default |
| **≤ 4** specialized agents; sentiment merged into escalation | SAD template / course complexity |
| **No database**; no live third-party ticketing/CRM | Backend persona / PRD §10 |
| **Non-streaming** JSON API | PRD course constraint |
| Fixed delivery window **2026-08-01 → 2026-09-12** (Week 2 current) | Operator / PRD §8 |
| English-first seed KB; chat channel only | PRD assumptions |
| Secrets via environment variables only | AAMAD core / security |
| Adapter baseline: sequential, `allow_delegation=false`, `memory=False`, `max_iter≤12` | `adapter-crewai.mdc` |

### Key design decisions (ADRs)

| ADR | Decision | Rationale |
|-----|----------|-----------|
| ADR-01 | Runtime = **CrewAI** (YAML agents/tasks) | PRD lock; reproducible sequential MVP |
| ADR-02 | **4 agents**; sentiment **inside** `escalation_manager` | Stay within 3–4 agent cap; PRD merge |
| ADR-03 | Frontend = **Next.js App Router + Tailwind + TypeScript** | FE persona defaults; PRD §6 |
| ADR-04 | Backend HTTP = **FastAPI** (Python) | Thin async JSON beside CrewAI |
| ADR-05 | Transport = **non-streaming JSON** | Course constraint; FE stage labels only |
| ADR-06 | **No database** | Backend prohibition; opaque optional `session_id` |
| ADR-07 | Repo layout = `frontend/` + `backend/` | PRD §10.2; clear epic ownership |
| ADR-08 | LLM access via **model tiers** (not one global model for all agents) — see ADR-19 | Cost vs quality; closes PRD OQ #1 for Build |
| ADR-09 | KB = **local files** under `backend/kb/` (≥10 FAQs) | No external vector SaaS in MVP |
| ADR-10 | Process = **sequential**; no delegation; no memory | Determinism; adapter baseline |
| ADR-11 | Fail-open to human on LLM/KB/timeout | PRD reliability; MRD degrade-to-human |
| ADR-12 | Text-only sentiment; no biometric emotion | MRD/PRD compliance; EU AI Act risk posture |
| ADR-13 | KB retrieval = **TF-IDF / bag-of-words cosine** (no embedding hard-dep for MVP); floor **0.35**; seed FAQs as `NN-slug.md` under `backend/kb/` | Close prior OQ #3; demo-stable Week 3; optional embedding later without topology change |
| ADR-14 | Operator strip from **last ChatResponse UI state**; `/api/last-result` optional polish | Close prior OQ #2; single Integration path for MVP |
| ADR-15 | StatusLine = **optimistic local stage animation** until non-streaming JSON returns; FE abort **50–60s** | No streaming protocol in MVP; first stage label &lt;10s of send |
| ADR-16 | Refuse/gap → final **`decision=escalate`** only (never resolve-only refuse); Path B locked | AC-03 groundedness + packet for humans |
| ADR-17 | Sentiment gate: escalate on **`risk=high`**, or **`sentiment=negative` plus** (medium/high risk, request_human, gap, refused, or low confidence) — not negative alone | Protect Path A from mild frustration false escalations |
| ADR-18 | Wall-clock **45s** wins over per-task caps; partial `steps[]` + minimal failure packet; HTTP **200 + error** for post-kickoff failures; full chain even when `request_human=true` | Deterministic failure UX; packet quality for Path C |
| ADR-19 | **Two tiers only:** `low` → `OPENAI_MODEL_LOW` (default `gpt-4.1-nano`) for classifier + retriever + escalation; `mid` → `OPENAI_MODEL_MID` (default `gpt-4.1-mini`) for `response_specialist`; `OPENAI_MODEL` fallback; no per-agent model envs; no `high` tier in MVP | Price-efficient: spend mid only on customer-facing prose |

### Design principles

- Customer / operator feedback first (demo paths A/B/C before enterprise features).
- Minimal viable agent set and simplest orchestration that delivers core value.
- Observable by default (health, structured errors, Prompt Trace).
- Deploy scaffolding deferred to Deliver week (local dual-process first).

---

## Appendix A — Implementation Guidance for AI Development Agents

### Sprint 1 / Week 2→3 vertical slice (must pass before UI polish)

```text
POST /api/chat
  → FastAPI validate
  → sequential crew (classify → kb_search → compose → triage)
  → ChatResponse { decision, sources_used | packet + stub_ticket_id, reason_codes, steps[], trace_id, error=null }
  → UI shows reply + Talk-to-human CTA
```

**Exit:** demo paths A/B/C succeed against ≥10 FAQ KB. Operator strip may show `decision` + `reason_codes` from the same response.

**Defer until after slice works:** StatusLine animation polish, OperatorStrip expand UX, DisclosureBanner edge cases, Future Work stubs, dual-process layout niceties, `/api/last-result`.

### Epic sequence

1. **Setup** (`@project.mgr`): `frontend/`, `backend/`, `backend/config/`, `backend/kb/`, `.env.example`, manifests; `setup.md` — **no business logic**.  
2. **Backend** (`@backend.eng`): YAML agents/tasks with named `output_pydantic` models, tools (`kb_search` per ADR-13), `crew.kickoff`, FastAPI `POST /api/chat` + `/health` — **vertical slice first**.  
3. **Frontend** (`@frontend.eng`): thin chat shell (composer, reply, Talk-to-human, optimistic StatusLine) + mocks shaped like `ChatResponse`; polish strip/stubs after Integration smoke.  
4. **Integration** (`@integration.eng`): wire `lib/api.ts` to `/api/chat` only; map last response into chat + operator strip; verify resolve + escalate.  
5. **QA** (`@qa.eng`): unit + integration + AC-01…06 in `qa.md`.  
6. **Deliver** (`@devops.eng`): CI + deploy.md + user-guide — no app logic changes.

**Pilot / demo exit:** KB ≥10 articles; paths A/B/C succeed; operator strip shows decision + reason_codes from last `ChatResponse`; no secrets in repo.  
**Post-MVP order:** live ticketing → multi-turn clarifier → streaming → CSAT → persistence/SSO.

---

## Appendix B — Traceability (PRD → Architecture)

| PRD anchor | SAD element |
|------------|-------------|
| AC-01 / AC-01a Disclosure + human control | DisclosureBanner + Talk-to-human (§1–§2) |
| AC-01b Disclosure metadata | `meta.ai_disclosure` + Prompt Trace (§2) |
| AC-02 Pipeline | 4-agent sequential crew + `steps[]` (§2) |
| AC-03 Grounding | kb_search + refuse + `sources_used` (§2) |
| AC-04 Escalation packet | `packet` + `stub_ticket_id` on `ChatResponse`; reason_codes + ticket_stub (§2) |
| AC-05 Operator | OperatorStrip from last ChatResponse UI state; last-result optional (§2–§3, ADR-14) |
| AC-06 Health/failure | `/health` + error envelope `{code, message}` (§2–§4) |
| §10.1 Logical/Process/Deploy | §§2–3 |
| §10.3 API | §2 contracts |
| No DB / stub ticket | ADR-06, ticket_stub (§5) |
| MRD hybrid FCR / fail-open | ADR-11 (§4–§5) |
| Named task schemas | `ClassifierOutput`…`EscalationPacket` + mapper table (§2) |
| Retrieval floor + KB seed | ADR-13 (TF-IDF MVP); seed KB contract + demo queries A/B/C (§2) |
| Non-streaming StatusLine | ADR-15 (§2 FE) |
| Refuse→escalate; sentiment gate; timeout/HTTP | ADR-16, ADR-17, ADR-18 (§2, §5) |
| Model tiers (low×3, mid×1) | ADR-19 (§2 Controls, §3 env) |

---

## Architecture Validation Checklist

- [x] PRD requirements mapped to architectural components  
- [x] Agents designed for the domain and selected runtime (`crewai`)  
- [x] Frontend and backend contracts agree on schemas / non-streaming  
- [x] Secrets via env vars only  
- [x] MVP vs Future Work boundaries explicit  
- [x] Resolved `AAMAD_TARGET_RUNTIME` recorded in Audit  
- [x] Document structured around Overview / Logical / Physical / Quality / Decisions  

---

## Sources

- `project-context/1.define/prd.md` (primary)  
- `project-context/1.define/mrd.md` (market/feasibility context)  
- `project-context/1.define/context-summary.md`  
- `.cursor/templates/sad-template.md`  
- `.cursor/rules/adapter-crewai.mdc`, `.cursor/rules/adapter-registry.mdc`  
- `.cursor/agents/system-arch.md`, backend/frontend/integration/qa/project-mgr contracts  

## Assumptions

- User stories directory not present; AC IDs in PRD are authoritative for QA.  
- `OPENAI_API_KEY` (or compatible provider configured for CrewAI) available at runtime.  
- Folder names `frontend/` and `backend/` acceptable unless instructor mandates otherwise (PRD OQ #4).  
- MVP retrieval = **TF-IDF / bag-of-words** per ADR-13; embedding optional post-slice; managed vector SaaS deferred.  
- Seed KB = hand-authored Acme Cloud Markdown FAQs (`NN-slug.md`); not auto-generated; demo queries A/B/C locked in §2.  
- `sentiment` enum = `positive|neutral|negative`; `risk` / `urgency` enums = `low|medium|high`; escalate per ADR-17 (not negative-alone).  
- `ChatResponse.packet` / `stub_ticket_id` required on escalate (including Path B refuse path and preferred on AC-06b failures); `null` on resolve.  
- `refused` / `gap` never produce `decision=resolve` (ADR-16).  
- Temperature and tier→model defaults above are architecture guidance; Backend may override via env and must record resolved map in Audit.  
- Model tiers: three agents **low**, `response_specialist` **mid** (ADR-19); no per-agent model env vars.  
- Architecture epic produces docs only — no application code in this action.  
- `meta` on `ChatResponse` is additive for `AC-01b`; Integration maps when present and ignores if older mocks omit it.  
- Example config `security.require_security_assessment: true` → recommend `@security.eng` before Deliver even if course grading is TBD.  
- MRD “learns and adapts” = offline KB/prompt updates post-MVP, not online fine-tuning (aligned with PRD).  
- Operator grading uses last `ChatResponse` in UI (ADR-14); `/api/last-result` is not an MVP Integration exit criterion.  
- StatusLine is local optimistic animation only until JSON returns (ADR-15); FE abort 50–60s.  
- PRD §10.3 schema must match this SAD; where they diverge, **SAD §2 is authoritative** for Build until PRD is synced.  
- CORS includes both `localhost:3000` and `127.0.0.1:3000`.  
- Concurrent demo target is best-effort on a single process; serial kickoff is acceptable.  
- GDPR log retention duration remains TBD (Open Question); minimize PII in traces meanwhile.

## Open Questions

1. Confirm instructor monorepo naming if not `frontend/` + `backend/`.  
2. ~~`/api/last-result` vs UI state~~ — **Resolved (ADR-14):** UI state from last `ChatResponse`; last-result optional polish.  
3. ~~KB retrieval algorithm / similarity floor~~ — **Resolved (ADR-13):** TF-IDF / bag-of-words cosine for MVP; floor `0.35`; seed contract + demo queries locked.  
4. Security assessment graded vs optional for this course (PRD OQ #5); until answered, treat as recommended gate.  
5. Public hosting target for Week 6 (local-only vs single cloud VM).  
6. Disclosure UX: acknowledge-to-dismiss vs always-persistent banner — either OK; FE documents choice in `frontend.md`.  
7. GDPR / Prompt Trace retention duration (days) for course machines.  
8. Legal disclosure copy owner (generic “You are chatting with an AI assistant” until provided — PRD OQ #2).  
9. ~~Refuse vs escalate / sentiment gate / timeout HTTP~~ — **Resolved (ADR-16…18).**  
10. ~~Per-agent vs tiered models~~ — **Resolved (ADR-19):** `OPENAI_MODEL_LOW` / `OPENAI_MODEL_MID` + agent→tier map.

## Audit

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-13T07:51:00-05:00 |
| Persona id | system-arch |
| Action | sharpen-sad (polish: Path B wording, Future Work/exclusions, agents.yaml model_tier) |
| Prior action | sharpen-sad (ADR-19 model tiers: low×3 + mid×1) @ 2026-08-13T07:45:00-05:00 |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai (PRD-locked; env unset → adapter default) |
| Prompt Trace | Omitted — architecture synthesis; no secrets |
| Model / controls | Deterministic artifact write; N/A temperature for file output |
| Adapter rule | `.cursor/rules/adapter-crewai.mdc` |
| Warning | None — runtime resolved cleanly to crewai |
| Change note | Path B escalate-only wording; Future Work + exclusions for Ollama/high tier/rate limit; agents.yaml model_tier sketch |
