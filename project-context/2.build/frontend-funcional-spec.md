# Frontend Functional Spec: Critical Research Workflow

**Feature ID**: FE-CRW-001  
**Primary UI**: single route `/` (form + results on one page)  
**Selected Runtime**: `crewai` (UI mocks only; no live API in this epic)  
**Owning persona**: `@frontend.eng`

This spec defines the **Critical Research Workflow** — the customer-facing path that submits a research query, runs a mocked multi-agent research cycle, and shows a grounded result or a clean escalate packet. Persistent chat transcripts, live `POST /api/chat`, and a database-backed history are out of this epic.

---

## Purpose and Scope

- **Purpose**: Let a customer submit a research question, watch a run complete (`idle → running → done`), and inspect the latest result plus session history.
- **In Scope**: Inputs form, run FSM + stub services, results panel, in-session history, Spec Sync checklist.
- **Out of Scope**: Live backend wiring (Integration epic); streaming tokens; SSO; Voice / CSAT / live ticketing (visible stubs only); persisted run history (SAD Future Work).

---

## Traceability

| Anchor | Reference |
|--------|-----------|
| PRD §6 Interface Requirements | Chat page `/`, disclosure, status line, result card, operator strip, Talk-to-human |
| PRD §10.4 Frontend epic | UI only; mocks; no live BE; Tailwind + Next.js App Router + TypeScript |
| PRD AC-01…AC-06 | Disclosure, resolve/escalate UX, operator fields, failure CTA |
| SAD §2 Frontend logical structure | `app/page.tsx`, components, `lib/types.ts`, `lib/api.ts` mocks |
| SAD ADR-03 / ADR-14 / ADR-15 | Next.js + Tailwind + TS; last result in UI state; optimistic local stages (no SSE) |
| SAD Future Work | DB/history, streaming UI, voice, CSAT dashboard, live ticketing |

---

## Inputs

Single form on `/`. Submit is enabled only in FSM `idle` (or after explicit reset from `done`).

| Input | Type / format | Source | Required | Validation |
|-------|---------------|--------|----------|------------|
| `query` | string, mapped to `ChatRequest.message` | Research topic field | Yes | Trimmed non-empty; max **4000** chars (SAD) |
| `requestHuman` | boolean, mapped to `ChatRequest.request_human` | “Talk to a human” checkbox | No | Default `false` |
| `disclosureAcknowledged` | boolean, mapped to `ChatRequest.disclosure_acknowledged` | AI disclosure control | No | Default `false`; missing/`false` does **not** block submit (AC-01b) |
| `sessionId` | optional opaque string | Generated in-session if needed | No | Not shown; not persisted |

**UI rules**

- AI disclosure is visible until acknowledged (AC-01). Acknowledge-to-dismiss is allowed.
- Keyboard: Enter in the query field submits when valid and phase is `idle`.
- While `running`, inputs are disabled (no second concurrent run).
- Empty or >4000-character query: client-side error; FSM stays `idle`; no stub call.

---

## Run

Lightweight client FSM. No Redux. No streaming protocol.

### States

```
idle → running → done
```

| State | Meaning | UI |
|-------|---------|----|
| `idle` | No active run | Form enabled; results empty or showing last completed run after reset-to-edit |
| `running` | Stub run in flight | Form disabled; status line cycles Classifying → Retrieving → Composing → Triaging (local timer, ADR-15); first label within 10s of send |
| `done` | Stub returned a result | Form stays disabled until Reset / New research; Results and History update |

### Transitions

| From | Event | To | Trigger |
|------|-------|----|---------|
| `idle` | `START` | `running` | Valid submit → `startRun()` succeeds |
| `running` | `COMPLETE` | `done` | `getRunStatus()` returns `status: "done"` |
| `done` | `RESET` | `idle` | User chooses New research (keeps History) |
| `done` | `START` | `running` | User submits again without reset (allowed) |

Illegal transitions are no-ops.

### Stub services (FE epic — no live backend)

| Function | Input | Output | Behavior |
|----------|-------|--------|----------|
| `startRun` | `{ query, requestHuman, disclosureAcknowledged }` | `{ runId: string }` | In-memory stub; does **not** call `POST /api/chat` |
| `getRunStatus` | `{ runId }` | `{ status: "running" \| "done", result?: ChatResponse }` | Poll while FSM is `running`; completes with a mock `ChatResponse` |

**Client timeout:** abort wait at **50–60s**. On abort, still transition `running → done` with an error-shaped `ChatResponse` (`error.code = llm_or_timeout`) and Talk-to-human CTA. Do not invent an answer.

**Hook point for Integration:** replace stub bodies in `lib/api.ts` / `lib/services/runService.ts` with `fetch(NEXT_PUBLIC_API_BASE_URL + "/api/chat")`. Do not add that call in this epic.

---

## Results

Rendered on the same route when FSM is `done` (and may remain visible in `idle` after reset until a new run starts — implementation may clear or keep last result; current UI keeps last result until a new `START`).

Bind to the **last `ChatResponse` in UI state** (ADR-14). Do not call `/api/last-result`.

| Region | Fields | Notes |
|--------|--------|-------|
| Result card | `reply`, `sources_used[]`, escalate notice | Sources on resolve; escalate copy when `decision=escalate` or `error != null` |
| Talk to a human | CTA | Always visible; in `done` it is informational / Future live-chat. Checkbox on Inputs sets `request_human` for the **next** run |
| Operator strip | `decision`, `reason_codes[]`, expandable `steps[]`, `trace_id` | From last response only |
| Packet | `packet`, `stub_ticket_id` | Shown when escalate; `null` on resolve |

**Demo path expectations (mocked)**

| Path | Typical query | Mock `decision` |
|------|---------------|-----------------|
| A | in-KB FAQ (e.g. password reset) | `resolve` + sources |
| B | unknown topic (e.g. quantum warranty) | `escalate` + packet + stub ticket |
| C | `requestHuman=true` | `escalate`, `reason_codes` include `request_human` |

---

## History

SAD lists **DB/history** as Future Work. This epic implements **session-only** history in React state.

| Behavior | MVP (this epic) | Future Work |
|----------|-----------------|-------------|
| Storage | In-memory list for the browser tab | Persistent DB |
| Append | Each `done` run prepends `{ runId, query, decision, completedAt }` | Server-side run log |
| Select | Click a row to re-display that run’s result (no re-fetch) | Replay from API |
| Survive refresh | No | Yes |
| Cross-tab | No | Optional |

History does not change the FSM by itself. Selecting a past run updates the Results panel only.

---

## Spec Sync checklist

Update this table **after every commit** that touches frontend code or this spec. Tick the boxes that remain true; add a row with commit SHA.

### After-commit checks

- [ ] **Inputs** — form fields and validation still match the Inputs table
- [ ] **Run** — FSM is still `idle → running → done`; `startRun` / `getRunStatus` still stubs (or Integration has updated this spec)
- [ ] **Results** — Result card + operator strip still bind last `ChatResponse` in UI state
- [ ] **History** — still session-only unless SAD/PRD changed
- [ ] **`frontend.md`** — Audit appended for the same change
- [ ] **No live backend** — no `fetch` to `/api/chat` unless Integration epic owns the commit
- [ ] **Placeholders** — Voice / CSAT / Live ticketing remain non-functional

### Commit log

| Date | Commit SHA | Spec sections touched | Boxes re-checked | Notes |
|------|------------|-----------------------|------------------|-------|
| 2026-08-14 | *(uncommitted — initial FE slice)* | Inputs, Run, Results, History | All drafted | Initial Critical Research Workflow |

---

## Sources

- `project-context/1.define/prd.md` (§6, §10.4, AC-01…06)
- `project-context/1.define/sad.md` (§2 Frontend, API contracts, ADR-03/14/15)
- `.cursor/agents/frontend-eng.md`
- `.cursor/templates/sfs-template.md` (section taxonomy adapted; user-requested Inputs / Run / Results / History)

## Assumptions

- `setup.md` is not present; frontend is scaffolded in this epic against SAD layout (`frontend/` Next.js App Router).
- Operator asked for a **form + results** single route rather than a multi-bubble chat transcript; that is treated as the thin FE vertical slice. A message-list polish can follow without changing stub contracts.
- Filename `frontend-funcional-spec.md` is the operator-requested spelling.
- `AAMAD_TARGET_RUNTIME` is unset → resolve `crewai`.
- `aamad.config.yml` is absent; `aamad.config.example.yml` UI theme `system` yields to PRD/SAD **light** theme.

## Open Questions

1. Should Week 4 polish replace this form with a chat message list while keeping the same FSM + stubs?
2. Should History survive `localStorage` in MVP, or stay tab-session only (current)?
3. Instructor copy for AI disclosure beyond the generic SAD sentence.

## Audit

- **Timestamp**: 2026-08-14T23:10:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe` (author functional spec)
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — no LLM crew prompts in this UI-only spec; stub copy is static
