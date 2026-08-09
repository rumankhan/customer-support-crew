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
| Operator visibility | Decision, reason_codes, step summaries in UI (optional last-result API) | AC-05 |
| Health & failure path | Liveness probe; structured error + escalate CTA on LLM/KB failure | AC-06 |

**Demo paths:** (A) in-KB FAQ → resolve + sources; (B) unknown topic → refuse/escalate; (C) request human / high risk → escalate with packet.

### Main interfaces

| Interface | Direction | Contract |
|-----------|-----------|----------|
| Web chat UI (`/`) | Customer ↔ Frontend | Disclosure, composer, stage labels, result/escalate card, operator strip |
| `POST /api/chat` | Frontend ↔ Backend | Non-streaming JSON request/response (primary resolve path) |
| `GET /health` | Ops / CI ↔ Backend | `{ "status": "ok" }` |
| `GET /api/last-result` | Operator UI ↔ Backend (optional) | Last in-memory `ChatResponse` for demo strip |
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
| **Future (P1/P2)** | Live ticketing, streaming UI, multi-turn clarifier, CSAT dashboard, DB/history, SSO, voice, CRM writes, cloud vector DB, 5th agent |

**Explicit exclusions:** persistent database, Zendesk/Intercom live APIs, biometric emotion, horizontal autoscaling, MCP servers, hierarchical CrewAI process.

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

**UI requirements:** stages Classifying → Retrieving → Composing → Triaging (first stage < 10s); sources on resolve; escalate CTA on error; Talk-to-human always available; responsive 375px / 1280px.

### Backend API contracts

**Base:** FastAPI in `backend/main.py` (or `backend/app/main.py`). CORS for local Next (e.g. `http://localhost:3000`).

| Method | Path | Purpose | AC |
|--------|------|---------|-----|
| GET | `/health` | Liveness `{ "status": "ok" }` | AC-06a |
| POST | `/api/chat` | Run crew; return decision | AC-02…05, AC-01b |
| GET | `/api/last-result` | Optional last in-memory result | AC-05a |

**Request**

```json
{
  "message": "string",
  "request_human": false,
  "session_id": "optional-string",
  "disclosure_acknowledged": true
}
```

**Validation:** `message` required, non-empty, max **4000** chars; `request_human` default false; `disclosure_acknowledged` optional (AC-01b).

**Success response (non-streaming)**

```json
{
  "decision": "resolve|escalate",
  "reply": "string",
  "sources_used": [{"title": "string", "snippet": "string"}],
  "sentiment": "string|number",
  "reason_codes": ["string"],
  "steps": [{"agent": "string", "summary": "string"}],
  "trace_id": "string",
  "meta": {
    "ai_disclosure": true,
    "disclosure_acknowledged": true
  },
  "error": null
}
```

**AC-01b:** Always set `meta.ai_disclosure=true`; echo `disclosure_acknowledged` when provided; record both in Prompt Trace.

**Error envelope:** `decision=escalate`, safe user reply, `reason_codes` include `system_error` or `timeout`, `error.code` e.g. `llm_or_timeout`, plus escalate CTA in UI (AC-06b).

### Multi-agent coordination

**Pattern:** sequential pipeline; each task consumes prior output via CrewAI `Task.context`. No peer delegation (`allow_delegation=false`). `memory=False`.

```
classify_inquiry → retrieve_knowledge → compose_response → triage_and_escalate
```

| Agent id | Role | Goal | Tools |
|----------|------|------|-------|
| `query_classifier` | Inquiry Classification Specialist | Intent, entities, urgency | none |
| `knowledge_retriever` | Knowledge Base Research Specialist | Grounded passages + citations | `kb_search` |
| `response_specialist` | Customer Response Composer | Draft from evidence only or refuse | none |
| `escalation_manager` | Sentiment, Risk & Escalation Coordinator | Text sentiment/risk; resolve vs escalate; packet | `ticket_stub` |

**Structured outputs**

- Classifier → `{intent, urgency, entities, confidence}`
- Retriever → `{passages[], citations[], gap: bool}`
- Response → `{reply, sources_used[], refused: bool}`
- Escalation → `{decision, sentiment, risk, reason_codes[], packet}`

| Task id | Agent | Context from | Suggest `max_execution_time` |
|---------|-------|--------------|------------------------------|
| `classify_inquiry` | query_classifier | user message | 15s |
| `retrieve_knowledge` | knowledge_retriever | classify_inquiry | 15s |
| `compose_response` | response_specialist | classify + retrieve | 20s |
| `triage_and_escalate` | escalation_manager | all prior + `request_human` | 15s |

**Escalation packet (`AC-04a`)**

```json
{
  "intent": "string",
  "urgency": "string",
  "customer_message": "string",
  "request_human": false,
  "citations_attempted": [{"title": "string", "snippet": "string"}],
  "draft_reply": "string",
  "sentiment": "string|number",
  "risk": "low|medium|high",
  "reason_codes": ["string"],
  "stub_ticket_id": "STUB-…"
}
```

**Reason codes:** `request_human` | `retrieval_gap` | `refused` | `low_confidence` | `high_risk_sentiment` | `timeout` | `system_error`

**Escalation gates:** escalate if any of: `request_human=true`; `gap=true` or `refused=true`; confidence < `CLASSIFIER_CONFIDENCE_MIN` (default **0.55**); high/negative sentiment/risk; else resolve when grounded reply exists and `sources_used` non-empty.

**Retrieval gap:** Backend sets similarity/score floor (document in `backend.md`). No passage above floor → `gap=true`.

### Runtime integration (crewai)

1. FastAPI receives `ChatRequest` → validate → timeout guard.  
2. Build/cached crew from `backend/config/agents.yaml` + `tasks.yaml` + tool bindings.  
3. `crew.kickoff(inputs={"message": ..., "request_human": ...})` with `Process.sequential`.  
4. Map task outputs → `ChatResponse`; write Prompt Trace; update `last_result`.  
5. Return JSON.

**Controls:** `max_iter ≤ 12`; `max_retry_limit ≥ 2`; crew `max_rpm` suggest **10**; wall-clock API soft timeout **45s**. Suggest temperature **0.2** (classifier/retriever/escalation), **0.4** (response). Model from `OPENAI_MODEL` default `gpt-4o-mini`.

**Not used in MVP:** hierarchical process, `kickoff_for_each`, MCP, memory storage dir. *(claude-agent-sdk / cursor-sdk: N/A — runtime locked to crewai.)*

### Failure / degrade path

```
LLM/KB/tool failure OR wall-clock timeout
  → stop further agent work
  → Prompt Trace + Diagnostic reason
  → error envelope (decision=escalate)
  → FE safe message + “Talk to a human” (AC-06b)
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

**Local run:** Terminal A = uvicorn; Terminal B = Next.js. Seed KB ≥10 FAQs under `backend/kb/` by Week 2 exit.

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
| `OPENAI_MODEL` | Default `gpt-4o-mini` |
| `AAMAD_TARGET_RUNTIME` | `crewai` |
| `BACKEND_PORT` | Default `8000` |
| `NEXT_PUBLIC_API_BASE_URL` | FE → API base |
| `OPERATOR_API_KEY` | Optional gate for `/api/last-result` (`X-Operator-Key`) |
| `LOG_DIR` | Default `project-context/2.build/logs` |
| `KB_DIR` | Default `backend/kb` |
| `CLASSIFIER_CONFIDENCE_MIN` | Default `0.55` |

Chat endpoint is **open for demo**. Optional operator key applies to last-result only.

---

## 4. Quality Attributes

### Scalability

| Metric | MVP target |
|--------|------------|
| Concurrent demo sessions | ≥ 5 (10 aspirational) |
| Horizontal scale | **Deferred** — single backend instance |
| Cost / token control | Small model default; `max_rpm`; short prompts; early refuse on gap |

Scale-out (replicas, shared session store, managed vector DB) is Future Work; MVP optimizes for course-demo concurrency, not production load.

### Reliability

| Concern | Architectural response |
|---------|------------------------|
| End-to-end latency | p95 `/api/chat` < **30s**; FE first status < **10s** |
| Timeouts | Per-task caps + API soft timeout **45s** → escalate envelope |
| LLM / KB outage | Fail-open to human (ADR-11); never invent after tool failure |
| Agent loops / cost overrun | `max_iter ≤ 12`, `max_retry_limit ≥ 2`, crew `max_rpm` |
| Ticket side-effects | Stub only; live connector idempotency deferred |

### Observability

| Signal | Mechanism |
|--------|-----------|
| Liveness | `GET /health` |
| Per-run audit | `trace_id` + Prompt Trace JSON under `LOG_DIR` |
| Pipeline visibility | `steps[]` in API; StatusLine in UI; operator strip |
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
| ADR-08 | Default LLM = **`gpt-4o-mini`** (env override) | Cost-efficient; closes PRD OQ #1 for Build |
| ADR-09 | KB = **local files** under `backend/kb/` (≥10 FAQs) | No external vector SaaS in MVP |
| ADR-10 | Process = **sequential**; no delegation; no memory | Determinism; adapter baseline |
| ADR-11 | Fail-open to human on LLM/KB/timeout | PRD reliability; MRD degrade-to-human |
| ADR-12 | Text-only sentiment; no biometric emotion | MRD/PRD compliance; EU AI Act risk posture |

### Design principles

- Customer / operator feedback first (demo paths A/B/C before enterprise features).
- Minimal viable agent set and simplest orchestration that delivers core value.
- Observable by default (health, structured errors, Prompt Trace).
- Deploy scaffolding deferred to Deliver week (local dual-process first).

---

## Appendix A — Implementation Guidance for AI Development Agents

1. **Setup** (`@project.mgr`): `frontend/`, `backend/`, `backend/config/`, `backend/kb/`, `.env.example`, manifests; `setup.md` — **no business logic**.  
2. **Frontend** (`@frontend.eng`): Next.js UI + mocks + Future Work stubs — **no live BE**.  
3. **Backend** (`@backend.eng`): YAML agents/tasks, tools, `crew.kickoff`, FastAPI routes per this SAD.  
4. **Integration** (`@integration.eng`): wire `lib/api.ts` to `/api/chat`; verify resolve + escalate.  
5. **QA** (`@qa.eng`): unit + integration + AC-01…06 in `qa.md`.  
6. **Deliver** (`@devops.eng`): CI + deploy.md + user-guide — no app logic changes.

**Pilot / demo exit:** KB ≥10 articles; paths A/B/C succeed; operator strip shows decision + reason_codes; no secrets in repo.  
**Post-MVP order:** live ticketing → multi-turn clarifier → streaming → CSAT → persistence/SSO.

---

## Appendix B — Traceability (PRD → Architecture)

| PRD anchor | SAD element |
|------------|-------------|
| AC-01 / AC-01a Disclosure + human control | DisclosureBanner + Talk-to-human (§1–§2) |
| AC-01b Disclosure metadata | `meta.ai_disclosure` + Prompt Trace (§2) |
| AC-02 Pipeline | 4-agent sequential crew + `steps[]` (§2) |
| AC-03 Grounding | kb_search + refuse + `sources_used` (§2) |
| AC-04 Escalation packet | packet schema + reason_codes + ticket_stub (§2) |
| AC-05 Operator | OperatorStrip + optional last-result (§2–§3) |
| AC-06 Health/failure | `/health` + error envelope (§2–§4) |
| §10.1 Logical/Process/Deploy | §§2–3 |
| §10.3 API | §2 contracts |
| No DB / stub ticket | ADR-06, ticket_stub (§5) |
| MRD hybrid FCR / fail-open | ADR-11 (§4–§5) |

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
- Simple KB retrieval (keyword and/or lightweight embeddings) is sufficient; managed vector SaaS deferred.  
- Temperature/model defaults above are architecture guidance; Backend may tune and record in Audit.  
- Architecture epic produces docs only — no application code in this action.  
- `meta` on `ChatResponse` is additive for `AC-01b`; Integration maps when present and ignores if older mocks omit it.  
- Example config `security.require_security_assessment: true` → recommend `@security.eng` before Deliver even if course grading is TBD.  
- MRD “learns and adapts” = offline KB/prompt updates post-MVP, not online fine-tuning (aligned with PRD).

## Open Questions

1. Confirm instructor monorepo naming if not `frontend/` + `backend/`.  
2. Is `/api/last-result` required for grading, or is operator strip fed only from the last chat response in UI state? (Prefer UI state + optional endpoint.)  
3. Exact KB retrieval algorithm and similarity floor — Backend chooses; document in `backend.md`.  
4. Security assessment graded vs optional for this course (PRD OQ #5); until answered, treat as recommended gate.  
5. Public hosting target for Week 6 (local-only vs single cloud VM).  
6. Disclosure UX: acknowledge-to-dismiss vs always-persistent banner — either OK; FE documents choice in `frontend.md`.

## Audit

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-08T21:15:00-05:00 |
| Persona id | system-arch |
| Action | create-sad (restructure to overview / logical / physical / quality / decisions) |
| Prior action | create-sad (gap review) @ 2026-08-08T21:12:00-05:00 |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai (PRD-locked; env unset → adapter default; example config agrees) |
| Prompt Trace | Omitted — architecture synthesis from PRD/MRD; no secrets |
| Model / controls | Deterministic artifact write; N/A temperature for file output |
| Adapter rule | `.cursor/rules/adapter-crewai.mdc` |
| Warning | None — runtime resolved cleanly to crewai |
| Change note | Reorganized SAD into five primary architecture sections; preserved API/agent/packet contracts, ADRs, and AC traceability in appendices |
