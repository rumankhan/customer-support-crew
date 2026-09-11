# Backend Implementation: Multi-Agent Customer Support Crew

**Epic**: Backend  
**Persona**: @backend.eng  
**Action**: develop-be, define-agents, implement-endpoint, document-backend  
**PRD**: `project-context/1.define/prd.md`  
**SAD**: `project-context/1.define/sad.md`  
**Runtime**: `crewai` (locked per PRD §3)

---

## 1. Overview

This document details the backend implementation for the Multi-Agent Customer Support Crew MVP. The backend implements:

- **4 specialized CrewAI agents** with structured Pydantic outputs (YAML in `backend/config/`)
- **Sequential task pipeline** with context chaining
- **SQLite FTS5 knowledge retrieval** over `backend/data/support.db` (seeded from `backend/kb/articles.csv`; SAD ADR-20)
- **Telegram HITL** for policy actions (billing credit, ETF waiver; SAD ADR-21)
- **FastAPI** JSON `POST /api/chat` plus **SSE** `POST /api/chat/stream`
- **Crew timeout** `CHAT_TIMEOUT_SECONDS` (default 180s) and HITL wait `HITL_TIMEOUT_SECONDS` (default 300s)
- **Prompt trace logging** for auditability

**Core Value**: Grounded chat resolution, clean human escalation with a context packet, or manager-gated policy action — without a blind queue or black-box FAQ bot.

### Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Pydantic Models | ✅ Complete | `backend/models.py` — crew outputs + `ChatResponse` (`pending_approval`, `approval`) |
| KB Search Tool | ✅ Complete | `backend/tools.py` — SQLite FTS5, floor 0.35 |
| Account / order lookup | ✅ Complete | Stub tables in `support.db` |
| Ticket Stub Tool | ✅ Complete | `backend/tools.py` — in-memory stub |
| Agents (4) | ✅ Complete | `backend/crew.py` + `config/agents.yaml` |
| Tasks (4) | ✅ Complete | `config/tasks.yaml` — sequential with context |
| FastAPI Endpoints | ✅ Complete | `/api/chat`, `/api/chat/stream`, `/api/approvals/*`, `/health` |
| HITL + Telegram | ✅ Complete | `approval_service.py`, `telegram_bot.py` |
| Error Handling | ✅ Complete | Timeout, LLM failure, KB unavailable |
| Prompt Trace | ✅ Complete | JSON logs to LOG_DIR |
| Seed KB | ✅ Complete | 12 B-Mobile FAQs in CSV → FTS5 on startup |

---

## 2. Architecture

### Component Structure

```
backend/
├── main.py               # FastAPI app + lifespan (SQLite + optional Telegram poll)
├── crew.py               # CustomerSupportCrew (YAML + tools)
├── chat_service.py       # Mapper, guardrails, policy-action detect
├── streaming.py          # SSE events including HITL wait
├── approval_service.py   # SQLite approval queue + customer copy
├── telegram_bot.py       # Manager Approve/Deny + deny reason
├── db.py                 # Schema + seed (kb, stubs, approvals)
├── models.py             # Pydantic schemas
├── tools.py              # kb_search (FTS5), account/order lookup, ticket_stub
├── llm_config.py         # LLM provider resolution (OpenAI/Ollama)
├── config/agents.yaml + tasks.yaml
├── kb/articles.csv       # Canonical FAQ seed/export
├── data/support.db       # Live DB (local; not committed)
└── scripts/              # migrate_kb_csv_to_sqlite, telegram_get_chat_id, validate_kb_hitl
```

### Agent Pipeline (Sequential)

```
classify_inquiry (query_classifier)
    ↓ context
retrieve_knowledge (knowledge_retriever + kb_search tool)
    ↓ context
compose_response (response_specialist)
    ↓ context
triage_and_escalate (escalation_manager + ticket_stub tool)
    ↓
ChatResponse (decision: resolve | escalate)
```

### Data Flow

```
POST /api/chat {message, request_human, ...}
    ↓
FastAPI validation (max 4000 chars)
    ↓
crew.kickoff() [CHAT_TIMEOUT_SECONDS, default 180s]
    ↓
4 sequential tasks → Pydantic outputs
    ↓
Mapper: task outputs → ChatResponse
    ↓
Write prompt trace → LOG_DIR/{trace_id}.json
    ↓
Return HTTP 200 + JSON (success or error envelope)
```

---

## 3. Implementation Details

### 3.1 Pydantic Models (`backend/models.py`)

Nine structured models aligned with SAD §2 contracts:

**Agent Task Outputs:**
1. `ClassifierOutput` — intent (str), urgency (low|medium|high), entities (list), confidence (float)
2. `RetrieverOutput` — passages (list with score), citations, gap (bool)
3. `ResponseOutput` — reply (str), sources_used, refused (bool)
4. `EscalationOutput` — decision (resolve|escalate), sentiment, risk, reason_codes, packet (optional)
5. `EscalationPacket` — full context for human agents (intent, urgency, customer_message, citations_attempted, draft_reply, sentiment, risk, reason_codes, stub_ticket_id)

**API Schemas:**
6. `ChatRequest` — message (1-4000 chars), request_human (bool), session_id (optional), disclosure_acknowledged (optional)
7. `ChatResponse` — decision, reply, sources_used, sentiment, risk, reason_codes, steps, trace_id, packet, stub_ticket_id, meta, error
8. `MetaInfo` — ai_disclosure (always true), disclosure_acknowledged (echoed)
9. `ErrorDetail` — code (llm_or_timeout | validation_error | kb_unavailable | system_error), message

**Additional Helpers:**
- `PassageResult` — title, snippet, score (for retriever passages)
- `Citation` — title, snippet (for grounded sources)
- `StepSummary` — agent, summary (for pipeline visibility)
- `HealthResponse` — status ("ok")

### 3.2 Tools (`backend/tools.py`)

#### KBSearchTool

**Purpose**: Search the **live** FAQ index in SQLite FTS5 (`backend/data/support.db`).  
**Not** a runtime CSV reader. `backend/kb/articles.csv` is only the authoring/seed file that populates the DB (SAD ADR-20). Former TF-IDF-over-CSV path (ADR-13) is historical.

**Implementation**:
- Opens `KB_DB_PATH` (created/seeded by `ensure_database()` on startup from the CSV)
- FTS5 `MATCH` over title + body; AND of content tokens; English stopwords
- Score `min(1.0, abs(bm25) / 10.0)`; keep passages ≥ `KB_SIMILARITY_FLOOR` (default 0.35)
- Top-k via `KB_TOP_K` (default 3); `gap=true` if none meet the floor

**Configuration**:
- `KB_DB_PATH` (default: `backend/data/support.db`) — **live**
- `KB_DIR` / `KB_FILE` (CSV seed only; `backend/kb` + `articles.csv`)
- `KB_SIMILARITY_FLOOR` (default: `0.35`)

**Output**: JSON string matching `RetrieverOutput` schema

**Re-seed:** `python -m backend.scripts.migrate_kb_csv_to_sqlite` (or restart backend)

#### TicketStubTool

**Purpose**: Generate stub ticket ID for escalations (no live ticketing in MVP).

**Implementation**:
- Returns `STUB-{uuid}` format (8-char hex, uppercase)
- No persistence or external API calls
- Future: integrate with Zendesk/Intercom/etc.

#### AccountLookupTool / OrderLookupTool

Stub rows in `support.db` (`stub_accounts`, `stub_orders`) for HITL demos (`ACC-1001`, `ACC-2002`, `ORD-*`).

### 3.2.1 HITL policy actions (`backend/approval_service.py`)

After the crew maps to `ChatResponse`, `detect_policy_action()` may set `decision=pending_approval`. Vague “credit for outage” / “waive my fee” (no account/amount) still HITL with lookup # 1–100. Customer waits on SSE; manager decides in Telegram. Deny with a typed reason uses that text only; `/skip` uses contract boilerplate.

### 3.3 Crew Orchestration (`backend/crew.py`)

#### CustomerSupportCrew Class

**Initialization**:
- Loads LLM provider configuration via `LLM_PROVIDER` (default `openai`):
  - **OpenAI** (default): Uses `OPENAI_MODEL_LOW` / `OPENAI_MODEL_MID` / `OPENAI_MODEL`
  - **Ollama Cloud**: Uses `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` via LiteLLM OpenAI-compatible route
- Loads model tier configuration per SAD ADR-19:
  - Low tier (default `gpt-4o-mini` / `gemma4:31b`) → classifier, retriever, escalation_manager
  - Mid tier (default `gpt-4o-mini` / `gemma4:31b`) → response_specialist
  - Fallback: `OPENAI_MODEL` (OpenAI) or `OLLAMA_MODEL` (Ollama)
- **Loads agent and task definitions from YAML** (`backend/config/agents.yaml`, `backend/config/tasks.yaml`) per CrewAI adapter rules
- Creates 4 Agent instances with CrewAI LLM objects
- Temperature: 0.2 (low tier), 0.4 (mid tier)
- `allow_delegation=False` on all agents
- `max_iter` from env (default 12)

**Agent Definitions**:

1. **query_classifier**
   - Role: Inquiry Classification Specialist
   - Goal: Classify intent, entities, urgency
   - Tools: None
   - LLM: low tier
   - Output: `ClassifierOutput`

2. **knowledge_retriever**
   - Role: Knowledge Base Research Specialist
   - Goal: Retrieve grounded passages with citations
   - Tools: `kb_search_tool`
   - LLM: low tier
   - Output: `RetrieverOutput`

3. **response_specialist**
   - Role: Customer Response Composer
   - Goal: Draft replies using only grounded evidence
   - Tools: None
   - LLM: **mid tier** (higher quality for customer-facing prose)
   - Output: `ResponseOutput`

4. **escalation_manager**
   - Role: Sentiment, Risk & Escalation Coordinator
   - Goal: Decide resolve vs escalate; package context
   - Tools: `ticket_stub_tool`
   - LLM: low tier
   - Output: `EscalationOutput`

**Task Creation** (`_create_tasks`):
- Loads task definitions from `backend/config/tasks.yaml` per CrewAI adapter rules
- Dynamically creates 4 Task objects for each kickoff
- Injects `{message}`, `{request_human}`, and `{classifier_confidence_min}` into YAML template descriptions
- Maps `output_pydantic` field names to Pydantic model classes
- Configures `context` dependencies from YAML: 
  - retrieve → [classify]
  - compose → [classify, retrieve]
  - triage → [classify, retrieve, compose]

**Kickoff Execution**:
- Creates Crew with `Process.sequential`
- `memory=False` for reproducibility (adapter baseline)
- `max_rpm` from env (default 10)
- `verbose=True` for observability
- Returns dict with result, tasks, inputs

**Escalation Rules** (enforced in `triage_and_escalate` task description in `backend/config/tasks.yaml`):

| # | Rule | Decision |
|---|------|----------|
| 0 | Greeting / small_talk / thanks / farewell; `request_human=false` | **RESOLVE** |
| 0a | `out_of_scope` intent; `request_human=false` | **RESOLVE** |
| 0b | `urgency=low` + neutral/positive sentiment + low/medium risk; `request_human=false` | **RESOLVE** |
| 1 | `request_human=true` | ESCALATE (`request_human`) |
| 2 | `gap=true` or `refused=true` (unless 0 / 0a / 0b apply) | ESCALATE (`retrieval_gap` / `refused`) |
| 3 | `confidence < CLASSIFIER_CONFIDENCE_MIN` | ESCALATE (`low_confidence`) |
| 4 | `risk=high` | ESCALATE (`high_risk_sentiment`) |
| 5 | `sentiment=negative` AND (risk/gap/refused/low confidence/request_human) | ESCALATE (`high_risk_sentiment`) |
| — | Otherwise | **RESOLVE** |

### Guardrails — deterministic post-processing (2026-08-27)

The escalation agent may still emit `decision=escalate` on KB gaps. **`backend/chat_service.py`** applies overrides in `map_to_response()` so customer-facing behavior matches product intent:

| Function | When applied | Effect |
|----------|--------------|--------|
| `apply_greeting_resolve_override()` | Classifier intent is greeting / small_talk | `decision=resolve`; strip soft reason codes; default welcome reply |
| `apply_low_urgency_resolve_override()` | `urgency=low`, neutral/positive, not high risk, no hard reason codes | `decision=resolve`; gap reply without human handoff |
| `apply_out_of_scope_reply_policy()` | Intent is `out_of_scope` / off-topic | `decision=resolve`; `OUT_OF_SCOPE_REPLY` or sanitized reply (strips “human agent” pitches) |
| `filter_grounded_sources()` | After crew mapping | Re-query FTS on the **customer message**; drop citations whose titles are not live KB hits (Path B fabrication) |
| `ensure_escalation_artifacts()` | `decision=escalate` or `request_human=true` | Packet required; `stub_ticket_id` must match `STUB-` + 8 hex (replace LLM `TICKET-` / `TKT-` ids) |

**Hard escalate reason codes** (overrides never apply): `request_human`, `high_risk_sentiment`, `timeout`, `system_error`.

**Soft reason codes** (stripped on resolve override): `retrieval_gap`, `refused`, `low_confidence`.

**Compose guardrail:** `compose_response` in `tasks.yaml` — out-of-scope refusals must not recommend a human agent; in-scope KB gaps may suggest another B-Mobile question only.

**SAD note:** Original ADR-16 required gap/refuse → escalate. MVP guardrails **relax** that for greetings, low-urgency calm interactions, and out-of-scope questions — document under Assumptions until PRD/SAD are formally amended.

### 3.4 FastAPI Backend (`backend/main.py`)

#### Endpoints

**GET /health**
- Returns `{"status": "ok"}` (AC-06a)
- No auth required

**POST /api/chat/stream** (primary)
- SSE progress via `backend/streaming.py` + `chat_service.map_to_response()`
- Events: `started`, `stage`, `heartbeat`, `complete` | `error`
- Timeout: `CHAT_TIMEOUT_SECONDS` (default 180s)

**POST /api/chat** (legacy JSON)
- Request: `ChatRequest` (validated by Pydantic)
- Process: kickoff → `map_to_response()` → prompt trace → JSON
- Used by scripts/tests (`test_ollama_backend.py`)

**GET /api/last-result**
- Optional polish endpoint (not required for AC-05 per SAD ADR-14)
- Returns in-memory `last_result` (lost on restart)
- 404 if no result available

#### Error Handling

All errors return HTTP 200 with error envelope (prefer consistent schema for FE):

| Error Code | When | Response |
|------------|------|----------|
| `llm_or_timeout` | Crew timeout or LLM failure | decision=escalate, minimal packet, reason_codes=["timeout"] |
| `kb_unavailable` | SQLite KB missing/unreadable (`support.db` / FTS error) — not “CSV missing at search time” | decision=escalate, minimal packet, reason_codes=["system_error"] |
| `system_error` | Unexpected exception | decision=escalate, minimal packet, reason_codes=["system_error"] |
| `validation_error` | Invalid ChatRequest (400 before kickoff) | Optional: prefer same envelope shape when practical |

**System-Failure Packet Policy** (SAD §2):
- On timeout/error, still create minimal EscalationPacket when possible
- Include customer_message, request_human, partial intent/urgency/citations from completed tasks
- Set missing fields to "" / [] / defaults
- Generate stub_ticket_id
- Helps operators avoid blind escalations

#### Mapper (`map_to_response` in `backend/chat_service.py`)

Maps crew task outputs to ChatResponse fields per SAD §2 (shared by JSON and SSE paths):

| Source | Maps to ChatResponse |
|--------|---------------------|
| ResponseOutput.reply | reply |
| ResponseOutput.sources_used | sources_used (empty on escalate) |
| EscalationOutput.decision | decision (may be overridden by guardrails) |
| EscalationOutput.sentiment | sentiment |
| EscalationOutput.risk | risk |
| EscalationOutput.reason_codes | reason_codes |
| EscalationOutput.packet | packet (null after resolve guardrails) |
| EscalationPacket.stub_ticket_id | stub_ticket_id |
| Each completed task | steps[] entry {agent, summary} |
| New UUID | trace_id |
| Request disclosure fields | meta {ai_disclosure, disclosure_acknowledged} |
| Exception/timeout | error + escalate envelope |

#### Prompt Trace Logging (`write_prompt_trace` in `backend/chat_service.py`)

Writes `{LOG_DIR}/{trace_id}.json` per SAD §2 minimum schema:

**Required Fields**:
- `trace_id`, `timestamp` (ISO-8601)
- `inputs` — {message (truncated to 200 chars), request_human, session_id, disclosure_acknowledged}
- `steps` — same as API steps[] (partial on timeout)
- `decision`, `reason_codes`
- `meta` — {ai_disclosure, disclosure_acknowledged}
- `error` — {code, message} or null

**Recommended Fields**:
- `model_tiers` — resolved {low, mid} model names
- `elapsed_ms` — request duration

**Redaction**: Truncates message to 200 chars; never stores API keys; PII minimization.

**Location**: Default `project-context/2.build/logs` (configurable via `LOG_DIR`).

#### Lifecycle

- Startup: `ensure_database()` then `CustomerSupportCrew`; optional Telegram long-poll if `TELEGRAM_ENABLED=true`
- Shutdown: Graceful cleanup
- In-memory state: `crew_instance` (global), `last_result` (process-local, racy under concurrency)

---

## 4. Configuration

### Environment Variables (`.env.example`)

**LLM Provider Configuration**:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `openai` | LLM provider: `openai` or `ollama` |

**OpenAI Configuration** (when `LLM_PROVIDER=openai`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | *(required)* | OpenAI API authentication |
| `OPENAI_MODEL_LOW` | `gpt-4o-mini` | Low-tier model (3 agents) |
| `OPENAI_MODEL_MID` | `gpt-4o-mini` | Mid-tier model (response_specialist) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Fallback if tier env unset |

**Ollama Cloud Configuration** (when `LLM_PROVIDER=ollama`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_API_KEY` | *(required)* | Ollama Cloud API key (https://ollama.com/settings/keys) |
| `OLLAMA_BASE_URL` | `https://ollama.com/v1` | Ollama Cloud endpoint |
| `OLLAMA_MODEL` | `gemma4:31b` | Ollama model (used for all tiers) |

**Application Configuration**:

| Variable | Default | Purpose |
|----------|---------|---------|
| `AAMAD_TARGET_RUNTIME` | `crewai` | Runtime adapter (locked for MVP) |
| `BACKEND_PORT` | `8000` in `.env.example`; local demo often **8001** | FastAPI listen port |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8001` | FE API base |
| `CHAT_TIMEOUT_SECONDS` | `180` | Crew wall-clock for JSON + SSE |
| `MAX_ITER` | `12` | Max iterations per agent |
| `MAX_RPM` | `10` | Max requests per minute (crew) |
| `CLASSIFIER_CONFIDENCE_MIN` | `0.55` | Confidence threshold for escalation |
| `KB_DIR` | `backend/kb` | CSV seed directory |
| `KB_FILE` | `articles.csv` | Canonical FAQ export |
| `KB_DB_PATH` | `backend/data/support.db` | Live FTS5 + stubs + approvals |
| `KB_SIMILARITY_FLOOR` | `0.35` | FTS rank mapped to 0–1 gap floor |
| `KB_TOP_K` | `3` | Max passages |
| `TELEGRAM_ENABLED` | `false` | Start manager bot polling |
| `TELEGRAM_BOT_TOKEN` | *(required if enabled)* | BotFather token |
| `TELEGRAM_MANAGER_CHAT_ID` | *(required if enabled)* | Allow-listed chat (groups often negative) |
| `HITL_TIMEOUT_SECONDS` | `300` | SSE wait for Approve/Deny |
| `LOG_DIR` | `project-context/2.build/logs` | Prompt trace directory |
| `OPERATOR_API_KEY` | *(optional)* | Gate for /api/last-result |

### Dependencies (`backend/requirements.txt`)

**Core**:
- `crewai>=0.80.0` — Multi-agent framework
- `crewai-tools>=0.12.0` — Tool base classes
- `fastapi>=0.104.0` — HTTP API
- `uvicorn[standard]>=0.24.0` — ASGI server
- `pydantic>=2.5.0` — Data validation

**ML/NLP** (legacy; live retrieval is stdlib `sqlite3` FTS5):
- `scikit-learn>=1.3.0` / `numpy` — still listed in `requirements.txt`; **unused** after ADR-20

**LLM**:
- `openai>=1.0.0` — OpenAI provider (also used for Ollama Cloud via LiteLLM compatibility)
- `litellm` — LLM provider abstraction (bundled with CrewAI)

**Utilities**:
- `python-dotenv>=1.0.0` — Environment loading
- `pyyaml>=6.0.0` — YAML config loading per CrewAI adapter

### Seed Knowledge Base (`backend/kb/articles.csv`)

**Format**: CSV with RFC4180 quoting, columns `id`, `title`, `body`

**Count**: 12 B-Mobile FAQ rows (meets ≥10 requirement)

**Domain**: Fictional B-Mobile consumer mobile carrier

**Coverage**:
- Account PIN reset (Path A demo query)
- Billing/invoice download
- Device shipping tracking
- Returns/refunds
- Plan upgrade/downgrade
- Account email change
- Data usage checking
- Roaming setup
- eSIM setup
- Lost/stolen phone
- Number porting
- Voicemail setup

**Path A Query** (hit): `"How do I reset my B-Mobile My Account PIN?"` → **resolve** with sources

**Path B Query** (miss): `"What is your quantum warranty for the hardware drone?"` → **escalate** (gap=true, no fabrication)

**Path C Query**: `"I want to talk to a human now — this billing charge is ridiculous!"` with `request_human=true` → **escalate** with full packet

---

## 5. API Contracts

### POST /api/chat/stream (primary — SSE)

**Transport:** `text/event-stream` via `sse-starlette` (`EventSourceResponse`).

**Request:** Same `ChatRequest` body as `/api/chat`.

**Events:**

| Event | Data | Notes |
|-------|------|-------|
| `started` | `{ "trace_id": "uuid" }` | Kickoff accepted |
| `stage` | `{ "trace_id", "agent", "status": "running"\|"completed", "summary"? }` | CrewAI `task_callback` |
| `heartbeat` | `{ "trace_id" }` | Every 15s while crew runs |
| `approval_required` | `{ approval_id, reply_pending, response }` | HITL wait — manager notified on Telegram |
| `approval_decided` | `{ outcome, reply, response }` | Approved or denied |
| `approval_timeout` | `{ reply, response }` | No decision within `HITL_TIMEOUT_SECONDS` |
| `complete` | `{ "response": ChatResponse }` | HTTP 200 stream end |
| `error` | `{ "response": ChatResponse }` | Error envelope; still valid `ChatResponse` |

**Implementation:** `backend/streaming.py`, shared mapper in `backend/chat_service.py`.

**Timeout:** `CHAT_TIMEOUT_SECONDS` env (default **180**). HITL wait is `HITL_TIMEOUT_SECONDS` (default **300**) after `approval_required`.

### GET /api/approvals/* and POST /api/approvals/{id}/decide

SQLite-backed queue used by Telegram and the read-only `/operator` page.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/approvals/pending` | Open requests |
| GET | `/api/approvals/history` | Recent decided |
| GET | `/api/approvals/{id}/status` | Includes `customer_reply` for UI poll fallback |
| POST | `/api/approvals/{id}/decide` | `{ decision: approve\|deny, operator_note? }` |

### POST /api/chat (legacy JSON)

**Request** (`ChatRequest`):
```json
{
  "message": "How do I reset my B-Mobile My Account PIN?",
  "request_human": false,
  "session_id": "optional-uuid",
  "disclosure_acknowledged": true
}
```

**Response** (`ChatResponse`) — Success (resolve):
```json
{
  "decision": "resolve",
  "reply": "To reset your B-Mobile My Account PIN, open the B-Mobile app...",
  "sources_used": [
    {
      "title": "Reset your B-Mobile My Account PIN",
      "snippet": "Open the B-Mobile app or visit My Account on b-mobile.example..."
    }
  ],
  "sentiment": "neutral",
  "risk": "low",
  "reason_codes": [],
  "steps": [
    {"agent": "query_classifier", "summary": "Classified as account PIN reset, medium urgency..."},
    {"agent": "knowledge_retriever", "summary": "Found 1 article with 0.87 similarity..."},
    {"agent": "response_specialist", "summary": "Composed grounded reply with citation..."},
    {"agent": "escalation_manager", "summary": "Resolved with low risk, neutral sentiment..."}
  ],
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-1234567890ab",
  "packet": null,
  "stub_ticket_id": null,
  "meta": {
    "ai_disclosure": true,
    "disclosure_acknowledged": true
  },
  "error": null
}
```

**Response** (`ChatResponse`) — Escalate (gap):
```json
{
  "decision": "escalate",
  "reply": "I don't have information about quantum warranties in my knowledge base...",
  "sources_used": [],
  "sentiment": "neutral",
  "risk": "medium",
  "reason_codes": ["retrieval_gap", "refused"],
  "steps": [ /* 4 step summaries */ ],
  "trace_id": "...",
  "packet": {
    "intent": "warranty inquiry",
    "urgency": "low",
    "customer_message": "What is your quantum warranty for the hardware drone?",
    "request_human": false,
    "citations_attempted": [],
    "draft_reply": "I don't have information...",
    "sentiment": "neutral",
    "risk": "medium",
    "reason_codes": ["retrieval_gap", "refused"],
    "stub_ticket_id": "STUB-A1B2C3D4"
  },
  "stub_ticket_id": "STUB-A1B2C3D4",
  "meta": { /* ... */ },
  "error": null
}
```

**Response** (`ChatResponse`) — Error (timeout):
```json
{
  "decision": "escalate",
  "reply": "Request timed out. Please talk to a human agent.",
  "sources_used": [],
  "sentiment": "neutral",
  "risk": "medium",
  "reason_codes": ["timeout"],
  "steps": [ /* partial steps from completed tasks */ ],
  "trace_id": "...",
  "packet": {
    "intent": "",
    "urgency": "medium",
    "customer_message": "...",
    "request_human": false,
    "citations_attempted": [],
    "draft_reply": "",
    "sentiment": "neutral",
    "risk": "medium",
    "reason_codes": ["timeout"],
    "stub_ticket_id": "STUB-..."
  },
  "stub_ticket_id": "STUB-...",
  "meta": { /* ... */ },
  "error": {
    "code": "llm_or_timeout",
    "message": "Request timed out (CHAT_TIMEOUT_SECONDS)..."
  }
}
```

### GET /health

**Response** (`HealthResponse`):
```json
{
  "status": "ok"
}
```

---

## 6. Testing & Validation

### Manual Testing (Vertical Slice)

Operator runbook (local + Docker Compose): [`RUNNING.md`](../../RUNNING.md). Deliver packaging: [`project-context/3.deliver/deploy.md`](../3.deliver/deploy.md).

**Prerequisites**:
1. Copy `.env.example` to `.env` and set provider keys (`OLLAMA_API_KEY` or `OPENAI_API_KEY`) plus `OPERATOR_API_KEY`
2. Install dependencies: `pip install -r backend/requirements.txt`
3. Verify `backend/kb/articles.csv` exists with 12 rows (seeds SQLite FTS5 on startup)

**Start Server** (repo root):
```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
# Server starts on http://127.0.0.1:8001
# Or: docker compose up --build  → app at http://127.0.0.1:3000
```

**Test Health**:
```bash
curl http://127.0.0.1:8001/health
# Expected: {"status":"ok"}
```

**Test Path A (Resolve)**:
```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I reset my B-Mobile My Account PIN?",
    "request_human": false,
    "disclosure_acknowledged": true
  }'
# Expected: decision="resolve", sources_used non-empty, packet=null
```

**Test Path B (Escalate - Gap)**:
```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is your quantum warranty for the hardware drone?",
    "request_human": false
  }'
# Expected: decision="escalate", reason_codes includes "retrieval_gap" or "refused", packet present
```

**Test Path C (Escalate - Request Human)**:
```bash
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want to talk to a human now - this billing charge is ridiculous!",
    "request_human": true
  }'
# Expected: decision="escalate", reason_codes includes "request_human", packet with 4 steps
```

**Verify Prompt Traces**:
```bash
ls -l project-context/2.build/logs/
# Should contain {trace_id}.json files for each request
cat project-context/2.build/logs/{trace_id}.json
# Verify minimum schema: trace_id, timestamp, inputs, steps, decision, reason_codes, meta, error
```

### Integration Testing

**With Frontend** (Integration Epic):
1. Frontend streams `POST /api/chat/stream` with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001`
2. Verify CORS allows `localhost:3000` and `127.0.0.1:3000`
3. Map response fields to chat UI + operator strip
4. Test error path (stop backend mid-request) → safe message + Talk-to-human CTA

### Unit Testing (QA Epic)

Recommended test coverage:
- Classifier output shape (`ClassifierOutput` validation)
- Retriever gap detection (`KB_SIMILARITY_FLOOR` edge cases)
- Escalation rules (each of 5 conditions)
- Error envelope generation (timeout, kb_unavailable, system_error)
- Prompt trace schema compliance (minimum required fields)
- Stub ticket ID format (`STUB-` prefix, 8-char hex)

---

## 7. Known Limitations & Future Work

### MVP Scope Constraints

**Out of Scope** (per Backend persona prohibited-actions and PRD §10.3, **except** the ADR-20/21 demo store):
- ❌ Conversation-history / session database (P2)
- ✅ Local SQLite `support.db` for FAQ FTS5, stub accounts/orders, HITL rows (ADR-20/21)
- ❌ Live Zendesk/Intercom/CRM integration (stub only)
- ✅ SSE orchestration progress (`POST /api/chat/stream`) — 2026-08-27
- ❌ LLM token streaming via SSE/WebSocket (future)
- ❌ Multi-turn clarification state machine
- ❌ CSAT survey integration
- ❌ Analytics dashboard / metrics aggregation
- ❌ Horizontal scaling / shared session store
- ❌ Managed vector DB (e.g., Pinecone, Weaviate)
- ❌ SSO/IAM authentication
- ❌ Fifth agent or hierarchical process
- ❌ MCP servers
- ❌ Per-agent model env vars (use tiers only per ADR-19)
- ❌ API rate limiting middleware
- ❌ Local Ollama (self-hosted) - Ollama Cloud is supported via OpenAI-compatible route

### Technical Debt

1. **Concurrency**: Single process, `last_result` is racy under concurrent requests (acceptable for course demo)
2. **KB Indexing**: FTS5 rebuilt when `ensure_database` / migrate script runs; edit CSV then re-migrate
3. **Timeout Granularity**: `CHAT_TIMEOUT_SECONDS` (default 180) for crew; HITL wait is separate (300s)
4. **Error Resilience**: No retry logic on transient LLM failures (relying on crew `max_retry_limit`)
5. **Observability**: Basic structured logs; no APM/tracing (e.g., Datadog, Sentry)

### Future Enhancements (Priority P1/P2)

**P1** (post-MVP, before production):
- Live ticketing connector with idempotent mutations
- Streaming UI via SSE (requires agent-by-agent output vs full kickoff)
- Multi-turn clarifier (stateful follow-up questions)
- CSAT in-chat survey
- Persistent DB for conversation history
- Managed vector DB for semantic search (e.g., OpenAI embeddings)

**P2** (enterprise features):
- Voice channel integration (CCaaS)
- Autonomous CRM mutations with policy engine
- Online learning / continuous fine-tuning
- Sales+support dual orchestration
- Outcome-based billing metering
- SSO/IAM with least-privilege roles
- Horizontal scaling with shared Redis session store
- Biometric emotion detection (requires legal review per MRD)

### Open Questions

1. GDPR log retention duration (days) for prompt traces — TBD by operator
2. Public hosting target for Week 6 Deliver (local-only vs cloud VM)
3. Security assessment graded/required for course (recommended before Deliver)
4. Disclosure UX: acknowledge-to-dismiss vs always-persistent banner (FE decision)
5. Legal disclosure copy owner (working default: "You are chatting with the B-Mobile AI assistant")

---

## 8. Deployment Notes

### Local Development

**Prerequisites**:
- Python 3.10+
- OpenAI API key (or compatible provider)

**Setup**:
```bash
# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set OPENAI_API_KEY

# Verify KB exists
cat backend/kb/articles.csv
# Should show 12 B-Mobile FAQ rows

# Run server (repo root)
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
# Server starts on http://127.0.0.1:8001
```

**Logs**:
- Application logs: stdout (structured JSON recommended for production)
- Prompt traces: `project-context/2.build/logs/{trace_id}.json`

### Docker / Compose (Week 6 Deliver)

Future: `Dockerfile` + `docker-compose.yml` with:
- `backend` service: Python + FastAPI + CrewAI
- `frontend` service: Next.js
- Volumes for KB and logs
- Secrets via env vars (never in image)

### CI/CD (Week 6 Deliver)

Recommended pipeline stages:
1. **Lint**: `ruff` or `flake8`
2. **Typecheck**: `mypy backend/` (optional)
3. **Test**: `pytest tests/` (when QA provides unit tests)
4. **Build**: Package backend + dependencies
5. **Deploy**: Manual promotion only (no auto-deploy without authorization)

---

## 9. Traceability

### PRD/SAD Compliance

| PRD Requirement | Implementation | Evidence |
|----------------|----------------|----------|
| AC-01 AI Disclosure | `meta.ai_disclosure=true` in ChatResponse | `backend/main.py` _map_to_response |
| AC-01b Disclosure metadata | `meta.disclosure_acknowledged` echoed | ChatRequest → ChatResponse.meta |
| AC-02 Multi-agent pipeline | 4 sequential tasks with context chaining | `backend/crew.py` _create_tasks |
| AC-02c Prompt Trace | JSON logs to LOG_DIR | `backend/main.py` _write_prompt_trace |
| AC-03 Grounded answers + refusal | kb_search + refused flag + gap detection | `backend/tools.py`, tasks.yaml compose_response |
| AC-04 Escalation packet | EscalationPacket on decision=escalate | `backend/models.py`, crew.py triage task |
| AC-06a Health check | GET /health → {status: ok} | `backend/main.py` health_check |
| AC-06b Failure path | Error envelope + escalate + minimal packet | `backend/main.py` _error_response |
| §3 Runtime=crewai | CustomerSupportCrew uses CrewAI primitives | `backend/crew.py` imports + Crew() |
| §3 4 agents | query_classifier, knowledge_retriever, response_specialist, escalation_manager | `backend/crew.py` _create_agents |
| §3 Local KB | SQLite FTS5 over `backend/data/support.db` (seed: articles.csv) | `backend/tools.py` KBSearchTool |
| §3 Ticket stub | STUB-{uuid} format | `backend/tools.py` TicketStubTool |
| §10.3 Named Pydantic models | 9 models matching SAD §2 | `backend/models.py` |
| SAD ADR-13 TF-IDF retrieval | **Superseded** by ADR-20 SQLite FTS5 | `backend/tools.py` KBSearchTool |
| SAD ADR-16 Refuse→escalate | refused=true → decision=escalate | triage_and_escalate task rules |
| SAD ADR-18 timeout | `CHAT_TIMEOUT_SECONDS` default 180s; HITL 300s | `backend/chat_service.py`, `backend/streaming.py` |
| SAD ADR-19 Model tiers | low (3 agents), mid (1 agent), tier→model map | `backend/crew.py` __init__, _create_agents |

### Agent/Task Alignment with SAD §2

| SAD Agent | Implemented | Role | Tools | Model Tier | Output |
|-----------|-------------|------|-------|------------|--------|
| query_classifier | ✅ | Inquiry Classification Specialist | None | low | ClassifierOutput |
| knowledge_retriever | ✅ | Knowledge Base Research Specialist | kb_search | low | RetrieverOutput |
| response_specialist | ✅ | Customer Response Composer | None | **mid** | ResponseOutput |
| escalation_manager | ✅ | Sentiment, Risk & Escalation Coordinator | ticket_stub | low | EscalationOutput |

### Demo Path Coverage

| Path | Query | Expected Decision | Implementation Status |
|------|-------|------------------|----------------------|
| A | "How do I reset my B-Mobile My Account PIN?" | resolve + sources | ✅ KB row `01-account-pin` |
| B | "What is your quantum warranty for the hardware drone?" | escalate (gap) | ✅ No matching KB row → gap=true |
| C | request_human=true + message | escalate (request_human) | ✅ Triage rule #1 |

---

## 10. Acceptance Criteria

### Backend Epic Exit Criteria (from PRD §10.3)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| **agents.yaml + tasks.yaml** with 4 agents/tasks | ✅ Complete | `backend/config/agents.yaml`, `backend/config/tasks.yaml` + `backend/crew.py` YAML loader |
| **Named output_pydantic models** (9 total) | ✅ Complete | `backend/models.py` |
| **crew.py sequential process**, memory=False, max_iter≤12 | ✅ Complete | `backend/crew.py` CustomerSupportCrew.kickoff |
| **kb_search tool** SQLite FTS5 (ADR-20), floor 0.35 | ✅ Complete | `backend/tools.py` KBSearchTool |
| **ticket_stub tool** (no-op/in-memory) | ✅ Complete | `backend/tools.py` TicketStubTool |
| **POST /api/chat** + **POST /api/chat/stream** (SSE) | ✅ Complete | `backend/main.py`, `backend/streaming.py` |
| **GET /health** → {status: ok} | ✅ Complete | `backend/main.py` health_check |
| **CHAT_TIMEOUT_SECONDS** (180s) + HITL wait + error envelope | ✅ Complete | `backend/chat_service.py`, `backend/streaming.py` |
| **Prompt Trace** to LOG_DIR (min schema §2) | ✅ Complete | `backend/main.py` _write_prompt_trace |
| **CORS** for localhost:3000 and 127.0.0.1:3000 | ✅ Complete | CORSMiddleware in main.py |
| **Seed KB** ≥10 FAQ rows (B-Mobile, demo A/B/C) | ✅ Complete | `backend/kb/articles.csv` (12 rows) |
| **Offline kickoff** smoke test (curl) | ✅ Ready | Manual testing section §6 |
| **Sprint 1 vertical slice**: resolve/escalate JSON for paths A/B/C | ✅ Ready | Curl tests documented |
| **backend.md** documentation | ✅ Complete | This document |

### Acceptance Tests (QA Epic)

**Unit** (QA to implement):
- Classification JSON shape matches ClassifierOutput
- Retrieval gap detection when all scores < 0.35
- `request_human=true` → reason_codes includes "request_human"
- Escalation rules (5 conditions) → correct decision + reason_codes
- Packet fields populated on escalate, null on resolve
- Stub ticket ID format STUB-{8 hex}

**Integration** (Integration Epic):
- FE → POST /api/chat → valid ChatResponse
- Health endpoint returns 200 + {status: ok}
- Error path (backend down) → FE shows safe message + Talk-to-human CTA
- CORS allows both localhost:3000 and 127.0.0.1:3000

**Smoke** (QA + Integration):
- Path A → decision=resolve, sources_used non-empty, packet=null
- Path G (greeting) → decision=resolve, no packet, no specialist banner
- Path B′ (out of scope) → decision=resolve, scope boundary reply, no human-agent pitch
- Path B (in-scope KB gap, low urgency) → decision=resolve when guardrails apply; escalate only with negative sentiment / request_human
- Path C → decision=escalate, reason_codes includes request_human, 4 steps in response

---

## Sources

- `project-context/1.define/prd.md` (primary requirements)
- `project-context/1.define/sad.md` (architecture contracts, ADRs 1–19)
- `.cursor/rules/adapter-crewai.mdc` (CrewAI adapter rules)
- `.cursor/rules/aamad-core.mdc` (AAMAD principles)
- `.cursor/agents/backend-eng.md` (persona contract)
- `backend/kb/articles.csv` (seed knowledge base)
- CrewAI documentation (agents, tasks, tools)
- FastAPI documentation (endpoints, CORS, Pydantic)

---

## Assumptions

1. **LLM Provider**: Either `OPENAI_API_KEY` (OpenAI) or `OLLAMA_API_KEY` (Ollama Cloud) available in .env with valid credentials
   - OpenAI: Uses `gpt-4o-mini` or specified tier models
   - Ollama: Uses Ollama Cloud at `https://ollama.com/v1` with `gemma4:31b` or specified model via LiteLLM OpenAI-compatible route
2. Seed KB `backend/kb/articles.csv` committed in repo with 12 B-Mobile FAQ rows
3. Live retrieval is SQLite FTS5 (ADR-20); CSV remains the hand-authored seed. Embedding / managed vector SaaS still deferred.
4. Primary UI transport is SSE progress (not LLM tokens). Legacy JSON `POST /api/chat` remains for scripts.
5. Single backend process acceptable for ≥5 concurrent demo sessions (best-effort)
6. Operator HITL detail on **`/operator`**; customer `/` has no specialist strip (SAD ADR-14 updated)
7. Gap/refuse → escalate per SAD ADR-16 **unless** MVP guardrails apply (greeting, low-urgency calm, out-of-scope) — see § Guardrails
8. Sentiment gates per SAD ADR-17 (not negative-alone escalation; protects Path A)
9. Crew wall-clock timeout is `CHAT_TIMEOUT_SECONDS` (default 180); original SAD ADR-18 45s is superseded for this Ollama-backed demo
10. Model tiers (low/mid) configured via env; no per-agent model env vars (SAD ADR-19)
11. No live ticketing or MCP. Local SQLite demo store is in scope (ADR-20/21); conversation-history DB remains Future Work
12. `meta.ai_disclosure=true` always; `disclosure_acknowledged` echoed when provided (AC-01b)
13. Prompt traces redact secrets/PII; message truncated to 200 chars in trace
14. Python 3.10+ runtime; dependencies compatible per requirements.txt
15. Integration Epic removes FE mock `GET /api/kb` and wires to `POST /api/chat` only

---

## Open Questions

1. GDPR / Prompt Trace retention duration (days) for course machines — **pending operator decision**
2. Security assessment graded/required for this course (recommended before Deliver) — **pending instructor clarification**
3. Public hosting target for Week 6 (local-only vs single cloud VM) — **pending Deliver decision**
4. Disclosure copy owner (working default: "You are chatting with the B-Mobile AI assistant") — **pending legal/instructor copy**
5. Monorepo naming if not `frontend/` + `backend/` (PRD OQ #4) — **assumed OK unless instructor overrides**
6. `setup.md` existence (PRD §10.2 suggests `@project.mgr` creates it) — **not found; backend proceeded with `.env.example` only**
7. Optimal `MAX_RPM` for course demo load (default 10) — **tunable via env; monitor LLM rate limits**

---

## Audit

| Field | Value |
|-------|-------|
| **Timestamp** | 2026-08-25T23:10:00-05:00 (YAML externalization complete) |
| **Persona id** | backend-eng |
| **Action** | develop-be, define-agents, implement-endpoint, document-backend, update-llm-config, externalize-yaml |
| **Resolved `AAMAD_TARGET_RUNTIME`** | crewai (PRD-locked; env unset → adapter default) |
| **LLM Providers** | OpenAI (default) + Ollama Cloud (via LiteLLM OpenAI-compatible route) |
| **Model tiers** | OpenAI: low=gpt-4o-mini, mid=gpt-4o-mini; Ollama: gemma4:31b (all tiers) |
| **KB algorithm** | SQLite FTS5 (ADR-20); CSV seed; ADR-13 TF-IDF historical |
| **Seed KB** | 12 B-Mobile FAQ rows in `backend/kb/articles.csv` (covers Path A/B demo queries) |
| **YAML Configs** | `backend/config/agents.yaml` (4 agents), `backend/config/tasks.yaml` (4 tasks) per CrewAI adapter rules |
| **Temperature** | low=0.2, mid=0.4 (determinism for classifiers; quality for customer prose) |
| **Max iterations** | 12 (per crew agent; adapter baseline) |
| **Max RPM** | 10 (crew-level rate limit) |
| **Timeout** | Crew 180s (`CHAT_TIMEOUT_SECONDS`); HITL 300s; FE abort ~500s |
| **CORS** | localhost:3000 and 127.0.0.1:3000 (both — browser origin distinction) |
| **Prompt Trace** | `{LOG_DIR}/{trace_id}.json`, min schema per SAD §2, redacts PII/secrets |
| **Concurrency** | Single process; `last_result` in-memory (racy under concurrent requests; acceptable for demo) |
| **Dependencies** | crewai 0.80+, fastapi 0.104+, scikit-learn 1.3+, openai 1.0+, pyyaml 6.0+ |
| **Files created** | backend/models.py, backend/tools.py, backend/crew.py, backend/llm_config.py, backend/main.py, backend/requirements.txt, backend/__init__.py, backend/config/agents.yaml, backend/config/tasks.yaml, backend/validate_yaml_config.py, .env.example |
| **Prohibited scope** | Live Zendesk/CRM, analytics, SSO, MCP; conversation-history DB (local SQLite demo store is in scope) |
| **Exit criteria** | Backend epic acceptance criteria (§10) met; Sprint 1 vertical slice ready; YAML externalization complete per SAD §2 |
| **Next epic** | Integration (`@integration.eng` → wire FE to `POST /api/chat` + verify Path A/B/C) |
| **Prompt Trace** | Omitted — deterministic file writes; no secrets in backend implementation |

---

## Appendix: File Summary

| File | Purpose | Lines |
|------|---------|-------|
| `backend/models.py` | Pydantic schemas (9 models) | ~220 |
| `backend/tools.py` | kb_search (SQLite FTS5) + ticket_stub | ~180 |
| `backend/crew.py` | CustomerSupportCrew orchestrator (YAML loader) | ~200 |
| `backend/llm_config.py` | LLM provider resolution | ~140 |
| `backend/main.py` | FastAPI endpoints + mapper + error handling | ~420 |
| `backend/config/agents.yaml` | 4 agent definitions per CrewAI adapter | ~50 |
| `backend/config/tasks.yaml` | 4 task definitions with context | ~120 |
| `backend/requirements.txt` | Python dependencies | ~25 |
| `backend/__init__.py` | Package marker | ~4 |
| `.env.example` | Environment template | ~60 |
| `backend/kb/articles.csv` | Seed knowledge base (12 B-Mobile FAQs) | ~13 |

**Total implementation**: ~1,432 lines of Python + YAML + config

---

## Appendix: Quick Start Commands

```bash
# 1. Setup
cp .env.example .env
# Edit .env and set OPENAI_API_KEY (OpenAI) or OLLAMA_API_KEY (Ollama Cloud)
pip install -r backend/requirements.txt

# 2. Verify KB
cat backend/kb/articles.csv
# Should show 12 B-Mobile FAQ rows

# 3. Start server (from repo root)
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
# Server on http://127.0.0.1:8001

# 4. Test health
curl http://127.0.0.1:8001/health

# 5. Test Path A (resolve)
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I reset my B-Mobile My Account PIN?", "request_human": false}'

# 6. Test Path B (escalate - gap)
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is your quantum warranty for the hardware drone?", "request_human": false}'

# 7. Test Path C (escalate - request_human)
curl -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to talk to a human!", "request_human": true}'

# 8. Check prompt traces
ls -l project-context/2.build/logs/
```

---

## Audit

| Timestamp | Persona | Action | Notes |
|-----------|---------|--------|-------|
| 2026-08-23T19:30:00Z | @backend.eng | develop-be | Initial backend implementation complete; all 9 models, 4 agents, 2 tools, FastAPI endpoints, seed KB with OpenAI support |
| 2026-08-23T20:30:00Z | @backend.eng | update-llm-config | Added Ollama Cloud provider support via `LLM_PROVIDER` env var; implemented LiteLLM OpenAI-compatible route; added `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` configuration; updated documentation sections |
| 2026-08-25T23:05:00Z | @backend.eng | externalize-yaml | Extracted agent and task definitions to `backend/config/agents.yaml` and `backend/config/tasks.yaml` per CrewAI adapter rules; updated crew.py to load from YAML with dynamic value injection; added pyyaml dependency; fully compliant with SAD §2 YAML externalization requirement |
| 2026-08-28T23:45:00-05:00 | @backend.eng | sync-docs | Documented SQLite FTS5 (ADR-20), Telegram HITL (ADR-21), SSE HITL events, approval APIs, 180s crew / 300s HITL timeouts, port 8001 demo |
| 2026-08-29T11:20:00-05:00 | @backend.eng | sync-docs | Traceability + audit appendix: FTS5 live, 180s/300s/~500s; no customer specialist strip; superseded 45s/TF-IDF rows |
| 2026-09-10T21:45:00-05:00 | @backend.eng | fix-failure-paths | Path B: strip ungrounded citations via live FTS on the customer message. Path C: replace hallucinated ticket ids with `STUB-` + 8 hex; force escalate + packet when `request_human=true`. |

---

**Backend Implementation Status: COMPLETE**  
**LLM Providers**: OpenAI (default) + Ollama Cloud  
**Sprint 1 Vertical Slice: READY FOR INTEGRATION**  
**Next Step**: Integration Epic — wire FE to `POST /api/chat` + verify demo paths A/B/C
