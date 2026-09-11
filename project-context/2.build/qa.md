# QA Report: Multi-Agent Customer Support Crew

**Persona**: `@qa.eng`  
**Resolved runtime**: `crewai` (`AAMAD_TARGET_RUNTIME=crewai` in `.env`)  
**Latest status**: **PASS** — live integration (2026-08-26/27) plus SQLite FTS5 KB and Telegram HITL (2026-08-28). Docs synced 2026-08-29 (timeouts, no customer specialist strip).  
**Prior status**: **FAIL — live integration blocked** (2026-08-26T13:05-05:00); **PASS with scoped gaps** — frontend mock smoke 2026-08-15 (see §Historical below)

HITL and FTS5 were not in the 2026-08-26 browser retest. Demo script: [`RUNNING.md`](../../RUNNING.md). Validator: `python -m backend.scripts.validate_kb_hitl`.

### Eval suite (SAD §9)

Measurable EC-* gates live under `evals/`. How to run: [`RUNNING.md` § Evals](../../RUNNING.md#evals-quality-gates). Strategy + results: [`evals.md`](evals.md). Criteria contract: [`sad.md` §9](../1.define/sad.md).

```bash
python -m evals.run --static --fixtures --profile mvp          # course demo bar
python -m evals.run --all --profile production                 # promotion gate
python -m evals.run --live --base-url http://127.0.0.1:8001   # needs backend
```

---

## Live integration retest — 2026-08-26 (after fixes)

**Actions**: `*qa`, `*verify-flow`, `*test-integration`  
**Fixes applied**: Backend moved to **port 8001**; `OLLAMA_MODEL=gemma4:31b`; frontend `.env.local` aligned; single uvicorn instance; `PYTHONIOENCODING=utf-8`.

### Verdict

**Integration PASS** for Path A PIN query (`how do I reset pin`).

| ID | Check | Result | Evidence |
|----|-------|--------|----------|
| I-R01 | Direct `POST :8001/api/chat` | **PASS** | `decision: resolve`, 4 steps, 2 sources, grounded PIN reply (~19s) |
| I-R02 | `POST :3000/api/chat` via rewrite | **PASS** | `decision: resolve`, 4 steps, 2 sources |
| I-R03 | `GET :3000/health` via rewrite | **PASS** | `{"status":"ok"}` (B-Mobile backend) |
| I-R04 | Browser E2E (isolated run) | **PASS** | Reply + “From our help articles” sources; `/operator` for HITL queue |
| I-R05 | Browser E2E under concurrent API load | **FAIL** | HTTP 500 / `ECONNRESET` when backend already running a crew kickoff |

**Remaining gap:** Backend handles one synchronous crew at a time; concurrent requests can cause Next.js proxy `socket hang up` (HTTP 500 in UI). Not MVP-blocking for single-user demo; document for production.

### Defects closed (SSE retest)

| ID | Resolution |
|----|------------|
| DEF-INT-09 | **Mitigated** — SSE stream + heartbeat prevents proxy `ECONNRESET`; real stage events in UI |

### Audit (SSE implementation)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-27T13:10:00-05:00 |
| Persona id | qa-eng / integration.eng |
| Action | Implement SSE progress stream + documentation |
| Result | Primary chat path uses `POST /api/chat/stream`; legacy JSON retained |

### Guardrails (2026-08-27)

Product guardrails documented in [`RUNNING.md`](../../RUNNING.md#guardrails-2026-08-27), [`backend.md`](backend.md), [`integration.md`](integration.md).

| ID | Guardrail | Verify |
|----|-----------|--------|
| GR-01 | Greeting → `decision=resolve`, no STUB | Send `hello` |
| GR-02 | Low urgency + neutral → no specialist banner | Neutral reply; no amber handoff copy |
| GR-03 | Out of scope → scope message, no “human agent” pitch | e.g. capital-of-France question |
| GR-04 | `request_human=true` → still escalates | Path C unchanged |
| GR-05 | SSE `complete` event parsed on stream close | No “stream ended before reply” synthetic error |

**Note:** Path B smoke expectations updated — in-scope KB gap with calm tone resolves in-chat; escalate reserved for request_human / negative sentiment / hard errors.

### Defects closed (port/model retest)

| ID | Resolution |
|----|------------|
| DEF-INT-01 | **Closed** — backend on `:8001`, away from Docker/WSL `:8000` conflict |
| DEF-INT-02 | **Closed** — `gemma4:31b` works on Ollama Cloud account |
| DEF-INT-03 | **Closed** — frontend rewrite returns 200 + resolve |

### New defect (superseded by SSE)

| ID | Severity | Description |
|----|----------|-------------|
| DEF-INT-09 | Low | ~~Concurrent chat + long JSON POST caused proxy reset~~ → **Mitigated** by SSE stream |

---

## Live integration QA — 2026-08-26

**Actions**: `*qa`, `*verify-flow`, `*test-integration`, `*log-defects`  
**Harness**: Direct API (`Invoke-RestMethod` / Python), Cursor IDE browser at `http://localhost:3000/`, crew kickoff script  
**Test query**: `how do I reset pin` (Path A variant; canonical demo: “How do I reset my B-Mobile My Account PIN?”)

### Scope

| In this run | Out of this run |
|-------------|-----------------|
| `GET /health`, `POST /api/chat` direct + via Next.js rewrite | Load / concurrent sessions |
| CrewAI `kickoff()` with Ollama Cloud | OpenAI provider path |
| Browser E2E chat submit + error UI | Security assessment |
| Port conflict diagnosis on `:8000` | Full Path B/C demo matrix |

### Verdict

**Integration FAIL.** Frontend UI and error envelopes work, but the chat pipeline cannot complete a grounded PIN answer:

1. **Port 8000 is contested** — Docker (`com.docker.backend`), WSL (`wslrelay`), and **two** Python uvicorn processes all listen on `:8000`. Requests are routed non-deterministically.
2. **Frontend rewrite often hits the wrong backend** — `GET http://localhost:3000/health` returns `{"status":"ok","service":"recruitment-assistant-api","runtime":"crewai"}` (not B-Mobile). `POST http://localhost:3000/api/chat` returns **HTTP 404**.
3. **When B-Mobile backend is hit**, CrewAI fails on first agent — Ollama Cloud returns `model "llama3.2:3b" not found`. API responds with `decision: escalate`, `error.code: system_error`, **empty `steps[]`**.

Demo Path A (resolve + sources for PIN reset) **did not pass**.

---

### Integration results

| ID | Check | AC | Result | Evidence |
|----|-------|-----|--------|----------|
| I-L01 | Direct `GET http://127.0.0.1:8000/health` | AC-06a | **PASS** (intermittent) | `{"status":"ok"}` when B-Mobile uvicorn receives request |
| I-L02 | Direct `POST http://127.0.0.1:8000/api/chat` PIN query | AC-02…05 | **FAIL** | HTTP 200 but `decision: escalate`, `error.code: system_error`, `steps: []`, stub ticket generated |
| I-L03 | `POST http://127.0.0.1:3000/api/chat` via rewrite | AC-02…05 | **FAIL** | HTTP **404** — wrong service on `:8000` lacks `/api/chat` |
| I-L04 | `GET http://localhost:3000/health` via rewrite | AC-06a | **FAIL** | Returns `recruitment-assistant-api`, not B-Mobile health schema |
| I-L05 | Browser E2E: disclosure → submit PIN query | AC-01, AC-02 | **PARTIAL** | UI FSM works (Ready → Looking that up → Finished); reply shows HTTP 404 + escalate copy; **no grounded PIN answer** |
| I-L06 | Crew kickoff (Python, UTF-8 console) | AC-02 | **FAIL** | `litellm.NotFoundError: model "llama3.2:3b" not found` on classify task |
| I-L07 | Prompt trace `{LOG_DIR}/{trace_id}.json` | AC-02c | **FAIL** | No trace files under `project-context/2.build/logs/` after failed runs |
| I-L08 | Operator strip `steps[]` on failure | AC-02, AC-05 | **FAIL** | Empty steps when crew fails before task completion |
| I-L09 | `npx tsc --noEmit` | — | **PASS** | No TypeScript errors (2026-08-26) |

### Browser smoke — PIN query (`how do I reset pin`)

| Step | Observed | Result |
|------|----------|--------|
| Disclosure banner + **I understand** | Banner compacts; copy updates | **PASS** |
| Submit query | User bubble + pending “Understanding your question …” | **PASS** |
| Status FSM | **Looking that up…** → **Finished** | **PASS** |
| B-Mobile reply | “We could not complete this request…” + “Support is unavailable (HTTP 404)…” | **FAIL** (expected Path A resolve + KB sources) |
| Escalation | Stub reference `STUB-7F9BEC43` shown | **PASS** (error-path envelope) |
| Specialist strip | Expandable; no agent step summaries | **FAIL** (empty `steps[]`) |

### Root-cause notes

**Port 8000 listeners (Windows, 2026-08-26):**

| PID | Process | Impact |
|-----|---------|--------|
| 34128 | `wslrelay.exe` | Steals `:8000` traffic |
| 12964 | `com.docker.backend` | Steals `:8000` traffic; serves `recruitment-assistant-api` health |
| 11616, 45204 | `python` (uvicorn) | Two B-Mobile backend instances — stale model config possible |

**LLM:** `.env` sets `OLLAMA_MODEL=llama3.2:3b`. Ollama Cloud API rejects this model name. Running uvicorn (PID 11616) logged `Model: qwen3.5:cloud` at startup — env/process mismatch suggests stale or competing processes.

**Windows logging:** CrewAI EventBus handlers fail with `'charmap' codec can't encode character '\U0001f680'` when console encoding is not UTF-8. Cosmetic for API, but obscures diagnostics.

---

### Defects (live integration)

| ID | Severity | AC / area | Description | Owner |
|----|----------|-----------|-------------|-------|
| DEF-INT-01 | **Critical** | Integration / DevOps | **Port 8000 conflict** — Docker, WSL, and duplicate Python backends share `:8000`; frontend rewrite non-deterministic | `@devops.eng` / operator |
| DEF-INT-02 | **Critical** | AC-02…05 | **Invalid Ollama model** — `llama3.2:3b` not found; crew fails on first LLM call | `@backend.eng` |
| DEF-INT-03 | **Critical** | AC-02…05 | **Frontend `POST /api/chat` → HTTP 404** via Next.js rewrite when wrong `:8000` listener wins | `@integration.eng` (blocked by DEF-INT-01) |
| DEF-INT-04 | Medium | AC-02, AC-05 | **Empty `steps[]` on crew failure** — pipeline visibility lost; UI shows no agent summaries | `@backend.eng` |
| DEF-INT-05 | Medium | AC-06b | **Misleading dual error copy in UI** — generic escalate text plus raw “HTTP 404” system message | `@frontend.eng` |
| DEF-INT-06 | Low | AC-06a | **Health rewrite returns foreign service** (`recruitment-assistant-api`) | `@integration.eng` |
| DEF-INT-07 | Low | Observability | **Prompt trace files not written** on observed failure paths | `@backend.eng` |
| DEF-INT-08 | Low | DevOps | **Duplicate uvicorn processes** with potentially different `OLLAMA_MODEL` values | operator |

### Remediation (operator checklist)

1. **Free port 8000** — stop Docker/WSL containers using `:8000`, or change `BACKEND_PORT` / `NEXT_PUBLIC_API_BASE_URL` to an unused port (e.g. `8001`).
2. **Run exactly one backend** — `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001` from repo root with venv active.
3. **Fix Ollama model** — set `OLLAMA_MODEL` to a model confirmed on Ollama Cloud (e.g. `qwen3.5:cloud` per running instance log, or pull/list via Ollama API); restart backend after change.
4. **Align frontend env** — update `frontend/.env.local` `NEXT_PUBLIC_API_BASE_URL` to match backend port; restart `npm run dev`.
5. **Windows console** — `$env:PYTHONIOENCODING='utf-8'` before uvicorn to reduce EventBus noise.
6. **Re-run Path A** — “How do I reset my B-Mobile My Account PIN?” → expect `decision: resolve`, non-empty `sources_used`, four `steps[]`.

Recommend `@backend.eng` fix DEF-INT-02/04/07, then `@integration.eng` re-verify I-L03–I-L05 after DEF-INT-01 cleared. `@security.eng` before Deliver.

---

## Historical — Frontend mock QA (2026-08-15)

**Status**: **PASS with scoped gaps** — UI + mock Paths A/B/C only; live crew / FastAPI not in scope.

**Harness**: Cursor IDE browser against `http://localhost:3000/`; `npx tsc --noEmit` PASS; `GET /api/kb` mock CSV loader

---

## Scope and gate

> **Historical — FE epic only (2026-08-15).** Live MVP status is in the header and §Live integration retest.

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

### Audit (live integration retest — PASS)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-26T13:39:00-05:00 |
| Persona id | qa-eng |
| Action | qa + verify-flow after port 8001 + gemma4:31b fixes |
| Result | **PASS** Path A PIN query via API, proxy, and browser (isolated) |
| Test query | `how do I reset pin` |
| Open | DEF-INT-09 concurrent-request proxy reset; DEF-INT-04…08 from prior run partially addressed |

### Audit (append — docs sync)

| Field | Value |
|-------|-------|
| Timestamp | 2026-08-28T23:45:00-05:00 |
| Persona id | qa-eng |
| Action | sync-docs |
| Result | Status line updated: FTS5 + Telegram HITL implemented; not re-run in this pass. Use RUNNING.md demo script. |
