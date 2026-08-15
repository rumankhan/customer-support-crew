# Frontend Functional Spec: Critical Research Workflow

**Feature ID**: FE-CRW-001  
**Primary UI**: single route `/` (chat window + Status + For specialists)  
**Selected Runtime**: `crewai` (UI mocks only; no live API in this epic)  
**Owning persona**: `@frontend.eng`

This spec defines the **Critical Research Workflow** for **B-Mobile** (fictional consumer mobile carrier): the customer submits a support question from the chat composer, a mocked multi-agent cycle retrieves dummy help articles (or escalates), and the UI shows a grounded reply in a B-Mobile bubble or a handoff notice. Persistent transcripts, live `POST /api/chat`, and a database-backed history are out of this epic.

---

## Purpose and Scope

- **Purpose**: Let a B-Mobile customer submit a support question, watch a run complete (`idle → running → done`), and read the reply in the same chat thread.
- **In Scope**: Chat window + compact composer, run FSM + stub services, specialist strip from last `ChatResponse`, session thread in React state, Spec Sync checklist.
- **Out of Scope**: Live backend wiring (Integration epic); streaming tokens; SSO; Voice / CSAT / live ticketing (visible stubs only); persisted run history (SAD Future Work).

---

## Traceability

| Anchor | Reference |
|--------|-----------|
| PRD §6 Interface Requirements | Chat page `/`, disclosure, status line, chat reply, specialist strip, talk-to-a-person |
| PRD §10.4 Frontend epic | UI only; mocks; no live BE; Tailwind + Next.js App Router + TypeScript |
| PRD AC-01…AC-06 | Disclosure, resolve/escalate UX, operator fields, failure CTA |
| SAD §2 Frontend logical structure | `app/page.tsx`, components, `lib/types.ts`, `lib/api.ts` mocks |
| SAD ADR-03 / ADR-14 / ADR-15 | Next.js + Tailwind + TS; last result in UI state; optimistic local stages (no SSE) |
| SAD Future Work | DB/history, streaming UI, voice, CSAT dashboard, live ticketing |

---

## Inputs

Single composer inside `ChatWindow` on `/`. Submit is enabled whenever the FSM is not `running` (`idle` or `done`).

| Input | Type / format | Source | Required | Validation |
|-------|---------------|--------|----------|------------|
| `query` | string, mapped to `ChatRequest.message` | Chat composer | Yes | Trimmed non-empty; max **4000** chars (SAD) |
| `requestHuman` | boolean, mapped to `ChatRequest.request_human` | “I'd rather talk to a person” checkbox | No | Default `false` |
| `disclosureAcknowledged` | boolean, mapped to `ChatRequest.disclosure_acknowledged` | AI disclosure control | No | Default `false`; missing/`false` does **not** block submit (AC-01b) |
| `sessionId` | optional opaque string | Generated in-session if needed | No | Not shown; not persisted |

**UI rules**

- AI disclosure is visible until acknowledged (AC-01). Acknowledge-to-dismiss is allowed.
- Keyboard: Enter in the query field submits when valid and phase is not `running`.
- While `running`, composer is disabled (no second concurrent run).
- Empty or >4000-character query: client-side error (“Please type a question so we can help.” / length copy); FSM stays `idle`; no stub call.

---

## Run

Lightweight client FSM. No Redux. No streaming protocol.

### States

```
idle → running → done
```

| State | Meaning | UI |
|-------|---------|----|
| `idle` | No active run | Composer enabled; chat shows prior turns or empty prompt |
| `running` | Stub run in flight | Composer disabled; Status **Looking that up**; stages Understanding your question → Searching help articles → Writing a reply → Checking next steps (local timer, ADR-15); pending B-Mobile bubble; first label within 10s of send |
| `done` | Stub returned a result | Composer enabled for another turn; B-Mobile bubble + specialist strip update. **Start new conversation** (when the thread is not empty) runs `RESET` and **clears** the thread |

### Transitions

| From | Event | To | Trigger |
|------|-------|----|---------|
| `idle` | `START` | `running` | Valid submit → `startRun()` succeeds |
| `running` | `COMPLETE` | `done` | `getRunStatus()` returns `status: "done"` |
| `done` | `RESET` | `idle` | User chooses **Start new conversation** (clears thread + specialist strip) |
| `done` | `START` | `running` | User submits another question without reset (allowed) |

Illegal transitions are no-ops.

### Stub services (FE epic — no live backend)

| Function | Input | Output | Behavior |
|----------|-------|--------|----------|
| `startRun` | `{ query, requestHuman, disclosureAcknowledged }` | `{ runId: string }` | In-memory stub; does **not** call `POST /api/chat` |
| `getRunStatus` | `{ runId }` | `{ status: "running" \| "done", result?: ChatResponse }` | Poll while FSM is `running`; completes with a mock `ChatResponse` |

**Client timeout:** abort wait at **50–60s**. On abort, still transition `running → done` with an error-shaped `ChatResponse` (`error.code = llm_or_timeout`) and talk-to-a-person CTA. Do not invent an answer.

**Hook point for Integration:** replace stub bodies in `lib/api.ts` / `lib/services/runService.ts` with `fetch(NEXT_PUBLIC_API_BASE_URL + "/api/chat")`. Do not add that call in this epic.

---

## Results

Rendered on the same route. Customer-facing content lives in chat bubbles. The specialist strip binds to the **last `ChatResponse` in UI state** (ADR-14). Do not call `/api/last-result`.

| Region | Fields | Notes |
|--------|--------|-------|
| B-Mobile bubble | `reply`, `sources_used[]`, escalate notice | Sources on resolve; escalate copy when `decision=escalate` or `error != null` |
| I'd rather talk to a person | Checkbox | Always visible in the composer; sets `request_human` for the **next** send. Escalate notice in chat is informational / Future live-chat |
| For specialists | `decision`, `reason_codes[]`, expandable `steps[]`, `trace_id` | From last response only; Outcome shows Answered / Sent to a specialist plus the contract `decision` |
| Packet | `packet`, `stub_ticket_id` | Shown in the strip when escalate; `null` on resolve |

**Demo path expectations (mocked)**

| Path | Typical query | Mock `decision` |
|------|---------------|-----------------|
| A | in-KB FAQ (e.g. My Account PIN) | `resolve` + sources |
| B | unknown topic (e.g. quantum warranty) | `escalate` + packet + stub ticket |
| C | `requestHuman=true` | `escalate`, `reason_codes` include `request_human` |

---

## History

SAD lists **DB/history** as Future Work. This epic implements a **session-only chat thread** in React state (`history[]` rendered in `ChatWindow`). There is no separate History list and no click-to-restore of a past run.

| Behavior | MVP (this epic) | Future Work |
|----------|-----------------|-------------|
| Storage | In-memory turns for the browser tab | Persistent DB |
| Append | Each `done` run adds a You + B-Mobile pair | Server-side run log |
| Start new conversation | Clears thread, specialist strip, FSM → idle | Archive / new ticket |
| Survive refresh | No | Yes |
| Cross-tab | No | Optional |

Selecting a past turn is not supported. Follow-up questions append to the same thread unless the customer starts a new conversation.

---

## Spec Sync checklist

Update this table **after every commit** that touches frontend code or this spec. Tick the boxes that remain true; add a row with commit SHA.

### After-commit checks

- [ ] **Inputs** — composer fields and validation still match the Inputs table
- [ ] **Run** — FSM is still `idle → running → done`; `startRun` / `getRunStatus` still stubs (or Integration has updated this spec)
- [ ] **Results** — chat reply + specialist strip still bind last `ChatResponse` in UI state
- [ ] **History** — session thread only; **Start new conversation** clears the tab unless SAD/PRD changed
- [ ] **`frontend.md`** — Audit appended for the same change
- [ ] **No live backend** — no `fetch` to `/api/chat` unless Integration epic owns the commit
- [ ] **Placeholders** — Voice / CSAT / Live ticketing remain non-functional

### Commit log

| Date | Commit SHA | Spec sections touched | Boxes re-checked | Notes |
|------|------------|-----------------------|------------------|-------|
| 2026-08-14 | *(uncommitted — initial FE slice)* | Inputs, Run, Results, History | All drafted | Initial Critical Research Workflow |
| 2026-08-15 | *(uncommitted — chat window)* | Inputs, Run, Results, History | Re-checked | Chat bubbles; Start new conversation clears thread |

---

## Sources

- `project-context/1.define/prd.md` (§6, §10.4, AC-01…06)
- `project-context/1.define/sad.md` (§2 Frontend, API contracts, ADR-03/14/15)
- `.cursor/agents/frontend-eng.md`
- `.cursor/templates/sfs-template.md` (section taxonomy adapted; user-requested Inputs / Run / Results / History)

## Assumptions

- `setup.md` is not present; frontend is scaffolded in this epic against SAD layout (`frontend/` Next.js App Router).
- Operator asked for a **chat window** (You right / B-Mobile left) with Status under the chat and a specialist strip; stub contracts unchanged.
- Filename `frontend-funcional-spec.md` is the operator-requested spelling.
- `AAMAD_TARGET_RUNTIME` is unset → resolve `crewai`.
- `aamad.config.yml` is absent; `aamad.config.example.yml` UI theme `system` yields to PRD/SAD **light** theme.

## Open Questions

1. Should the session thread survive `localStorage` in MVP, or stay tab-session only (current)?
2. Instructor copy for AI disclosure beyond the generic SAD sentence.

## Audit

- **Timestamp**: 2026-08-14T23:10:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` (author functional spec)
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — no LLM crew prompts in this UI-only spec; stub copy is static

### Audit (append)

- **Timestamp**: 2026-08-15T17:30:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` (spec sync: chat window, Get help, Start new conversation, specialist strip)
