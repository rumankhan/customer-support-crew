# Context Summary — Multi-Agent Customer Support Crew

Handoff brief from `@product-mgr` to `@system.arch` and Build personas.

## Product one-liner

An orchestrated multi-agent helpdesk crew for **B-Mobile** (fictional mobile carrier) that classifies inquiries, retrieves grounded knowledge, personalizes responses, scores sentiment/risk, and escalates with full context — 24/7 chat support with human fallback.

## Course / complexity verdict

**Pass** for 6-week AAMAD Build (Architecture → Setup → Frontend → Backend → Integration → QA): 4 agents, chat-only, local KB, ticket stub, no DB, non-streaming JSON, Next.js + CrewAI. See PRD §8 validation table and §10 epic contracts.

## Define stage success indicators

| Indicator | Status |
|-----------|--------|
| Clarity — what & why | **Met** |
| Completeness — architecture-ready PRD | **Met** |
| Alignment — MRD supports PRD | **Met** |
| Scope — core MVP user value | **Met** |

**Define stage: COMPLETE** (incl. SAD). Next: `@project.mgr` → `*setup-project`, then Week 2 `@backend.eng`.

## MVP user value

Customer gets a **grounded chat answer** or a **clean human escalation with full context** — not a blind queue or black-box FAQ bot.

## Artifacts produced

| Artifact | Path | Action |
|----------|------|--------|
| MRD | `project-context/1.define/mrd.md` | `*create-mrd` |
| PRD | `project-context/1.define/prd.md` | `*create-context` (+ course alignment) |
| Context summary | `project-context/1.define/context-summary.md` | `*create-context` |
| SAD | `project-context/1.define/sad.md` | `*create-sad` |

## Resolved runtime

- **`AAMAD_TARGET_RUNTIME`**: `crewai` (**locked** for course MVP)
- YAML agents/tasks; sequential process; `memory=False`

## MVP scope (approved context boundary)

**In**
- Web chat with AI disclosure (`AC-01`)
- Sequential **4-agent** crew: Classifier → Retriever → Response Specialist → Escalation Manager (sentiment+handoff)
- Local/seed KB RAG + refusal (`AC-03`)
- Escalation packet for humans (`AC-04`)
- Minimal operator strip (`AC-05`)
- Health + structured failure path (`AC-06`)

**Out (Future Work / P1)**
- Live ticketing, voice, CRM writes, streaming, multi-turn clarifier, CSAT dashboard, DB, SSO, online learning, biometric emotion

## Agent roster (for SAD) — max 4

1. `query_classifier`  
2. `knowledge_retriever`  
3. `response_specialist`  
4. `escalation_manager` (includes text sentiment/risk)

## Critical constraints

- Text-only sentiment; Art. 50-style disclosure P0  
- Secrets via env only; redact traces  
- No database; no live third-party integrations in MVP  
- Named task outputs (`ClassifierOutput`…`EscalationPacket`); retrieval floor `0.35` (SAD ADR-13)  
- Operator strip from last `ChatResponse` UI state; StatusLine = optimistic local animation (no streaming)  
- Sprint 1 = vertical slice before UI polish  
- **Fixed 6-week delivery:** 2026-08-01 → 2026-09-12 (**Week 2 current**)

## 6-Week timeline (six Build epics)

| Week | Dates | Epic(s) | Status |
|------|-------|---------|--------|
| 1 | Aug 1–7 | Architecture + Setup | Assumed started/complete |
| 2 | Aug 8–14 | Backend (crew + named schemas) | **Current** |
| 3 | Aug 15–21 | Backend API + thin FE vertical slice | Upcoming |
| 4 | Aug 22–28 | FE polish + Integration | Upcoming |
| 5 | Aug 29–Sep 4 | QA (+ security recommended) | Upcoming |
| 6 | Sep 5–12 | Deliver | Upcoming |

## Next recommended actions

1. `@project.mgr` → `*setup-project` / `*configure-env` / `*document-setup`  
2. `@backend.eng` → named `output_pydantic` models + crew YAML + kickoff + `POST /api/chat` vertical slice per SAD  
3. Do not expand into P1 (live ticketing, streaming, DB); polish StatusLine/OperatorStrip after slice works

## Sources

- `project-context/1.define/mrd.md`
- `project-context/1.define/prd.md` (§8–§10)
- `project-context/1.define/sad.md` (ADR-13/14/15; Sprint 1 slice)
- AAMAD README Phase 2 epics; SAD template MVP agent cap
- Operator: 6-week course alignment (2026-08-08); pre-Build sharpen (2026-08-12)

## Assumptions

- Course MVP freezes: stub ticketing, no DB, crewai, non-streaming, 4 agents
- Project clock started 2026-08-01
- Retrieval hybrid + floor 0.35; AC-05 via UI state (SAD OQ #2–#3 closed)

## Open Questions

- See PRD §Open Questions (disclosure copy, folder naming, security grading). SAD OQ #2 (operator path) and #3 (retrieval floor) are **resolved**.

## Audit

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-12T07:36:00-05:00 |
| Persona id | product-mgr |
| Action | sharpen-context-summary (pre-Build feedback sync) |
| Prior action | create-context (define success gate) @ 2026-08-08T13:49:48-05:00 |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai (locked) |
| Prompt Trace | Omitted — handoff summary only; no secrets |
| Change note | Synced Sprint 1 vertical slice, closed SAD OQs, StatusLine/operator/retrieval locks |
