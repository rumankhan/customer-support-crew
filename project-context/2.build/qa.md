# QA Report: Multi-Agent Customer Support Crew (Frontend, mock data)

**Persona**: `@qa.eng`  
**Actions**: `*qa`, `*verify-flow` (UI + mocks only), `*log-defects`, `*future-work`  
**Status**: **PASS with scoped gaps** — frontend smoke re-run 2026-08-15T09:29 after crew-status fix. Live crew / FastAPI not in this run.  
**Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)  
**Test date**: 2026-08-15 (initial) + **retest 2026-08-15T09:28–09:30-05:00**  
**Harness**: Cursor IDE browser against `http://localhost:3000/`; `npx tsc --noEmit` PASS; `npx next lint` PASS

---

## Scope and gate

This session tests **frontend-related SAD behaviors only**. Backend is not implemented; `lib/api.ts` re-exports stub `startRun` / `getRunStatus` and `lib/mockResponse.ts` supplies Path A/B/C `ChatResponse` shapes.

| In this run | Out of this run |
|-------------|-----------------|
| Disclosure, composer, FSM, StatusLine labels, result/escalate card, operator strip, session history, Future Work stubs | `POST /api/chat`, `GET /health`, CrewAI `kickoff`, Prompt Trace files, KB retrieval, ticket_stub live, `/api/last-result` |
| Mock Path A / B / C | Live LLM / KB / timeout after 45s API soft timeout |
| Viewport 375px and 1280px layout | Performance / load / concurrent 5-session NFR |

**Verdict for FE epic:** demo Paths A/B/C and AC-01 / AC-03 / AC-04 / AC-05 **UI bindings** pass on mocks. **Full MVP QA is blocked** until Backend + Integration exist.

Recommend `@security.eng` → `project-context/2.build/security.md` before Deliver (`security.require_security_assessment: true` in `aamad.config.example.yml`; project has no `aamad.config.yml`).

---

## Unit

| ID | Check | AC | Result | Notes |
|----|-------|----|--------|-------|
| U-01 | Automated unit suite for `lib/fsm.ts`, mock selectors, validation | — | **SKIP** | No `*.test.*` under `frontend/`. Retest ran `tsc --noEmit` and `next lint` instead (both PASS). |
| U-02 | FSM `idle → running → done` and `done → idle` on New research | AC-02 | **PASS** (observed in browser) | Illegal transitions not exercised as a unit table. |
| U-03 | Classification parse / gap→refuse / packet field unit tests | AC-03, AC-04 | **N/A** | Backend not present. Mock composer uses static payloads. |

No unit tests were authored in this session (browser smoke only, per operator scope).

---

## Integration

| ID | Check | AC | Result | Notes |
|----|-------|----|--------|-------|
| I-01 | FE `fetch` to `POST /api/chat` | AC-02…05 | **BLOCKED** | `lib/api.ts` is the Integration hook; no live call. Copy on Inputs states mocked services. |
| I-02 | CORS `localhost:3000` / `127.0.0.1:3000` | — | **N/A** | No backend origin. |
| I-03 | `GET /health` → `{ "status": "ok" }` | AC-06a | **BLOCKED** | Backend liveness; not a FE mock. |
| I-04 | Error envelope + FE abort 50–60s | AC-06b | **PARTIAL** | Client abort constant is `55_000` ms in `useResearchWorkflow.ts`. Stub latency is ~1.8s, so the timeout / `mockTimeout` path is **not reachable from the UI**. |
| I-05 | `meta.ai_disclosure` on live response | AC-01b | **PARTIAL** | Mocks always set `meta.ai_disclosure: true` and echo `disclosure_acknowledged`. Operator strip does **not** display `meta`. |

---

## Smoke / acceptance (browser)

Environment: light-theme Next.js App Router page titled “Critical Research Workflow”; single route `/` (form + results, not a chat bubble list — documented in `frontend.md`).

### AC-01 — AI-disclosed intake

| ID | Check | Result | Evidence |
|----|-------|--------|----------|
| AC-01 | Disclosure visible on first paint; copy states the assistant is AI | **PASS** | Amber banner: “You are chatting with an AI assistant…”. Button **I understand**. |
| AC-01a | Control to request human | **PASS** | Checkbox “Talk to a human (sets request_human for this run)” toggles; Path C used checked state. |
| AC-01b | Disclosure does not block chat; metadata echoed in mock | **PASS** | Path A submitted **before** acknowledge. After acknowledge, banner compact-persists. Mock `meta.disclosure_acknowledged` follows the control (not shown in strip). |
| FE-VAL | Empty submit stays idle | **PASS** | Alert: “Enter a research question to start a run.” |
| FE-KEY | Enter in query field submits (Shift+Enter not required for this check) | **PASS** | `keydown` Enter `preventDefault` + run completed for `password reset please`. |
| FE-CAP | 4000-character cap | **PASS** | Counter “4000 characters left”; `textarea maxLength=4000`. |

### AC-02 — Pipeline visibility (UI / mocks)

| ID | Check | Result | Evidence |
|----|-------|--------|----------|
| AC-02a | Four agent step identities on completed mock | **PASS** | `query_classifier`, `knowledge_retriever`, `response_specialist`, `escalation_manager`. |
| AC-02b | Ordered step summaries expandable in operator strip | **PASS** | “Show / Hide step summaries”. |
| AC-02c | Prompt Trace file `{LOG_DIR}/{trace_id}.json` | **N/A** | Backend. UI shows `trace_id` (e.g. `trace-942ea5fe-…`). |
| ADR-15 | First StatusLine label within 10s of send | **PASS** | Immediate **Crew: running — Classifying** (banner + Run card); submit button **Crew: running**; form disabled. Observed at 22ms. |

### Demo Path A — resolve + sources (`AC-03`)

Query: `How do I reset my Acme Cloud password?` (neutral).

| Expectation (SAD) | Observed | Result |
|-------------------|----------|--------|
| `decision=resolve` | Operator strip Decision **resolve** | **PASS** |
| Non-empty `sources_used` | “Reset your Acme Cloud password” + snippet | **PASS** |
| `packet=null` | No packet JSON on resolve | **PASS** |
| No escalate notice | Escalate banner absent | **PASS** |

**Defect (low):** mock `reason_codes` is `grounded_kb_hit` (not in SAD enum). Harmless for UI binding; Integration should not treat this as a live crew code.

### Demo Path B — unknown topic escalate (`AC-03b`, `AC-04a`, ADR-16)

Query: `What is your quantum warranty for the hardware drone?`

| Expectation (SAD) | Observed | Result |
|-------------------|----------|--------|
| `decision=escalate` (never resolve-only refuse) | Decision **escalate** | **PASS** |
| Refuse-style reply | “I don’t have that in my knowledge base…” | **PASS** |
| Empty sources | No source list | **PASS** |
| Packet + `stub_ticket_id` | Packet JSON + `STUB-TRACE-55` | **PASS** |
| Packet fields (intent, customer_message, draft_reply, sentiment, risk, reason_codes, stub) | Present; `request_human: false` | **PASS** |
| Talk-to-human notice | “This run needs a human… Stub ticket: STUB-TRACE-55” | **PASS** |
| `reason_codes` include `retrieval_gap` and/or `refused` | **`kb_gap`, `refused`** | **FAIL (mock naming)** |

**DEF-01 (medium):** Mock Path B uses `kb_gap` instead of SAD `retrieval_gap`. UI still renders codes; live mapper must emit SAD names.

### Demo Path C — request human (`AC-04b`)

Query: `I want to talk to a human now — this billing charge is ridiculous!` with checkbox on.

| Expectation (SAD) | Observed | Result |
|-------------------|----------|--------|
| `decision=escalate` | escalate | **PASS** |
| `reason_codes` include `request_human` | `request_human` | **PASS** |
| Full `steps[]` (4) | Four summaries | **PASS** |
| Packet + stub; `request_human: true` | `STUB-TRACE-66`; packet `request_human: true` | **PASS** |

### AC-05 — Operator strip from last `ChatResponse` (ADR-14)

| Check | Result |
|-------|--------|
| Strip shows `decision`, `reason_codes`, expandable `steps[]`, `trace_id` from UI state (no `/api/last-result`) | **PASS** |
| History click rebinds Results to that run without re-fetch | **PASS** (Path A restored; `runId` switched to Path A’s id; form query unchanged per spec) |
| New research → FSM idle; last result and history kept | **PASS** |

### AC-06 — Health and failure (frontend-reachable)

| ID | Check | Result |
|----|-------|--------|
| AC-06a | `GET /health` | **BLOCKED** (backend) |
| AC-06b | Structured error + safe message + escalate CTA | **NOT EXERCISED** in UI. `mockTimeout` exists (`error.code=llm_or_timeout`, partial steps, minimal packet) but stub completes in ~1.8s, well under 55s abort. Unknown-`runId` envelope is not a user path. |

### Layout, a11y (demo bar), Future Work

| Check | Result |
|-------|--------|
| Responsive 375px | **PASS** — `innerWidth=375`, `scrollWidth=375`, no horizontal overflow. Inputs usable. |
| Responsive 1280px | **PASS** — centered `max-w-3xl` column; FSM and composer visible. |
| Keyboard send + focusable primary controls | **PASS** |
| Contrast (demo) | **PASS** (qualitative: dark text on canvas, white on ink pills, blue submit). No WCAG audit. |
| Future Work stubs Voice / CSAT dashboard / Live ticketing | **PASS** — `span`s, `cursor: not-allowed`, title “Not available in MVP”, not buttons. |
| Session history prepend + three demo paths listed | **PASS** (four entries after Enter-key extra Path A). Refresh-clears copy present. |

### Crew status visibility (operator add-on, 2026-08-15)

Operator asked to make crew status obvious. **Initial check FAIL** (DEF-06…09). **Retest after fix: PASS** for idle / running / done. Red **Crew: error** is implemented but still not reachable from the UI (stub ~1.8s; same as DEF-05).

| ID | Requirement | Initial | Retest (09:28) | Evidence |
|----|-------------|---------|----------------|----------|
| ST-01 | Top banner `Crew: idle` / `running` / `done` | FAIL | **PASS** | First paint: `Crew: idle`. Path A running: `Crew: running — Classifying`. Complete: `Crew: done`. Same copy in Run card. |
| ST-02 | Color pill: gray / blue / green / red | FAIL | **PASS** (error not exercised) | Idle `rgb(231, 229, 228)` gray; running `rgb(29, 78, 216)` blue; done `rgb(5, 150, 105)` green. Red mapped in `CREW_STATUS_PILL.error`, not hit in UI. |
| ST-03 | Last updated near status | FAIL | **PASS** | Banner + Run card. Idle `9:28:31 AM` → running `9:29:18` → done `9:29:20`. History select bumped to `9:29:36`. |
| ST-04 | Same wording banner / buttons / inline | FAIL | **PASS** | Idle/done submit remains action **Start research run**. While running, button = **Crew: running**. Pills use `Crew: {state}`. **New research** stays an action label. |

**Phrasing inventory (retest)**

| Surface | Idle | Running | Done |
|---------|------|---------|------|
| Top banner | `Crew: idle` | `Crew: running — Classifying` | `Crew: done` |
| Run pill | `Crew: idle` | `Crew: running` | `Crew: done` |
| Submit button | `Start research run` | `Crew: running` | `Start research run` |

Validation empty-submit keeps **Crew: idle** (crew did not start) and shows form alert — intended.

---

## Defects

| ID | Severity | AC / SAD | Description | Suggested owner |
|----|----------|----------|-------------|-----------------|
| DEF-01 | Medium | AC-03b / reason_codes | Path B mock uses `kb_gap` instead of SAD `retrieval_gap`. | `@frontend.eng` (mock) then `@backend.eng` (live mapper) |
| DEF-02 | Low | Reason-code vocabulary | Path A mock uses `grounded_kb_hit` (not in SAD list). Resolve may use empty codes or omit extras. | `@frontend.eng` |
| DEF-03 | Low | AC-06b CTA | Escalate card copy is informational (“Talk-to-human is available…”) rather than a control that sets `request_human` and re-runs. Checkbox remains the AC-01a control. | `@frontend.eng` (polish) |
| DEF-04 | Low | `frontend-funcional-spec.md` vs code | Spec says submit enabled only in `idle` / after reset; code allows Start from `done` without reset (also listed as an allowed transition in the same spec). | Spec sync |
| DEF-05 | Coverage | AC-06b | Timeout / error envelope cannot be triggered from the UI with current stub latency. | `@frontend.eng` (dev-only mock switch) or Integration once API exists |
| DEF-06 | Medium | Crew status banner | **FIXED** (retest PASS) | Top `CrewStatusBanner` shows `Crew: idle/running/done`. |
| DEF-07 | Medium | Crew status color | **FIXED** (error color unexercised) | Gray/blue/green pills verified. Red implemented, no UI trigger (DEF-05). |
| DEF-08 | Medium | Last updated | **FIXED** (retest PASS) | Timestamp on banner and Run card; updates on start/complete/reset/history. |
| DEF-09 | Low | Consistent phrasing | **FIXED** (retest PASS) | Shared `CREW_STATUS_LABEL`; running button matches banner. |

Open defects remain DEF-01…05. Crew-status add-on ST-01…ST-04 **pass** on idle/running/done.

---

## Coverage vs SAD testing expectations

| Stage (SAD §4) | This run |
|----------------|----------|
| Unit: classification parse; gap→refuse; `request_human`→escalate; packet fields; health | Packet/gap/request_human **UI-mocked only**; health **not run** |
| Integration: FE↔API↔crew; error path; `meta.ai_disclosure` | **Blocked** on API; meta present in mocks only |
| Smoke / AC-01…06; demo A/B/C | FE smoke **A/B/C PASS**; AC-06a/b live **open** |

Runtime checks deferred: YAML load, Prompt Trace file for `trace_id`, real `ticket_stub`.

---

## Future work (testing)

- Live Path A/B/C against ≥10 FAQ KB after `@backend.eng` + `@integration.eng`.
- AC-06a health; AC-06b LLM/timeout envelope + 55s abort with partial `steps[]` and minimal packet.
- Unit tests for `transitionRunPhase`, `selectMockResponse`, 4000-char validation (`testing.require_unit_tests` in example config).
- Integration tests for `ChatRequest` / `ChatResponse` schema, CORS, disclosure metadata.
- Chat message-list polish vs current form+results (FE Open Question).
- Concurrent demo sessions (best-effort; do not fail QA solely on serial kickoff).
- Accessibility beyond demo bar (focus order, contrast ratios).
- `/api/last-result` optional polish — not required for AC-05.

---

## Sources

- `project-context/1.define/sad.md` (§1–2 UI, demo queries A/B/C, ADR-14/15/16, testing expectations)
- `project-context/1.define/prd.md` (AC-01…AC-06)
- `project-context/2.build/frontend.md`
- `project-context/2.build/frontend-funcional-spec.md`
- `.cursor/agents/qa-eng.md`
- `aamad.config.example.yml` (testing + security flags; no `aamad.config.yml`)
- Browser session at `http://localhost:3000/` on 2026-08-15

## Assumptions

- Operator scoped this QA run to **frontend + mocks**; missing `backend.md` / `integration.md` is expected, not a halt for this slice.
- Form + results single route satisfies SAD “Web chat UI (`/`)” for the FE epic (operator-requested layout in `frontend.md`).
- Session-only History is allowed; SAD DB/history remains Future Work.
- `AAMAD_TARGET_RUNTIME` unset → `crewai`.
- Screenshots captured during the session (first paint, Path A/B/C, 375px, 1280px) are local QA evidence, not committed artifacts.

## Open Questions

1. Should mock Path B `kb_gap` be renamed to `retrieval_gap` before Integration treats mocks as fixtures?
2. Should QA fail the epic until an explicit UI trigger exists for AC-06b (`mockTimeout`)? Current recommendation: **no** for FE-only gate; **yes** for full MVP gate.
3. Confirm whether Start-from-`done` without New research is intended (spec disagrees with itself).
4. Security assessment graded vs optional (SAD OQ); until answered, treat `@security.eng` as recommended before Deliver.
5. Should `Crew: error` be a fourth FSM state, or only a red treatment when `ChatResponse.error != null` while phase stays `done`?

## Audit

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-15T07:40:00-05:00 |
| Persona id | qa-eng |
| Action | qa (browser smoke + verify-flow FE mocks + log-defects + future-work) |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai (unset → adapter default) |
| Prompt Trace | Omitted — no crew LLM prompts; mock replies are static. No secrets. |
| Model / controls | Browser functional checks; no temperature. FE client abort 55s (not hit). |
| Adapter rule | `.cursor/rules/adapter-crewai.mdc` (runtime checks deferred) |
| Next recommended persona | `@backend.eng` then `@integration.eng`; `@security.eng` before Deliver |
| Warning | Full AC-02c / AC-06a / live AC-06b not validated. DEF-01 mock reason_code mismatch. |

### Audit (append)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-15T08:35:00-05:00 |
| Persona id | qa-eng |
| Action | qa (crew status visibility: banner, color pill, last updated, phrasing) |
| Result | **FAIL** ST-01…ST-04; defects DEF-06…DEF-09 |
| Prompt Trace | Omitted — UI inspection only |

### Audit (retest)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-15T09:30:00-05:00 |
| Persona id | qa-eng |
| Action | qa (full FE retest after crew-status fix) |
| Result | **PASS with scoped gaps** — AC-01…05 UI, Paths A/B/C, ST-01…04 idle/running/done. DEF-06…09 closed. Open: DEF-01…05, AC-06a/b live, ST-02 red unexercised. |
| Static checks | `npx tsc --noEmit` PASS; `npx next lint` PASS (0 warnings) |
| Prompt Trace | Omitted — UI + mocks; no secrets |
