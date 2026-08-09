# Product Requirements Document (PRD): Multi-Agent Customer Support Crew

**Deep Research Report / MRD**: `project-context/1.define/mrd.md`  
**System Description**: N/A (elicitation skipped; stakeholder concept + MRD used)  
**System Concept**: Multi-Agent Customer Support Crew — specialized AI agents collaborate to classify inquiries, retrieve knowledge, analyze sentiment, manage escalations, and deliver personalized 24/7 support.  
**Selected Runtime**: `crewai` (**locked** for course MVP)  
**MVP user value (one sentence)**: A customer gets a grounded chat answer or a clean human escalation with full context — without waiting in a blind queue or talking to a black-box FAQ bot.

---

## Define Stage Success Gate

| Success indicator | Evidence in artifacts | Status |
|-------------------|----------------------|--------|
| **Clarity** — any teammate understands *what* and *why* | MRD Exec Summary + PRD §§1–2 (problem, solution, personas, journey); context-summary one-liner | **Met** |
| **Completeness** — enough detail to start architecture | PRD §§3–6, §10.1 (agents, API shape, stack, NFRs, ADRs for SAD) | **Met** |
| **Alignment** — MRD opportunity supports PRD decisions | See **MRD→PRD alignment** below | **Met** |
| **Scope management** — core MVP user value only | 4 agents; chat + local KB + stub ticket; P1/P2 deferred; AC-01…06 | **Met** |

**Define stage verdict: COMPLETE** — hand off to `@system.arch` (`*create-sad --mvp`) if `sad.md` is not finished.

### MRD → PRD alignment

| MRD finding | PRD decision |
|-------------|--------------|
| Shift from FAQ bots → agentic multi-step resolution | Sequential 4-agent crew (classify → retrieve → reply → triage) |
| Hybrid AI+human FCR / CSAT risk on bad escalations | Escalation packet + “talk to human” (`AC-04`); no forced bot loops |
| Outcome/measurable resolution over seat bots | KPIs: containment, grounded rate, escalate reasons; Prompt Trace |
| Mid-market wants layer beside ticketing, not rip-replace | No live Zendesk in MVP; ticket **stub**; focus on chat orchestration |
| Art. 50 AI disclosure / avoid biometric emotion risk | Disclosure P0 (`AC-01`); text-only sentiment inside escalation agent |
| 6-week / course complexity | Local KB, no DB, non-streaming JSON, ≤4 agents |

---

## 1. Executive Summary

### Problem Statement

Traditional helpdesks rely on overloaded human queues and brittle single-bot scripts that fail on multi-step, emotional, or knowledge-sparse inquiries. Industry evidence (see MRD) shows pure automation FCR is strong on transactional queries (≈60–70%) but weak on complex ones (≈28–40%), while failed bot-then-escalate paths can cut CSAT by ~22%. Mid-market and SaaS support teams need round-the-clock coverage without sacrificing escalation quality or compliance transparency (EU AI Act Art. 50 disclosure from 2026-08-02).

**Impact (research-backed ranges)**: Contained tickets can save ~USD 5.50–11.50 vs human-handled; AI programs commonly cite 25–40% cost reduction per interaction and positive ROI within ~18 months for many adopters — course demo uses qualitative script; production baselines optional.

**Target users**: End-customers (chat), support agents (escalation packet), support managers (auditability). Admin/ops tooling beyond seed KB is out of MVP.

### Solution Overview

A **Multi-Agent Customer Support Crew** runs four specialized roles — classification, knowledge retrieval, response composition, and sentiment/risk escalation — in one auditable chat resolution path.

**Differentiators vs alternatives**
- Explicit multi-agent handoffs with Prompt Trace (not a monolithic black-box bot)
- Retrieval-grounded answers with citation/refusal behavior
- Sentiment-aware escalation with context packages for humans
- Course MVP on `crewai` (YAML agents/tasks)

**Expected outcomes (MVP / course demo)**
- Demo path A: in-KB FAQ → **resolve** with sources shown  
- Demo path B: unknown topic → **refuse/escalate** (no fabrication)  
- Demo path C: request human / high risk → **escalate** with packet  
- Automated path targets (stretch): p95 < 30s; median first status < 10s  

### Strategic Rationale

Multi-agent architecture matches support work (route → research → reply → triage). MRD shows market timing for agentic CX over FAQ chatbots. MVP value is **faster, grounded tier-1 answers plus trustworthy handoff** — not full agent replacement or suite displacement.

---

## 2. Market Context & User Analysis

### Target Market / Users

| Persona | Characteristics | Needs |
|---------|-----------------|-------|
| End-customer | Seeks fast, accurate, 24/7 answers; wants human when stuck or upset | Clear answers, disclosure that AI is used, easy escalate |
| Support agent | Handles escalations and complex cases | Rich context packet, suggested draft, priority/sentiment |
| Support manager | Owns CSAT, cost/ticket, SLA | Dashboards/metrics, policy controls, auditability |
| Admin / ops | Maintains KB, prompts, integrations | Versioned config, safe secrets, eval harness |

**Market segment**: AI customer service / agentic support — TAM cited in MRD as ~USD 13–19B near-term depending on definition; orchestration niche smaller but faster-growing. Geographic focus MVP: English-first; regions TBD (Open Question).

### User Needs Analysis

**Pain points**: Long waits; inconsistent answers; bots that loop; lost context on escalate; lack of AI transparency; expensive tier-1 labor.

**Journey (MVP)**  
1. Customer opens chat → AI disclosure shown  
2. Classifier labels intent + urgency  
3. Retriever grounds on local KB  
4. Response Specialist drafts personalized reply **or refuses** if ungrounded  
5. Escalation Manager scores text sentiment/risk → **resolve** or **escalate** with packet  
6. Operator strip shows decision + reason codes *(CSAT prompt = P1 stub only)*

**Adoption factors**: Grounded accuracy, fast escalate, manager-visible metrics. Barriers: distrust on billing/disputes, compliance fear, integration effort.

### Competitive Landscape

Incumbents: Zendesk AI, Intercom Fin, Salesforce Agentforce, Freshdesk Freddy. AI-natives: Sierra, Decagon, Ada, Kore.ai. MVP does **not** aim to replace suites; it delivers a transparent multi-agent crew for AAMAD-built MVPs and integrable orchestration demos. Gap: auditable specialized-agent pipeline with explicit escalation rationale in an open, adapter-based project template.

---

## 3. Technical Requirements & Architecture

### Runtime & Agent Specifications

- **Runtime**: `crewai` (default). Agents/tasks in YAML; sequential process; `allow_delegation=false` unless SAD justifies otherwise.
- **Collaboration**: Sequential task chain with `Task.context` dependencies.
- **Controls**: `max_iter ≤ 12`, `max_retry_limit ≥ 2`, crew-level `max_rpm`, per-task `max_execution_time`; `memory=False` by default for reproducibility.
- **Logging**: Prompt Trace + lifecycle logs under `project-context/2.build/logs` (Build phase); redact PII/secrets.

### Core Agent Definitions (MVP = **4 agents**, SAD-aligned)

Course/SAD complexity guidance caps MVP at **3–4 specialized agents**. Sentiment is **merged into** `escalation_manager` (text-only risk scoring + handoff). Do not add a fifth live agent in MVP.

**agent: query_classifier**  
- role: "Inquiry Classification Specialist"  
- goal: "Classify customer intent, entities, and urgency for routing"  
- tools: []  
- runtime notes: low temperature; structured JSON: `{intent, urgency, entities, confidence}`

**agent: knowledge_retriever**  
- role: "Knowledge Base Research Specialist"  
- goal: "Retrieve grounded passages with citations for the classified intent"  
- tools: [`kb_search`]  
- runtime notes: local/seed KB only in MVP (no external SaaS); return `{passages[], citations[], gap: bool}` if below similarity threshold

**agent: response_specialist**  
- role: "Customer Response Composer"  
- goal: "Draft clear, personalized, policy-aligned replies using only grounded evidence"  
- tools: []  
- runtime notes: refuse when `gap=true` or no passages; never invent policy/pricing; output `{reply, sources_used[], refused: bool}`

**agent: escalation_manager**  
- role: "Sentiment, Risk & Escalation Coordinator"  
- goal: "Score text sentiment/risk and decide resolve vs escalate; package context for humans"  
- tools: [`ticket_stub`] (in-memory / no-op create OK)  
- runtime notes: **no biometric emotion recognition**; deterministic rules on confidence, sentiment, customer_request_human, gap/refusal; output `{decision: resolve|escalate, sentiment, risk, reason_codes[], packet}`

**Task chain (sequential, `Task.context`):**  
`classify_inquiry` → `retrieve_knowledge` → `compose_response` → `triage_and_escalate`

### Integration Requirements

| Integration | MVP (course) | Deferred |
|-------------|--------------|----------|
| Chat UI ↔ Backend API | Required (Integration epic) | — |
| Seed / local knowledge corpus | Required (files under repo; simple retriever) | Managed vector SaaS |
| Ticketing (Zendesk/etc.) | **Stub only** — no live third-party | Live connector (P1) |
| CRM write actions | Out | P1+ |
| Auth | Demo-safe: open chat; optional `OPERATOR_API_KEY` for operator panel | SSO/IAM |
| LLM provider | Via env (`OPENAI_API_KEY` or provider used by CrewAI) | Multi-provider router |
| Database | **None** (backend persona forbids persistence) | Optional store later |

**Performance targets (MVP)**: p95 automated response path < 30s end-to-end excluding human; support ≥ 5 concurrent demo sessions (course demo scale; 10 aspirational).

### Infrastructure Specifications

- Hosting: local dev + optional single compose service (Deliver week)
- Secrets: `.env.example` names only; never commit values
- Monitoring: `GET /health`; structured logs; Prompt Trace file/dir under `project-context/2.build/logs`
- Security assessment before Deliver when config requires it
- **Stack defaults for course MVP** (SAD may confirm, not reinvent):
  - Frontend: **Next.js** (App Router) + **Tailwind** + TypeScript
  - Backend: **Python** + **CrewAI** + lightweight HTTP API (FastAPI or equivalent per SAD)
  - Transport: **non-streaming JSON** request/response for MVP (streaming = Future Work stub in UI)

---

## 4. Functional Requirements

### Core Features (Priority P0) — with acceptance IDs for QA

1. **AI-disclosed chat intake** (`AC-01`)  
   - User story: As a customer, I see that I am interacting with AI before I chat, so I can make an informed choice.  
   - Acceptance: Disclosure visible on first paint; copy states the assistant is AI; control exists to request human (`AC-01a`); disclosure event logged or returned in API metadata (`AC-01b`).

2. **Multi-agent resolution pipeline** (`AC-02`)  
   - User story: As a support manager, I want specialized agents to classify, retrieve, draft, and triage so resolutions are consistent and auditable.  
   - Acceptance: Each run executes the 4-agent sequential chain (`AC-02a`); response includes ordered step summaries (`AC-02b`); Prompt Trace written for the run (`AC-02c`).

3. **Grounded answers with refusal** (`AC-03`)  
   - User story: As a customer, I receive answers tied to knowledge sources or a clear “I don’t know / escalate” path.  
   - Acceptance: Resolve path includes `sources_used` when answering (`AC-03a`); if retrieval gap, system refuses or escalates — never fabricates policy (`AC-03b`).

4. **Sentiment-aware escalation** (`AC-04`)  
   - User story: As a support agent, I receive escalations with sentiment/risk and full context when confidence is low or customer is distressed.  
   - Acceptance: Escalation packet includes intent, citations attempted, draft reply, sentiment, reason_codes (`AC-04a`); customer “talk to human” forces escalate (`AC-04b`).

5. **Operator visibility (minimal)** (`AC-05`)  
   - User story: As an operator, I can view conversation status (resolved/escalated) and agent rationale.  
   - Acceptance: UI panel or `/api/last-result` style read shows `decision`, `reason_codes`, and step summaries (`AC-05a`).

6. **Health & failure path** (`AC-06`)  
   - Acceptance: `GET /health` returns ok when API up (`AC-06a`); LLM/KB failure returns structured error and safe user message with escalate CTA (`AC-06b`).

### Enhanced Features (Priority P1) — out of 6-week course MVP unless time remains

- Live ticketing connector (create/update ticket)
- CSAT survey + analytics dashboard
- Multilingual classification/response
- Clarifying-question multi-turn state machine
- Streaming token UI

### Future Features (Priority P2) — Future Work

- Voice channel / CCaaS integration
- Autonomous CRM mutations (refunds, plan changes) with policy engine
- Online continuous learning / auto fine-tuning on production chats
- Biometric or camera-based emotion detection (**out of policy** unless legal review clears)
- Sales+support dual orchestration
- Outcome-based billing metering
- Persistent database / conversation history store
- SSO / enterprise IAM

---

## 5. Non-Functional Requirements

### Performance
- Automated path p95 < 30s; first token/status < 10s where streaming exists
- Graceful timeout with escalate-on-timeout

### Security & Compliance
- No secrets in artifacts or traces
- PII minimization and redaction in logs
- GDPR-aware retention settings (duration TBD)
- EU AI Act Art. 50-style disclosure for customer-facing AI
- Text-only sentiment; no prohibited emotion-monitoring patterns

### Scalability & Reliability
- MVP: vertical scale single instance; document horizontal scale as Future Work
- On LLM/KB failure: fail open to human queue with Diagnostic reason
- Idempotent ticket side-effects when connectors exist

---

## 6. User Experience Design

### Interface Requirements (Frontend epic contract)

| Screen / region | MVP behavior | Placeholder (visible, non-functional) |
|-----------------|--------------|----------------------------------------|
| Chat page `/` | Message list, composer, send | — |
| AI disclosure banner | Always visible until acknowledged or persistent notice | — |
| Status line | Shows pipeline stage labels during wait | Streaming tokens |
| Result card | Final reply + sources or escalate notice | — |
| Operator strip | Decision, reason_codes, expand step summaries | Full history / metrics dashboard |
| “Talk to a human” | Sets flag / calls API with `request_human=true` | Live agent chat |
| Voice / email tabs | — | Visible Future Work stubs |

- Framework: Next.js App Router + Tailwind + TS (per FE persona defaults)
- Responsive: usable at 375px and 1280px widths
- Accessibility: keyboard send (Enter), focusable controls, contrast adequate for demo
- FE epic **must not** call real backend until Integration epic (use mock data or disabled send documented in `frontend.md`)

### Agent Interaction Design
- Transparent status: “Classifying… Retrieving… Composing… Triaging…”
- Errors: human-readable + escalate CTA
- Explainability: short rationale + sources for operators; customers see source titles when resolving

---

## 7. Success Metrics & KPIs

### Business / Operational
- Cost per resolved chat (auto vs human)
- Containment rate on in-scope intents
- Escalation rate and reason mix
- SLA adherence for escalated queue

### Technical
- Retrieval hit rate; grounded answer rate
- Agent task success/fail; retry count; token cost per ticket
- p95 latency; error rate

### UX
- CSAT / CES; % customer-requested human; escape rate after disclosure

---

## 8. Implementation Strategy

### Course timeline & complexity validation

| Expectation (AAMAD course / framework) | This PRD alignment | Verdict |
|----------------------------------------|--------------------|---------|
| ~6-week Define→Build→Deliver window | 2026-08-01 → 2026-09-12; Week 2 current | Pass |
| Six Build epics: Architecture, Setup, Frontend, Backend, Integration, QA | Explicit mapping in schedule + §10 epic contracts | Pass |
| Lean MVP; SAD ≤3–4 agents | **4 agents** (sentiment merged into escalation) | Pass |
| Chat UI MVP; FE does not wire BE | Next.js chat + placeholders; Integration owns wire-up | Pass |
| Backend: runtime agents + chat API; **no DB / no external integrations** | Local KB + ticket stub; no Zendesk/CRM live | Pass |
| Integration: FE↔BE chat only | Single resolve endpoint, non-streaming JSON | Pass |
| QA: unit + integration + AC mapping | `AC-01`…`AC-06` defined | Pass |
| Complexity fit for 6 weeks | Single chat flow, sequential crew, seed KB, stub ticket | Pass — avoid P1 creep |

**Complexity watch-outs (do not pull into MVP):** live ticketing, streaming, multi-turn clarification engine, analytics dashboard, auth/SSO, vector DB cloud, fifth agent.

### Delivery window (fixed)

- **Duration:** 6 weeks  
- **Start:** 2026-08-01 (started one week before 2026-08-08)  
- **MVP complete:** 2026-09-12  
- **Current position (2026-08-08):** Week 2 — Backend (crew core)  
- **Rule:** Protect the end date by cutting P1/Future Work before slipping schedule.

### 6-Week schedule (mapped to six Build epics + Deliver)

| Week | Dates (2026) | Build epic(s) | Persona | Deliverables | Status |
|------|--------------|---------------|---------|--------------|--------|
| 1 | Aug 1–7 | **Architecture** + **Setup** | `@system.arch`, `@project.mgr` | `sad.md`, scaffold, `.env.example`, `setup.md` | Assumed started/complete |
| 2 | Aug 8–14 | **Backend** (Module 1 — crew) | `@backend.eng` | `agents.yaml`, `tasks.yaml`, offline `kickoff()` | **Current** |
| 3 | Aug 15–21 | **Backend** (API) + **Frontend** start | `@backend.eng`, `@frontend.eng` | `POST /api/chat` (or SAD name), Next.js chat shell | Upcoming |
| 4 | Aug 22–28 | **Frontend** finish + **Integration** | `@frontend.eng`, `@integration.eng` | Disclosure UI, operator strip, FE↔BE wired | Upcoming |
| 5 | Aug 29–Sep 4 | **QA** (+ security recommended) | `@qa.eng`, `@security.eng` | `qa.md` vs `AC-*`; `security.md` | Upcoming |
| 6 | Sep 5–12 | Deliver (post-Build) | `@devops.eng` | `deploy.md`, `user-guide.md`, demo | Upcoming |

### Development Phases (mapped to weeks)
1. **Define / Architecture / Setup** (Week 1): MRD ✓, PRD ✓ → SAD/SFS + stories + scaffold  
2. **Build** (Weeks 2–5): Backend → Frontend → Integration → QA  
3. **Deliver** (Week 6): deploy + user guide  

### Resource Requirements
- Cross-functional AAMAD persona sequence; Friday checkpoints Weeks 2–6.
- Seed FAQ/KB (≥10 articles) committed in-repo by end of Week 2.

### Risk Mitigation
| Risk | Mitigation |
|------|------------|
| Hallucinations | RAG threshold + refusal + eval set |
| Cost overrun | max_rpm, max_iter, caching retrieval |
| CSAT on escalate | Context-rich handoff; early human exit |
| Compliance | Disclosure P0; security assessment; redact traces |
| 6-week slip | No live ticketing; no streaming; no 5th agent; hard stop 2026-09-12 |
| Course over-scope | Enforce §10 epic boundaries and prohibited actions |

---

## 9. Launch & Go-to-Market Strategy

Optional product GTM (not required for course demo):  
- Pilot with seed KB product FAQs  
- Show resolve vs escalate with packet in demo script  
- Position as multi-agent crew teaching/demo system  
- Pricing N/A for course deliverable

---

## 10. Build Epic Requirements (handoff contracts)

Sufficient detail for each of the six Build-stage epics. Personas must not invent product scope beyond this section + §§3–6.

### 10.1 Solution Architecture (`@system.arch` → `sad.md`)

**Must decide / document**
- Logical view: FE chat app ↔ API gateway ↔ CrewAI runtime ↔ `kb_search` tool ↔ ticket stub  
- Process view: sequential task graph with context chaining; failure → structured error  
- Deployment view: local monorepo or `frontend/` + `backend/` layout; optional compose later  
- ADRs: 4-agent merge; non-streaming JSON; no DB; crewai YAML-first  
- Explicit Future Work list matching PRD P1/P2  

**Inputs from PRD:** agent roster, task chain, stack defaults, NFR targets, exclusions  
**Out of epic:** application code

### 10.2 Setup (`@project.mgr` → `setup.md`)

**Must create (no business logic)**
- Folders: e.g. `backend/`, `frontend/`, `backend/config/`, `backend/kb/` (seed FAQs), `project-context/2.build/`  
- Dependency manifests only (Python + Node) per SAD  
- `.env.example` entries (names only):

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` (or provider key CrewAI uses) | LLM access |
| `AAMAD_TARGET_RUNTIME` | `crewai` |
| `BACKEND_PORT` | API listen port (e.g. 8000) |
| `NEXT_PUBLIC_API_BASE_URL` | FE→API base (Integration uses) |
| `OPERATOR_API_KEY` | Optional operator panel gate |
| `LOG_DIR` | Default `project-context/2.build/logs` |

**Exit:** `setup.md` lists next steps for FE/BE/Integration; `crew.kickoff` not implemented here

### 10.3 Backend (`@backend.eng` → `backend.md`)

**Must implement**
- `config/agents.yaml` + `config/tasks.yaml` for the 4 agents / 4 tasks  
- `crew.py` (or equiv.) sequential process; `memory=False`; `max_iter≤12`  
- Tool `kb_search` over local seed KB; tool `ticket_stub` no-op/in-memory  
- HTTP API:

**`POST /api/chat`** (name may match SAD; keep path stable once set)

Request:
```json
{
  "message": "string",
  "request_human": false,
  "session_id": "optional-string"
}
```

Response (non-streaming):
```json
{
  "decision": "resolve|escalate",
  "reply": "string",
  "sources_used": [{"title": "string", "snippet": "string"}],
  "sentiment": "string|number",
  "reason_codes": ["string"],
  "steps": [{"agent": "string", "summary": "string"}],
  "trace_id": "string",
  "error": null
}
```

- `GET /health` → `{ "status": "ok" }`  
- Prompt Trace persisted under `LOG_DIR` / `project-context/2.build/logs` (redact secrets)  
- **Prohibited:** database, Zendesk/CRM live APIs, analytics products, non-MVP agents  

**Exit:** documented in `backend.md`; offline kickoff + API smokeable with curl

### 10.4 Frontend (`@frontend.eng` → `frontend.md`)

**Must implement (UI only — no live BE wiring)**
- Next.js chat page with disclosure banner (`AC-01`)  
- Composer, message list, loading stage labels, result/escalate card  
- Operator strip UI bound to **mock** JSON shaped like §10.3 response  
- Visible stubs: Voice tab, CSAT dashboard, “Live ticketing” badge (non-functional)  
- Tailwind responsive layout  

**Prohibited:** calling real backend; implementing auth/SSO  

**Exit:** `frontend.md` notes mock vs future Integration hook points

### 10.5 Integration (`@integration.eng` → `integration.md`)

**Must implement**
- Wire FE send → `POST /api/chat` using `NEXT_PUBLIC_API_BASE_URL`  
- Map response fields into chat + operator strip  
- Error envelope → user-visible message + escalate CTA (`AC-06b`)  
- Verify happy path resolve + escalate (`request_human=true` and low-confidence path)  

**Prohibited:** third-party SaaS integrations  

**Exit:** `integration.md` with verified message-flow notes

### 10.6 QA (`@qa.eng` → `qa.md`)

**Must validate (map tests to AC IDs)**

| Stage | Coverage |
|-------|----------|
| Unit | Classifier JSON shape; retrieval gap→refusal; escalation rules for `request_human` |
| Integration | FE↔API↔crew round-trip; health; error path |
| Smoke / acceptance | `AC-01`…`AC-06` checklist |

**Demo script (minimum):** (1) FAQ hit → resolve + sources (2) unknown topic → escalate/refuse (3) angry + request human → escalate packet  

**Prohibited:** load/perf campaigns beyond p95 smoke unless time remains; testing non-existent P1 features as failures  

**Exit:** `qa.md` with pass/fail per AC; known gaps explicit; recommend `@security.eng` before Deliver

---

## Quality Assurance Checklist

- [x] Requirements traceable to MRD and stakeholder concept  
- [x] Technical specifications feasible with `crewai` adapter  
- [x] Success metrics aligned with stated objectives  
- [x] MVP vs Future Work boundaries explicit  
- [x] Market sections populated (MRD not skipped)  
- [x] Scope validated against 6-week course timeline and lean complexity  
- [x] PRD details sufficient for six Build epics (Architecture, Setup, FE, BE, Integration, QA)  
- [x] Acceptance criteria IDs (`AC-*`) present for QA mapping  
- [x] Agent count ≤4 for MVP  
- [x] **Define Success — Clarity** (what/why readable from MRD/PRD)  
- [x] **Define Success — Completeness** (architecture-ready detail in §3–§10)  
- [x] **Define Success — Alignment** (MRD→PRD table)  
- [x] **Define Success — Scope** (core MVP user value only)

---

## Sources

- `project-context/1.define/mrd.md` (full citation list §Sources)
- Stakeholder concept: Multi-Agent Customer Support Crew (user, 2026-08-08)
- `.cursor/templates/prd-template.md`, `.cursor/templates/sad-template.md` (MVP ≤3–4 agents)
- AAMAD README Phase 2 Build epics; `.cursor/agents/*` persona contracts
- `aamad.config.example.yml` (runtime/security/testing preferences; no project `aamad.config.yml`)
- AAMAD adapter rules: `.cursor/rules/adapter-crewai.mdc`, `adapter-registry.mdc`
- Operator constraints: 6-week window; started 2026-08-01; course epic alignment request 2026-08-08

## Assumptions

- MRD completed prior; this PRD is the Build handoff source of truth.
- MVP channel is **web chat only**; email/voice deferred (UI stubs OK).
- “Learns and adapts” = analytics + human-approved KB/prompt updates post-MVP — **not** in 6-week build.
- **Ticketing is stub-only** for course MVP (no live third-party) — resolves prior Open Question for Build.
- **Runtime locked to `crewai`** for this course delivery unless operator overrides before Backend Week 2 ends.
- English-only seed KB; ≥10 FAQ docs in-repo.
- Sentiment is text-only inside `escalation_manager` (4-agent cap).
- **Non-streaming JSON** API for MVP; streaming UI is a visible stub only.
- **No database** in Backend epic.
- Clarifying multi-turn and CSAT dashboard are **P1 / not required** for Sep 12 demo.
- Operator strip is **in-app**, not a separate console product.
- Fixed calendar: 2026-08-01 → 2026-09-12; Week 2 current as of 2026-08-08.

## Open Questions

1. Exact LLM model string for CrewAI (e.g. `gpt-4o-mini` vs other) — SAD/Backend may pick cost-efficient default.  
2. Disclosure legal copy owner (use generic: “You are chatting with an AI assistant”) until provided.  
3. Confirm Week-1 `sad.md` / `setup.md` already exist on disk or must be produced ASAP in Week 2.  
4. Preferred monorepo layout names if instructor template differs (`apps/web` vs `frontend`).  
5. Whether `@security.eng` is graded/required for this course section or optional.  
6. Baseline CSAT metrics — N/A for course demo; use qualitative demo script instead.

## Audit

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-08T13:49:48-05:00 |
| Persona id | product-mgr |
| Action | create-context / define-stage success gate |
| Prior action | create-context / prd course-alignment @ 2026-08-08T13:47:11-05:00 |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai (locked for course MVP) |
| Prompt Trace | Omitted — requirements synthesis; no secrets |
| Change note | Added Define Success Gate + MRD→PRD alignment; clarified MVP user value and journey; marked Define COMPLETE |
