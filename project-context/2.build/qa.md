# QA Report: Multi-Agent Customer Support Crew (Frontend, mock data)

**Persona**: `@qa.eng`  
**Actions**: `*qa`, `*verify-flow` (UI + mocks only), `*log-defects`, `*future-work`  
**Status**: **PASS with scoped gaps** — frontend smoke re-run **2026-08-15T17:27–17:28-05:00** after chat-window UI. Live crew / FastAPI not in this run.  
**Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)  
**Test date**: 2026-08-15 (initial) + crew-status retest 09:28 + CSV/KB retest 11:55–11:57-05:00 + **chat UI retest 17:27–17:28-05:00**  
**Harness**: Cursor IDE browser against `http://localhost:3000/`; `npx tsc --noEmit` PASS (prior); `GET /api/kb` still the mock CSV loader

---

## Scope and gate

This session tests **frontend-related SAD behaviors only**. Backend is not implemented; `lib/api.ts` re-exports stub `startRun` / `getRunStatus` and `lib/mockResponse.ts` supplies Path A/B/C `ChatResponse` shapes.

| In this run | Out of this run |
|-------------|-----------------|
| Disclosure, chat window, composer, FSM, StatusLine labels, specialist strip, session thread, Future Work stubs, dummy CSV retrieval | `POST /api/chat`, `GET /health`, CrewAI `kickoff`, Prompt Trace files, live `kb_search`, ticket_stub live, `/api/last-result` |
| Mock Path A / B / C against `backend/kb/articles.csv` via mock `GET /api/kb` | Live LLM / CrewAI timeout after 45s API soft timeout |
| Viewport 375px and 1280px layout | Performance / load / concurrent 5-session NFR |

**Verdict for FE epic:** demo Paths A/B/C and AC-01 / AC-03 / AC-04 / AC-05 **UI bindings** pass on mocks. **Full MVP QA is blocked** until Backend + Integration exist.

Recommend `@security.eng` → `project-context/2.build/security.md` before Deliver (`security.require_security_assessment: true` in `aamad.config.example.yml`; project has no `aamad.config.yml`).

---

## Unit

| ID | Check | AC | Result | Notes |
|----|-------|----|--------|-------|
| U-01 | Automated unit suite for `lib/fsm.ts`, mock selectors, validation | — | **SKIP** | No `*.test.*` under `frontend/`. Retest ran `tsc --noEmit` and `next lint` instead (both PASS). |
| U-02 | FSM `idle → running → done` and `done → idle` on **Start new conversation** | AC-02 | **PASS** (observed in browser 17:27) | Illegal transitions not exercised as a unit table. Start new conversation **clears** the thread (not keep-history). |
| U-03 | Classification parse / gap→refuse / packet field unit tests | AC-03, AC-04 | **N/A** | Backend not present. Mock composer uses CSV-backed Path A/B plus static Path C. |
| U-04 | `parseKbCsv` + overlap floor on canonical CSV | AC-03 | **PASS** (scripted, no Jest) | 12 rows; PIN query → `01-account-pin` score 1.0; drone query → no hit. |

No Jest suite exists. CSV parser was smoke-checked with `tsx` against `backend/kb/articles.csv`.

---

## Integration

| ID | Check | AC | Result | Notes |
|----|-------|----|--------|-------|
| I-01 | FE `fetch` to `POST /api/chat` | AC-02…05 | **BLOCKED** | `lib/api.ts` is the Integration hook; no live call. Copy on Inputs states mocked services. |
| I-02 | CORS `localhost:3000` / `127.0.0.1:3000` | — | **N/A** | No backend origin. |
| I-03 | `GET /health` → `{ "status": "ok" }` | AC-06a | **BLOCKED** | Backend liveness; not a FE mock. |
| I-04 | Error envelope + FE abort 50–60s | AC-06b | **PARTIAL** | Client abort constant is `55_000` ms in `useResearchWorkflow.ts`. Stub latency is ~1.8s, so the timeout / `mockTimeout` path is **not reachable from the UI**. |
| I-05 | `meta.ai_disclosure` on live response | AC-01b | **PARTIAL** | Mocks always set `meta.ai_disclosure: true` and echo `disclosure_acknowledged`. Operator strip does **not** display `meta`. |
| I-06 | Mock `GET /api/kb` serves `backend/kb/articles.csv` | AC-03 | **PASS** | HTTP 200, `Content-Type: text/csv; charset=utf-8`, 3490 bytes, header `id,title,body` + 12 FAQ rows. Not the product `POST /api/chat`. |

---

## Smoke / acceptance (browser)

Environment: light-theme Next.js App Router page titled “B-Mobile Support”; header “B-Mobile Support Crew” / “How can we help?”; single route `/` (**chat window**: You right / B-Mobile left; Status under chat; **For specialists**). Dummy retrieval: `GET /api/kb` → `backend/kb/articles.csv` → `searchKb()` in `frontend/lib/kb.ts`.

### AC-01 — AI-disclosed intake

| ID | Check | Result | Evidence |
|----|-------|--------|----------|
| AC-01 | Disclosure visible on first paint; copy states the assistant is AI | **PASS** | Amber banner: “You are chatting with the B-Mobile AI assistant…”. Button **I understand**. |
| AC-01a | Control to request human | **PASS** | Checkbox **I'd rather talk to a person** toggles; Path C used checked state (17:27). |
| AC-01b | Disclosure does not block chat; metadata echoed in mock | **PASS** | Path A submitted **before** acknowledge. After acknowledge, banner compact-persists (prior). Mock `meta.disclosure_acknowledged` follows the control (not shown in strip). |
| FE-VAL | Empty submit stays idle | **PASS** | Alert: **Please type a question so we can help.** (17:27). Status still Ready. |
| FE-KEY | Enter in query field submits (Shift+Enter not required for this check) | **PASS** | `keydown` Enter `preventDefault` + run completed for Path A PIN query. |
| FE-CAP | 4000-character cap | **PASS** | Counter “4000 characters left”; `textarea maxLength=4000`. |

### AC-02 — Pipeline visibility (UI / mocks)

| ID | Check | Result | Evidence |
|----|-------|--------|----------|
| AC-02a | Four agent step identities on completed mock | **PASS** | `query_classifier`, `knowledge_retriever`, `response_specialist`, `escalation_manager`. |
| AC-02b | Ordered step summaries expandable in operator strip | **PASS** | **Show how we handled this** / **Hide how we handled this** (17:28). |
| AC-02c | Prompt Trace file `{LOG_DIR}/{trace_id}.json` | **N/A** | Backend. UI shows `trace_id` (e.g. `trace-942ea5fe-…`). |
| ADR-15 | First StatusLine label within 10s of send | **PASS** | Immediate pending B-Mobile bubble **Understanding your question …**; submit **Looking that up…**; composer disabled. Observed on Path A at 17:27:22. |

### Demo Path A — resolve + sources (`AC-03`)

Query: `How do I reset my B-Mobile My Account PIN?` (neutral).

| Expectation (SAD) | Observed | Result |
|-------------------|----------|--------|
| `decision=resolve` | Operator strip Decision **resolve** | **PASS** |
| Non-empty `sources_used` | “Reset your B-Mobile My Account PIN” + snippet from CSV body | **PASS** (11:56 retest) |
| `packet=null` | No packet JSON on resolve | **PASS** |
| No escalate notice | Escalate banner absent | **PASS** |

**Defect (low):** mock `reason_codes` is `grounded_kb_hit` (not in SAD enum). Harmless for UI binding; Integration should not treat this as a live crew code.

### Demo Path B — unknown topic escalate (`AC-03b`, `AC-04a`, ADR-16)

Query: `What is your quantum warranty for the hardware drone?`

| Expectation (SAD) | Observed | Result |
|-------------------|----------|--------|
| `decision=escalate` (never resolve-only refuse) | Decision **escalate** | **PASS** |
| Refuse-style reply | “I don’t have that in the B-Mobile help articles…” | **PASS** |
| Empty sources | No source list | **PASS** |
| Packet + `stub_ticket_id` | Packet JSON + `STUB-TRACE-65` (17:27; IDs vary per mock run) | **PASS** |
| Packet fields (intent, customer_message, draft_reply, sentiment, risk, reason_codes, stub) | Present; `request_human: false` | **PASS** |
| Talk-to-human notice | “We're connecting you with a B-Mobile specialist… Reference: STUB-TRACE-65” | **PASS** (17:27) |
| `reason_codes` include `retrieval_gap` and/or `refused` | **`retrieval_gap`, `refused`** | **PASS** (11:56 retest; DEF-01 closed) |

**DEF-01 (closed):** Earlier mock used `kb_gap`; Path B now emits SAD `retrieval_gap` + `refused`.

### Demo Path C — request human (`AC-04b`)

Query: `I want to talk to a human now — this billing charge is ridiculous!` with checkbox on.

| Expectation (SAD) | Observed | Result |
|-------------------|----------|--------|
| `decision=escalate` | escalate | **PASS** |
| `reason_codes` include `request_human` | `request_human` | **PASS** |
| Full `steps[]` (4) | Four summaries | **PASS** |
| Packet + stub; `request_human: true` | `STUB-TRACE-90` (17:27; IDs vary per mock run) | **PASS** |

### AC-05 — Operator strip from last `ChatResponse` (ADR-14)

| Check | Result |
|-------|--------|
| Strip shows `decision`, `reason_codes`, expandable `steps[]`, `trace_id` from UI state (no `/api/last-result`) | **PASS** — heading **For specialists**; **Show how we handled this** expands four agent steps (17:28 Path C). Outcome still includes contract `decision` in parentheses. |
| Session thread is the chat transcript (no History list) | **PASS** — Path B then Path C both visible as You / B-Mobile pairs. Click-to-restore a past run is **removed**. |
| **Start new conversation** → FSM idle; thread and specialist strip cleared | **PASS** (17:27 after Path A; empty chat prompt returned; Start new conversation hidden until the next send) |

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
| Session history prepend + three demo paths listed | **SUPERSEDED** | Chat transcript is the session thread. No Recent questions list. |

### Crew status visibility (operator add-on, 2026-08-15)

Operator asked to make crew status obvious. Status lives in the **Status** card (`role="status"`) under the chat. Customer labels: **Ready** / **Looking that up** / **Finished** (`frontend/lib/uiCopy.ts`). Red **Couldn't finish** is implemented but still not reachable from the UI (stub ~1.8s; same as DEF-05).

| ID | Requirement | Initial | Retest (09:28) | CSV retest (11:56) | Chat retest (17:27) | Evidence |
|----|-------------|---------|----------------|--------------------|---------------------|----------|
| ST-01 | Visible idle / running / done | FAIL | **PASS** | **PASS** | **PASS** | Status card only. First paint **Ready**. Running: **Looking that up** + **Understanding your question**. Complete: **Finished**. |
| ST-02 | Color pill: gray / blue / green / red | FAIL | **PASS** (error not exercised) | **PASS** (error not exercised) | **PASS** (error not exercised) | Same mapping; red unhit. |
| ST-03 | Last updated near status | FAIL | **PASS** | **PASS** | **PASS** | Status card. Path A ~17:27:24; Path B 17:27:40; Path C 17:27:54. |
| ST-04 | Same wording status / buttons / inline | FAIL | **PASS** | **PASS** | **PASS** | Idle/done submit **Get help**. Running submit **Looking that up…**. Pill customer labels. **Start new conversation** beside Get help when the thread is not empty. |

**Phrasing inventory (chat UI, 17:27)**

| Surface | Idle | Running | Done |
|---------|------|---------|------|
| Status pill | `Ready` | `Looking that up` (+ Understanding your question) | `Finished` |
| Submit button | `Get help` | `Looking that up…` | `Get help` |

Validation empty-submit keeps **Ready** (crew did not start) and shows composer alert — intended.

---

## Defects

| ID | Severity | AC / SAD | Description | Suggested owner |
|----|----------|----------|-------------|-----------------|
| DEF-01 | Medium | AC-03b / reason_codes | **CLOSED** — Path B mock now uses SAD `retrieval_gap` + `refused`. | — |
| DEF-02 | Low | Reason-code vocabulary | Path A mock uses `grounded_kb_hit` (not in SAD list). Resolve may use empty codes or omit extras. | `@frontend.eng` |
| DEF-03 | Low | AC-06b CTA | Escalate card copy is informational (“Talk-to-human is available…”) rather than a control that sets `request_human` and re-runs. Checkbox remains the AC-01a control. | `@frontend.eng` (polish) |
| DEF-04 | Low | `frontend.md` Inputs/Run vs code | **CLOSED** — spec now allows submit from `done` without reset; **Start new conversation** is optional and **clears** the thread. | Spec sync |
| DEF-05 | Coverage | AC-06b | Timeout / error envelope cannot be triggered from the UI with current stub latency. | `@frontend.eng` (dev-only mock switch) or Integration once API exists |
| DEF-06 | Medium | Crew status banner | **FIXED** (retest PASS) | Top `CrewStatusBanner` shows `Crew: idle/running/done`. |
| DEF-07 | Medium | Crew status color | **FIXED** (error color unexercised) | Gray/blue/green pills verified. Red implemented, no UI trigger (DEF-05). |
| DEF-08 | Medium | Last updated | **FIXED** (retest PASS) | Timestamp on banner and Run card; updates on start/complete/reset/history. |
| DEF-09 | Low | Consistent phrasing | **FIXED** (retest PASS) | Shared `CREW_STATUS_LABEL`; running button matches banner. |

Open defects remain DEF-02, DEF-03, DEF-05. Crew-status add-on ST-01…ST-04 **pass** on idle/running/done with customer labels. DEF-01 and DEF-04 closed.

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

- Live Path A/B/C against `articles.csv` after `@backend.eng` + `@integration.eng` (`kb_search`, not mock `GET /api/kb`).
- AC-06a health; AC-06b LLM/timeout envelope + 55s abort with partial `steps[]` and minimal packet.
- Unit tests for `transitionRunPhase`, `selectMockResponse`, 4000-char validation (`testing.require_unit_tests` in example config).
- Integration tests for `ChatRequest` / `ChatResponse` schema, CORS, disclosure metadata.
- Chat UI is the session thread (no History list). Persist in `localStorage` remains an Open Question.
- Concurrent demo sessions (best-effort; do not fail QA solely on serial kickoff).
- Accessibility beyond demo bar (focus order, contrast ratios).
- `/api/last-result` optional polish — not required for AC-05.

---

## Sources

- `project-context/1.define/sad.md` (§1–2 UI, demo queries A/B/C, ADR-14/15/16, testing expectations)
- `project-context/1.define/prd.md` (AC-01…AC-06)
- `project-context/2.build/frontend.md` (behavior + implementation; former `frontend-funcional-spec.md` folded in)
- `.cursor/agents/qa-eng.md`
- `aamad.config.example.yml` (testing + security flags; no `aamad.config.yml`)
- Browser session at `http://localhost:3000/` on 2026-08-15

## Assumptions

- Operator scoped this QA run to **frontend + mocks**; missing `backend.md` / `integration.md` is expected, not a halt for this slice.
- Chat window on `/` satisfies SAD “Web chat UI (`/`)” (PRD §6 / `frontend.md`).
- Session-only thread is allowed; SAD DB/history remains Future Work. **Start new conversation** clears the tab.
- `AAMAD_TARGET_RUNTIME` unset → `crewai`.
- Screenshots captured during earlier sessions are local QA evidence, not committed artifacts.

## Open Questions

1. ~~Should mock Path B `kb_gap` be renamed to `retrieval_gap`~~ — **Resolved:** Path B uses `retrieval_gap`.
2. Should QA fail the epic until an explicit UI trigger exists for AC-06b (`mockTimeout`)? Current recommendation: **no** for FE-only gate; **yes** for full MVP gate.
3. ~~Confirm whether Start-from-`done` without New research is intended~~ — **Resolved:** submit from `done` is allowed; **Start new conversation** clears the thread.
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
| Warning | Full AC-02c / AC-06a / live AC-06b not validated. |

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

### Audit (append)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-15T11:10:00-05:00 |
| Persona id | qa-eng |
| Action | qa (doc sync after B-Mobile domain + dummy KB) |
| Result | DEF-01 closed in mocks; Path A/B queries aligned to B-Mobile corpus. Full browser retest not re-run in this pass. |

### Audit (retest CSV KB)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-15T11:57:00-05:00 |
| Persona id | qa-eng |
| Action | qa (browser smoke + verify-flow after `articles.csv` + mock `GET /api/kb`) |
| Result | **PASS with scoped gaps** — AC-01…05 UI, Paths A/B/C from CSV, ST-01…04 idle/running/done in Run card. Open: DEF-02…05, AC-06a/b live, ST-02 red unexercised. |
| Static checks | `npx tsc --noEmit` PASS; `npx next lint` PASS (0 warnings); `GET /api/kb` 200 CSV 12 FAQs |
| Prompt Trace | Omitted — UI + mocks; no secrets |

### Audit (retest chat UI)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-15T17:28:00-05:00 |
| Persona id | qa-eng |
| Action | qa (browser smoke after chat window + Start new conversation; expected checks synced) |
| Result | **PASS with scoped gaps** — Chat + Get help + Looking that up; Path A sources; Path B escalate; Path C request_human; Start new conversation clears thread. Open: DEF-02, DEF-03, DEF-05, AC-06a/b live, ST-02 red unexercised. DEF-04 closed. |
| Prompt Trace | Omitted — UI + mocks; no secrets |
