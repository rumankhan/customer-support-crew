# Frontend Epic Log

**Persona**: `@frontend.eng`  
**Action**: `*document-frontend`  
**Status**: MVP chat UI complete (mocks + seed KB; no live `POST /api/chat`)  
**Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset; PRD locks CrewAI)  
**Feature ID**: FE-CRW-001  
**Primary UI**: single route `/`

This file is the single frontend artifact: **behavior contract** (Inputs / Run / Results / History) plus **implementation log** (layout, styling, Integration hooks). Former `frontend-funcional-spec.md` content lives here.

---

## Purpose and scope

Let a B-Mobile customer submit a support question, watch a mocked run complete (`idle → running → done`), and read a grounded reply or handoff in the same chat thread.

**In scope:** chat window + compact composer, run FSM + stub services, specialist strip from last `ChatResponse`, session thread in React state, Spec Sync checklist.

**Out of scope:** live `POST /api/chat` (Integration); streaming tokens; SSO; Voice / CSAT / live ticketing (visible stubs only); persisted run history (SAD Future Work).

### Traceability

| Anchor | Reference |
|--------|-----------|
| PRD §6 Interface Requirements | Chat page `/`, disclosure, status line, chat reply, specialist strip, talk-to-a-person |
| PRD §10.4 Frontend epic | UI only; mocks; no live BE; Tailwind + Next.js App Router + TypeScript |
| PRD AC-01…AC-06 | Disclosure, resolve/escalate UX, operator fields, failure CTA |
| SAD §2 Frontend logical structure | `app/page.tsx`, components, `lib/types.ts`, `lib/api.ts` mocks |
| SAD ADR-03 / ADR-14 / ADR-15 | Next.js + Tailwind + TS; last result in UI state; optimistic local stages (no SSE) |
| SAD Future Work | DB/history, streaming UI, voice, CSAT dashboard, live ticketing |

---

## What was built

Single-route Next.js App Router app at `frontend/` for **B-Mobile** customer help (fictional carrier). Page order on `/`:

1. Header (B-Mobile Support Crew / How can we help?)
2. AI disclosure (`DisclosureBanner`)
3. Chat window (`ChatWindow` + compact `InputsForm`)
4. Status (`RunStatus`)
5. For specialists (`SpecialistStrip`)
6. Coming later stubs (`FutureWorkStubs`)

| Region | Implementation |
|--------|----------------|
| Chat | `components/ChatWindow.tsx` — You (right, accent) / B-Mobile (left) bubbles; composer at bottom; auto-scroll |
| Composer | `components/InputsForm.tsx` (`compact`) — question, **I'd rather talk to a person**, **Get help**, **Start new conversation** when the thread is not empty |
| Status | `components/RunStatus.tsx` — Ready / Looking that up / Finished / Couldn't finish (`CrewStatusMark`) |
| For specialists | `components/SpecialistStrip.tsx` — last `ChatResponse`: `decision`, `reason_codes`, expandable `steps[]`, `trace_id`, packet |
| Session thread | In-memory `history[]` rendered as chat turns. **Start new conversation** clears the thread (`RESET` → idle) |
| Disclosure | `components/DisclosureBanner.tsx` — amber notice until **I understand**; compact persistent notice after (`AC-01`) |
| Future Work | `components/FutureWorkStubs.tsx` — Voice, CSAT dashboard, Live ticketing (non-functional) |

Stub services (no live backend):

- `startRun` / `getRunStatus` in `lib/services/runService.ts` (~1.8s in-memory latency)
- Re-exported from `lib/api.ts` (Integration hook point)
- Dummy retrieval: `lib/kb.ts` + mock `GET /api/kb` reads `backend/kb/articles.csv` (keyword overlap floor **0.35**)
- Mock `ChatResponse` in `lib/mockResponse.ts` for demo paths A/B/C and timeout envelope

Also included because PRD/SAD require them for the FE epic:

- Optimistic local stage labels (Understanding your question → Searching help articles → Writing a reply → Checking next steps) — **no SSE / WebSocket**
- Client abort **55s** with `error.code = llm_or_timeout` and escalate CTA (`AC-06b` shape)

---

## Stack and visual direction

| Item | Choice |
|------|--------|
| Framework | Next.js **15** App Router, React **19**, TypeScript |
| Styling | Tailwind CSS **3**; `color-scheme: light` in `app/globals.css` |
| Theme | Light canvas `#f6f4ef`, ink `#1c1917`, muted stone, accent `#1d4ed8` (`tailwind.config.ts`) |
| Fonts | Source Sans 3 (body) + Source Serif 4 (display) via `next/font` (`app/layout.tsx`) |
| State | Local React only (`useResearchWorkflow`); no Redux |
| Port | **3000** (`npm run dev` in `frontend/`) |
| Node | `>=20` (`package.json` engines) |

`aamad.config.example.yml` UI theme `system` yields to PRD/SAD **light** theme for MVP.

Responsive: `max-w-3xl` column, wrapping composer actions, usable at ~375px and 1280px. Accessibility: Enter submits (Shift+Enter newline), `role="status"` / `aria-live` on Status, `role="alert"` on validation and envelope errors, `:focus-visible` outline.

---

## SAD layout mapping

| SAD path | This epic |
|----------|-----------|
| `app/page.tsx` | Disclosure, ChatWindow, RunStatus, SpecialistStrip, FutureWorkStubs |
| `app/layout.tsx` | Title **B-Mobile Support**, fonts, canvas body |
| `app/api/kb/route.ts` | Mock-only read of `backend/kb/articles.csv` |
| `components/ChatWindow.tsx` | Transcript + pending bubble + composer |
| `components/InputsForm.tsx` | Query, talk-to-person, Get help, Start new conversation |
| `components/RunStatus.tsx` | Status pill + stage label + last updated + run id |
| `components/CrewStatusMark.tsx` | Status pill |
| `components/SpecialistStrip.tsx` | AC-05 operator strip |
| `components/DisclosureBanner.tsx` | AC-01 |
| `components/FutureWorkStubs.tsx` | Voice / CSAT / Live ticketing |
| `lib/types.ts` | `ChatRequest` / `ChatResponse` aligned to SAD §2 (incl. `meta` for AC-01b) |
| `lib/fsm.ts` | `idle → running → done`; `STAGE_LABELS` |
| `lib/useResearchWorkflow.ts` | Orchestrates stub run, poll, stages, abort, history |
| `lib/api.ts` | Stub re-exports; Integration replaces with `fetch` |
| `lib/services/runService.ts` | In-memory `startRun` / `getRunStatus` |
| `lib/mockResponse.ts` | Path A/B/C + timeout mocks |
| `lib/kb.ts` | CSV parse + `searchKb()` |
| `lib/uiCopy.ts` | Customer-facing labels |
| `lib/crewStatus.ts` | Display status overlay (`error` is not an FSM state) |

**Leftover files (not mounted on `/`)**: `components/HistoryList.tsx`, `components/ResultsPanel.tsx`. `useResearchWorkflow` still exports unused `showHistory`. Safe for Integration to ignore; SAD DB/history remains Future Work.

---

## Inputs

Single composer inside `ChatWindow` on `/`. Submit is enabled whenever the FSM is not `running` (`idle` or `done`).

| Input | Type / format | Source | Required | Validation |
|-------|---------------|--------|----------|------------|
| `query` | string → `ChatRequest.message` | Chat composer | Yes | Trimmed non-empty; max **4000** chars (SAD) |
| `requestHuman` | boolean → `ChatRequest.request_human` | **I'd rather talk to a person** | No | Default `false` |
| `disclosureAcknowledged` | boolean → `ChatRequest.disclosure_acknowledged` | **I understand** | No | Default `false`; missing/`false` does **not** block submit (AC-01b) |
| `sessionId` | optional opaque string | Generated in-session if needed | No | Not shown; not persisted |

**UI rules**

- AI disclosure is visible until acknowledged (AC-01). Acknowledge-to-dismiss is allowed; a compact notice remains.
- Keyboard: Enter in the query field submits when valid and phase is not `running` (Shift+Enter newline).
- While `running`, composer is disabled (no second concurrent run).
- Empty or >4000-character query: client-side error (“Please type a question so we can help.” / length copy); FSM stays `idle`; no stub call.

---

## Run

Lightweight client FSM in `lib/fsm.ts`. No Redux. No streaming protocol.

```
idle → running → done
```

| State | Meaning | UI |
|-------|---------|----|
| `idle` | No active run | Composer enabled; chat shows prior turns or empty prompt |
| `running` | Stub run in flight | Composer disabled; Status **Looking that up**; local stage labels (ADR-15); pending B-Mobile bubble; first label within 10s of send |
| `done` | Stub returned a result | Composer enabled for another turn; B-Mobile bubble + specialist strip update. **Start new conversation** (when the thread is not empty) runs `RESET` and **clears** the thread |

| From | Event | To | Trigger |
|------|-------|----|---------|
| `idle` | `START` | `running` | Valid **Get help** → `startRun()` succeeds |
| `running` | `COMPLETE` | `done` | `getRunStatus()` returns `status: "done"` |
| `done` | `RESET` | `idle` | **Start new conversation** (clears thread + specialist strip) |
| `done` | `START` | `running` | Follow-up question without reset (allowed) |
| `running` | `RESET` | `idle` | Start new conversation while a stub is in flight (timers cleared) |

Illegal transitions are no-ops. Poll interval **400ms**; stage tick **900ms**; first stage label is immediate on START.

### Stub services (FE epic — no live backend)

| Function | Input | Output | Behavior |
|----------|-------|--------|----------|
| `startRun` | `{ query, requestHuman, disclosureAcknowledged }` | `{ runId: string }` | In-memory stub; does **not** call `POST /api/chat` |
| `getRunStatus` | `{ runId }` | `{ status: "running" \| "done", result?: ChatResponse }` | Poll while FSM is `running`; completes with a mock `ChatResponse` after ~1.8s |

**Client timeout:** abort wait at **55s** (SAD 50–60s). On abort, still transition `running → done` with an error-shaped `ChatResponse` (`error.code = llm_or_timeout`) and talk-to-a-person CTA. Do not invent an answer.

**Hook point for Integration:** replace stub bodies in `lib/api.ts` / `lib/services/runService.ts` with `fetch(NEXT_PUBLIC_API_BASE_URL + "/api/chat")`. Do not add that call in this epic.

---

## Results

Rendered on the same route. Customer-facing content lives in chat bubbles. The specialist strip binds to the **last `ChatResponse` in UI state** (ADR-14). Do not call `/api/last-result`.

| Region | Fields | Notes |
|--------|--------|-------|
| B-Mobile bubble | `reply`, `sources_used[]`, escalate notice | Sources on resolve; escalate copy when `decision=escalate` or `error != null` |
| Pending bubble | Current stage label | Shown while `running` next to the sent You bubble |
| I'd rather talk to a person | Checkbox | Always visible; sets `request_human` for the **next** send. Escalate notice in chat is informational / Future live-chat |
| For specialists | `decision`, `reason_codes[]`, expandable `steps[]`, `trace_id` | From last response only; Outcome shows Answered / Sent to a specialist plus the contract `decision` |
| Packet | `packet`, `stub_ticket_id` | Shown in the strip when escalate; `null` on resolve |

**Demo path expectations (mocked)**

| Path | Typical query | Mock `decision` |
|------|---------------|-----------------|
| A | in-KB FAQ (e.g. My Account PIN) | `resolve` + sources |
| B | unknown topic (e.g. quantum warranty) | `escalate` + packet + stub ticket |
| C | `requestHuman=true` | `escalate`, `reason_codes` include `request_human` |

`selectMockResponse`: `requestHuman` → Path C; else `searchKb` hit → Path A; else Path B (`retrieval_gap`, `refused`) with packet.

---

## History

SAD lists **DB/history** as Future Work. This epic implements a **session-only chat thread** in React state (`history[]` rendered in `ChatWindow`). There is no separate History list and no click-to-restore of a past run. State stores newest first; ChatWindow reverses for chronological display.

| Behavior | MVP (this epic) | Future Work |
|----------|-----------------|-------------|
| Storage | In-memory turns for the browser tab | Persistent DB |
| Append | Each `done` run adds a You + B-Mobile pair | Server-side run log |
| Start new conversation | Clears thread, specialist strip, FSM → idle | Archive / new ticket |
| Survive refresh | No | Yes |
| Cross-tab | No | Optional |

Follow-up questions append to the same thread unless the customer starts a new conversation.

---

## Mock vs Integration hook points

| Call | FE epic (now) | Integration epic |
|------|----------------|------------------|
| Get help | `startRun()` in-memory stub | `POST ${NEXT_PUBLIC_API_BASE_URL}/api/chat` |
| Poll / wait | `getRunStatus()` stub (~1.8s) | Single non-streaming JSON; no poll required if request awaits kickoff |
| Last result | UI state (ADR-14) | Same; do not require `/api/last-result` |
| Timeout | Client abort **55s** | Keep; API soft timeout 45s |
| KB | `GET /api/kb` + `searchKb()` | Stop using mock KB for answers; crew `kb_search` |

Do **not** set `NEXT_PUBLIC_API_BASE_URL` usage in this epic. Mock `GET /api/kb` only reads the seed CSV; it is **not** a product API.

---

## StatusLine contract (ADR-15)

On `START`, a client timer cycles stage labels. First label is immediate (**Understanding your question**). On `COMPLETE` or error, animation stops; authoritative `steps[]` from the mock `ChatResponse` are in **For specialists**. While running, the chat also shows a B-Mobile pending bubble with the same stage label. No streaming protocol.

---

## PRD acceptance mapping (UI-only)

| AC | Frontend behavior |
|----|-------------------|
| AC-01 | Disclosure visible on first paint; copy states AI assistant |
| AC-01a | **I'd rather talk to a person** in composer |
| AC-01b | Mock `meta.ai_disclosure=true`; echoes `disclosure_acknowledged` |
| AC-02b | Mock `steps[]` (four agent summaries) in specialist strip |
| AC-03a | Path A: `sources_used` in B-Mobile bubble |
| AC-03b | Path B: escalate, no fabricated policy |
| AC-04a | Packet JSON in strip on escalate |
| AC-04b | Checkbox forces Path C |
| AC-05a | Strip bound to last `ChatResponse` in UI state |
| AC-06b | Timeout/unknown-run envelopes: safe reply + escalate; live `GET /health` is Backend/Integration |

---

## How to run

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Try:

- Path A: `How do I reset my B-Mobile My Account PIN?` → **Get help** (person unchecked) → resolve + sources in a B-Mobile bubble
- Path B: `What is your quantum warranty for the hardware drone?` → escalate + packet
- Path C: check **I'd rather talk to a person** → escalate with `request_human`
- **Start new conversation** (next to Get help, after a thread exists) → empty chat, Status **Ready**

---

## Spec Sync checklist

Update this table **after every commit** that touches `frontend/` or this file. Tick the boxes that remain true; add a row with commit SHA; append an Audit line.

### After-commit checks

- [ ] **Inputs** — composer fields and validation still match the Inputs table
- [ ] **Run** — FSM is still `idle → running → done`; `startRun` / `getRunStatus` still stubs (or Integration has updated this file)
- [ ] **Results** — chat reply + specialist strip still bind last `ChatResponse` in UI state
- [ ] **History** — session thread only; **Start new conversation** clears the tab unless SAD/PRD changed
- [ ] **Audit** — appended for the same change
- [ ] **No live backend** — no `fetch` to `/api/chat` unless Integration epic owns the commit
- [ ] **Placeholders** — Voice / CSAT / Live ticketing remain non-functional

### Commit log

| Date | Commit SHA | Spec sections touched | Boxes re-checked | Notes |
|------|------------|-----------------------|------------------|-------|
| 2026-08-14 | *(uncommitted — initial FE slice)* | Inputs, Run, Results, History | All drafted | Initial Critical Research Workflow |
| 2026-08-15 | *(uncommitted — chat window)* | Inputs, Run, Results, History | Re-checked | Chat bubbles; Start new conversation clears thread |
| 2026-08-15 | *(uncommitted — fold spec)* | Whole file | Re-checked | Merged former `frontend-funcional-spec.md` into this artifact |

---

## Sources

- `project-context/1.define/prd.md` (§6 Interface Requirements, §10.4 Frontend epic, AC-01…06)
- `project-context/1.define/sad.md` (§2 Frontend logical structure, ADR-03/14/15)
- `.cursor/agents/frontend-eng.md`
- `.cursor/templates/sfs-template.md` (Inputs / Run / Results / History taxonomy)
- Operator request: chat window (bubbles) + specialist strip; stub contracts unchanged

## Assumptions

- `setup.md` is missing; this epic scaffolded Next.js to match SAD + existing `frontend/package-lock.json`.
- Chat bubbles on `/` satisfy SAD “Web chat UI (`/`)”. Stub I/O (`ChatRequest` / `ChatResponse`) unchanged.
- Session thread is in-memory; SAD “DB/history” remains Future Work. **Start new conversation** clears the tab thread only.
- `aamad.config.yml` is absent; example config theme `system` does not override PRD light theme.
- CrewAI runtime is UI-visible only as mocked four-step `steps[]` and non-streaming wait (ADR-05); no live kickoff.

## Open Questions

1. Persist the session thread in `localStorage` for demos, or keep tab-session only (current)?
2. Final AI disclosure copy owner (PRD Open Question).
3. Remove unused `HistoryList.tsx` / `ResultsPanel.tsx` / `showHistory` in a cleanup commit?

## Audit

- **Timestamp**: 2026-08-14T23:10:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe`
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — UI-only mocks; no crew prompts rendered
- **Notes**: Created Next.js single-route app, FSM, stub `startRun`/`getRunStatus`, Spec Sync checklist (originally a separate functional spec)

### Audit (append)

- **Timestamp**: 2026-08-15T11:05:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` (B-Mobile copy + dummy KB retrieval)
- **Resolved runtime**: `crewai`
- **Prompt Trace**: omitted — stub retrieval, no crew prompts

### Audit (append)

- **Timestamp**: 2026-08-15T11:55:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` (seed KB → `backend/kb/articles.csv`)
- **Resolved runtime**: `crewai`
- **Prompt Trace**: omitted

### Audit (append)

- **Timestamp**: 2026-08-15T12:08:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` (customer-facing copy: Ask / Get help / Answer)

### Audit (append)

- **Timestamp**: 2026-08-15T17:25:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` (chat window, Start new conversation, Status under chat, specialist strip)

### Audit (append)

- **Timestamp**: 2026-08-15T17:30:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `document-frontend`
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — documentation of existing UI mocks; no crew prompts rendered
- **Notes**: Implementation log rewritten to match mounted `/` layout, stub contracts, StatusLine, AC mapping, and Integration hook points

### Audit (append)

- **Timestamp**: 2026-08-15T17:40:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `document-frontend`
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted
- **Notes**: Folded `frontend-funcional-spec.md` into this file and deleted the extra spec so `@frontend.eng` has one output artifact
