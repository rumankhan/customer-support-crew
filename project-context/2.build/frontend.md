# Frontend Epic Log

**Persona**: `@frontend.eng`  
**Action**: `*document-frontend`  
**Status**: MVP chat UI complete (mocks + seed KB; single `postChat` → JSON `ChatResponse`; no live `POST /api/chat`)  
**Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset; PRD locks CrewAI)  
**Feature ID**: FE-CRW-001  
**Primary UI**: single route `/`

This file is the single frontend artifact: **behavior contract** (Inputs / Run / Results / History) plus **implementation log** (layout, styling, Integration hooks). Former `frontend-funcional-spec.md` content lives here — **do not split** into a second markdown file.

---

## Purpose and scope

Let a B-Mobile customer submit a support question, watch a mocked run complete (`idle → running → done`), and read a grounded reply or handoff in the same chat thread.

**In scope:** chat window + compact composer, run FSM + stub `postChat`, specialist strip from last `ChatResponse`, session thread in React state, Spec Sync checklist.

**Out of scope:** live `POST /api/chat` (Integration); streaming tokens; SSO; Voice / CSAT / live ticketing (visible stubs only); persisted run history / localStorage (SAD Future Work).

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
| For specialists | `components/SpecialistStrip.tsx` — last `ChatResponse`: `decision`, `reason_codes`, expandable `steps[]` (opens on COMPLETE), `trace_id`, packet |
| Session thread | In-memory `history[]` rendered as chat turns. **Start new conversation** clears the thread (`RESET` → idle) |
| Disclosure | `components/DisclosureBanner.tsx` — amber notice until **I understand**; compact persistent notice after (`AC-01`) |
| Future Work | `components/FutureWorkStubs.tsx` — Voice, CSAT dashboard, Live ticketing (non-functional) |

Stub services (no live backend):

- `postChat(ChatRequest)` in `lib/api.ts` → `mockPostChat` in `lib/services/runService.ts` (~1.8s latency, one JSON `ChatResponse`)
- Dummy retrieval for **demo Path A/B only**: `lib/kb.ts` + mock `GET /api/kb` reads `backend/kb/articles.csv` (keyword overlap floor **0.35**)
- Mock `ChatResponse` in `lib/mockResponse.ts` for demo paths A/B/C and timeout envelope

Also included because PRD/SAD require them for the FE epic:

- Optimistic local stage labels (Understanding your question → Searching help articles → Writing a reply → Checking next steps) — **no SSE / WebSocket**
- On COMPLETE: **stop the local stage timer** and snap StatusLine / strip to authoritative `steps[]` (ADR-15) — pending bubble is **not** shown after decision is on screen
- Client abort **55s** with `error.code = llm_or_timeout` and escalate CTA when `error != null` (`AC-06b`)

**Cleanup:** unused `HistoryList.tsx` / `ResultsPanel.tsx` / `showHistory` removed (were never mounted). No localStorage history.

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

**Theme vs config:** `aamad.config.example.yml` UI theme `system` yields to PRD/SAD **light** theme for MVP. Documented intentional override — do not switch the app to `prefers-color-scheme` unless PRD/SAD change.

Responsive: `max-w-3xl` column, wrapping composer actions, usable at ~375px and 1280px. Accessibility: Enter submits (Shift+Enter newline), `role="status"` / `aria-live` on Status, `role="alert"` on validation and envelope errors, `:focus-visible` outline.

---

## SAD ChatRequest / ChatResponse envelope

Canonical TypeScript (also in `frontend/lib/types.ts`). `@backend.eng` / `@integration.eng`: use this shape — do not hunt for a second copy.

```typescript
export type SourceRef = {
  title: string;
  snippet: string;
};

export type StepSummary = {
  agent: string;
  summary: string;
};

export type EscalationPacket = {
  intent: string;
  urgency: string;
  customer_message: string;
  request_human: boolean;
  citations_attempted: SourceRef[];
  draft_reply: string;
  sentiment: "positive" | "neutral" | "negative";
  risk: "low" | "medium" | "high";
  reason_codes: string[];
  stub_ticket_id: string;
};

export type ChatError = {
  code: "llm_or_timeout" | "validation_error" | "kb_unavailable" | "system_error";
  message: string;
};

export type ChatRequest = {
  message: string;
  request_human: boolean;
  session_id?: string;
  disclosure_acknowledged?: boolean;
};

export type ChatResponse = {
  decision: "resolve" | "escalate";
  reply: string;
  sources_used: SourceRef[];
  sentiment: "positive" | "neutral" | "negative";
  risk: "low" | "medium" | "high";
  reason_codes: string[];
  steps: StepSummary[];
  trace_id: string;
  packet: EscalationPacket | null;
  stub_ticket_id: string | null;
  meta: {
    ai_disclosure: true;
    disclosure_acknowledged: boolean;
  };
  error: ChatError | null;
};
```

**Field mapping (composer → request → UI)**

| UI | `ChatRequest` / `ChatResponse` | Notes |
|----|-------------------------------|-------|
| Composer text | `message` | Trimmed; max 4000 |
| I'd rather talk to a person | `request_human` | Path C when `true` |
| I understand | `disclosure_acknowledged` | Optional; does not block send |
| B-Mobile bubble | `reply`, `sources_used[]` | Sources on resolve |
| Escalate notice + CTA | `decision === "escalate"` **or** `error != null` | CTA checks talk-to-person for next send |
| For specialists | `decision`, `reason_codes`, `steps[]`, `trace_id`, `packet`, `stub_ticket_id` | ADR-14 last result in UI state |

**Short JSON example (resolve)**

```json
{
  "decision": "resolve",
  "reply": "…",
  "sources_used": [{ "title": "Reset My Account PIN", "snippet": "…" }],
  "sentiment": "neutral",
  "risk": "low",
  "reason_codes": ["grounded_kb_hit"],
  "steps": [
    { "agent": "query_classifier", "summary": "…" },
    { "agent": "knowledge_retriever", "summary": "…" },
    { "agent": "response_specialist", "summary": "…" },
    { "agent": "escalation_manager", "summary": "…" }
  ],
  "trace_id": "trace-…",
  "packet": null,
  "stub_ticket_id": null,
  "meta": { "ai_disclosure": true, "disclosure_acknowledged": true },
  "error": null
}
```

**`error != null` → escalate CTA:** bubble shows safe reply + error message + **I'd rather talk to a person** control that sets `request_human` for the next send (AC-06b).

---

## SAD layout mapping

| SAD path | This epic |
|----------|-----------|
| `app/page.tsx` | Disclosure, ChatWindow, RunStatus, SpecialistStrip, FutureWorkStubs |
| `app/layout.tsx` | Title **B-Mobile Support**, fonts, canvas body |
| `app/api/kb/route.ts` | Mock-only read of `backend/kb/articles.csv` (demo Path A/B — **not** product chat) |
| `components/ChatWindow.tsx` | Transcript + pending bubble + composer |
| `components/InputsForm.tsx` | Query, talk-to-person, Get help, Start new conversation |
| `components/RunStatus.tsx` | Status pill + stage label + last updated + run id |
| `components/CrewStatusMark.tsx` | Status pill |
| `components/SpecialistStrip.tsx` | AC-05 operator strip; `steps[]` open on COMPLETE |
| `components/DisclosureBanner.tsx` | AC-01 |
| `components/FutureWorkStubs.tsx` | Voice / CSAT / Live ticketing |
| `lib/types.ts` | `ChatRequest` / `ChatResponse` (pasted above) |
| `lib/fsm.ts` | `idle → running → done`; `STAGE_LABELS` |
| `lib/useResearchWorkflow.ts` | One `postChat` await; optimistic stages; abort; history |
| `lib/api.ts` | `postChat` → mock; Integration replaces with live `fetch` |
| `lib/services/runService.ts` | `mockPostChat` (~1.8s) |
| `lib/mockResponse.ts` | Path A/B/C + timeout mocks |
| `lib/kb.ts` | CSV parse + `searchKb()` (**FE demo only**) |
| `lib/uiCopy.ts` | Customer-facing labels |
| `lib/crewStatus.ts` | Display status overlay (`error` is not an FSM state) |

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
- Empty or >4000-character query: client-side error; FSM stays `idle`; no stub call.

---

## Run

Lightweight client FSM in `lib/fsm.ts`. No Redux. No streaming protocol. **No poller.**

```
idle → running → done
```

| State | Meaning | UI |
|-------|---------|----|
| `idle` | No active run | Composer enabled; chat shows prior turns or empty prompt |
| `running` | Stub `postChat` in flight | Composer disabled; Status **Looking that up**; local stage labels (ADR-15); pending B-Mobile bubble; first label within 10s of send |
| `done` | One JSON `ChatResponse` returned | Composer enabled; pending bubble **gone**; B-Mobile bubble + specialist strip with authoritative `steps[]` |

| From | Event | To | Trigger |
|------|-------|----|---------|
| `idle` | `START` | `running` | Valid **Get help** → `postChat()` starts |
| `running` | `COMPLETE` | `done` | `postChat` resolves (or abort timeout envelope) |
| `done` | `RESET` | `idle` | **Start new conversation** (clears thread + specialist strip) |
| `done` | `START` | `running` | Follow-up question without reset (allowed) |
| `running` | `RESET` | `idle` | Start new conversation while in flight (abort + ignore late result) |

Illegal transitions are no-ops. Stage tick **900ms**; first stage label is immediate on START. On COMPLETE, stage timer **stops** and StatusLine snaps from `steps[]` length.

### Stub service (FE epic — no live backend)

| Function | Input | Output | Behavior |
|----------|-------|--------|----------|
| `postChat` | `ChatRequest` (+ optional `AbortSignal`) | `ChatResponse` | Mock latency ~1.8s; Path A/B/C via `selectMockResponse` + seed CSV; does **not** call live `POST /api/chat` |

**Client timeout:** abort wait at **55s** (SAD 50–60s). On abort, still transition `running → done` with an error-shaped `ChatResponse` (`error.code = llm_or_timeout`) and talk-to-a-person CTA. Do not invent an answer.

**Hook point for Integration:** replace `mockPostChat` behind `lib/api.ts` `postChat` with:

`fetch(`${NEXT_PUBLIC_API_BASE_URL}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal })`

Do **not** reintroduce `startRun` / `getRunStatus` polling. Do **not** use `searchKb()` / `GET /api/kb` for live answers — crew `kb_search` owns retrieval.

---

## Results

Rendered on the same route. Customer-facing content lives in chat bubbles. The specialist strip binds to the **last `ChatResponse` in UI state** (ADR-14). Do not call `/api/last-result`.

| Region | Fields | Notes |
|--------|--------|-------|
| B-Mobile bubble | `reply`, `sources_used[]`, escalate notice | Sources on resolve; escalate copy when `decision=escalate` or `error != null` |
| Pending bubble | Current stage label | **Only** while `phase === "running"` |
| I'd rather talk to a person | Checkbox + error CTA | Sets `request_human` for the **next** send |
| For specialists | `decision`, `reason_codes[]`, `steps[]`, `trace_id` | Opens `steps[]` when JSON lands |
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

SAD lists **DB/history** as Future Work. This epic implements a **session-only chat thread** in React state. **No localStorage.** No separate History list.

| Behavior | MVP (this epic) | Future Work |
|----------|-----------------|-------------|
| Storage | In-memory turns for the browser tab | Persistent DB |
| Append | Each `done` run adds a You + B-Mobile pair | Server-side run log |
| Start new conversation | Clears thread, specialist strip, FSM → idle | Archive / new ticket |
| Survive refresh | No | Yes |
| Cross-tab | No | Optional |

---

## Mock vs Integration hook points

| Call | FE epic (now) | Integration epic (**must**) |
|------|----------------|------------------------------|
| Get help | `postChat()` mock (~1.8s) | `POST ${NEXT_PUBLIC_API_BASE_URL}/api/chat` → one JSON body |
| Poll / wait | **Removed** | Do **not** add a poller |
| Last result | UI state (ADR-14) | Same; do not require `/api/last-result` |
| Timeout | Client abort **55s** | Keep; API soft timeout 45s |
| KB | `GET /api/kb` + `searchKb()` for **demo Path A/B only** | Drop client KB for answers; crew `kb_search` |

Do **not** set `NEXT_PUBLIC_API_BASE_URL` usage in this epic. Mock `GET /api/kb` only reads the seed CSV; it is **not** a product API. If Integration leaves the poller or client KB in the live path, the UI will resolve FAQs the crew never saw.

---

## StatusLine contract (ADR-15)

On `START`, a client timer cycles stage labels. First label is immediate (**Understanding your question**). On `COMPLETE` or error: **stop the timer**; snap label from authoritative `steps[]`; show those steps in **For specialists**; pending **Writing a reply** bubble is cleared because `phase !== "running"`. No streaming protocol.

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
| AC-06b | Timeout/error envelopes: safe reply + escalate CTA; live `GET /health` is Backend/Integration |

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

### Verification (this pass)

| Check | Result |
|-------|--------|
| `npm run build` (in `frontend/`) | **PASS** — Next.js 15.5.23, compiled, types OK, exit 0 (2026-08-20) |
| Unit / integration test script | **None** in `frontend/package.json` (only `dev` / `build` / `start` / `lint`) |
| Manual Path A/B/C | Still mock via `articles.csv` + `request_human` |

---

## Spec Sync checklist

Update this table **after every commit** that touches `frontend/` or this file. Tick the boxes that remain true; add a row with commit SHA; append an Audit line.

### After-commit checks

- [x] **Inputs** — composer fields and validation still match the Inputs table
- [x] **Run** — FSM is still `idle → running → done`; single `postChat` mock (no poller)
- [x] **Results** — chat reply + specialist strip still bind last `ChatResponse` in UI state; `error != null` → escalate CTA
- [x] **History** — session thread only (no localStorage); **Start new conversation** clears the tab
- [x] **Audit** — appended for the same change
- [x] **No live backend** — no `fetch` to `/api/chat` (FE epic still owns mocks)
- [x] **Placeholders** — Voice / CSAT / Live ticketing remain non-functional
- [x] **Envelope** — `ChatRequest` / `ChatResponse` pasted in this file
- [x] **ADR-15** — stage timer stops on COMPLETE; authoritative `steps[]` shown; no stuck “Writing a reply”

### Commit log

| Date | Commit SHA | Spec sections touched | Boxes re-checked | Notes |
|------|------------|-----------------------|------------------|-------|
| 2026-08-14 | *(uncommitted — initial FE slice)* | Inputs, Run, Results, History | All drafted | Initial Critical Research Workflow |
| 2026-08-15 | *(uncommitted — chat window)* | Inputs, Run, Results, History | Re-checked | Chat bubbles; Start new conversation clears thread |
| 2026-08-15 | *(uncommitted — fold spec)* | Whole file | Re-checked | Merged former `frontend-funcional-spec.md` into this artifact |
| 2026-08-20 | *(filled after commit)* | Run, Results, Envelope, Spec Sync, Cleanup | All above | Single `postChat`; drop poller; ADR-15 snap; envelope paste; cleanup; `npm run build` PASS |

---

## Sources

- `project-context/1.define/prd.md` (§6 Interface Requirements, §10.4 Frontend epic, AC-01…06)
- `project-context/1.define/sad.md` (§2 Frontend logical structure, ADR-03/14/15, ChatRequest/ChatResponse)
- `.cursor/agents/frontend-eng.md`
- `.cursor/templates/sfs-template.md` (Inputs / Run / Results / History taxonomy)
- Operator review: one file; drop poller/client KB for Integration; ADR-15 snap; paste envelope; cleanup leftovers

## Assumptions

- `setup.md` is missing; this epic scaffolded Next.js to match SAD + existing `frontend/package-lock.json`.
- Chat bubbles on `/` satisfy SAD “Web chat UI (`/`)”. Stub I/O (`ChatRequest` / `ChatResponse`) unchanged.
- Session thread is in-memory only; **no localStorage**; SAD “DB/history” remains Future Work.
- Light theme overrides example config `system` theme (documented above).
- CrewAI runtime is UI-visible only as mocked four-step `steps[]` and non-streaming wait (ADR-05); no live kickoff.
- These review fixes were applied in the **B-Mobile `AAMAD/agentic-ai`** tree (not the learning-platform NoorLearn mock).

## Open Questions

1. Final AI disclosure copy owner (PRD Open Question).
2. When Integration lands, should mock `GET /api/kb` be deleted entirely or kept behind a `USE_MOCK_KB` flag for offline demos?

## Audit

- **Timestamp**: 2026-08-14T23:10:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe`
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — UI-only mocks; no crew prompts rendered
- **Notes**: Created Next.js single-route app, FSM, stub services, Spec Sync checklist (originally a separate functional spec)

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

### Audit (append)

- **Timestamp**: 2026-08-20T12:35:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` + `document-frontend`
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — UI mocks only
- **Notes**: Replaced startRun/poll with single `postChat`; ADR-15 stop timer + snap `steps[]`; pasted ChatRequest/ChatResponse envelope; escalate CTA on `error != null`; dropped leftover History/Results; skipped localStorage; documented light theme; `npm run build` PASS; no second spec file
