# Frontend Epic Log

**Persona**: `@frontend.eng`  
**Action**: `*develop-fe`  
**Status**: Thin Critical Research Workflow UI complete (mocks only)  
**Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)

---

## What was built

Single-route Next.js App Router app at `frontend/` implementing the **Critical Research Workflow**:

| Section | Implementation |
|---------|----------------|
| Inputs | `components/InputsForm.tsx` — query, Talk-to-human checkbox, 4000-char cap |
| Run | FSM `idle → running → done` in `lib/fsm.ts`; status in `components/RunStatus.tsx` |
| Results | `components/ResultsPanel.tsx` + operator strip from last `ChatResponse` in UI state |
| History | `components/HistoryList.tsx` — session-only |
| Spec | `project-context/2.build/frontend-funcional-spec.md` (includes Spec Sync checklist) |

Stub services (no live backend):

- `startRun` / `getRunStatus` in `lib/services/runService.ts`
- Re-exported from `lib/api.ts` as the Integration hook point
- Mock `ChatResponse` payloads in `lib/mockResponse.ts` for demo paths A/B/C

Also included because PRD/SAD require them for the FE epic:

- AI disclosure banner (`AC-01`)
- Optimistic local stage labels (Classifying → Retrieving → Composing → Triaging) — **no SSE**
- Visible Future Work stubs: Voice, CSAT dashboard, Live ticketing

## Stack

- Next.js 15 App Router, React 19, TypeScript, Tailwind CSS 3
- Light theme; Source Sans 3 + Source Serif 4 via `next/font`
- Local React state only (no Redux)
- Port **3000** (`npm run dev` in `frontend/`)

## SAD layout mapping

| SAD path | This epic |
|----------|-----------|
| `app/page.tsx` | Single route: form + run + results + history |
| `components/*` | Disclosure, Inputs, Run, Results, History, FutureWorkStubs |
| `lib/types.ts` | `ChatRequest` / `ChatResponse` aligned to SAD §2 |
| `lib/api.ts` | Stub re-exports; Integration replaces with `fetch` |
| `lib/mockResponse.ts` | Path A/B/C mocks |

**Not a chat bubble list.** Operator requested a form + results page. Message-list polish is deferred (Open Question).

## Mock vs Integration hook points

| Call | FE epic (now) | Integration epic |
|------|----------------|------------------|
| Start research | `startRun()` in-memory stub | `POST ${NEXT_PUBLIC_API_BASE_URL}/api/chat` |
| Poll / wait | `getRunStatus()` stub (~1.8s) | Single non-streaming JSON; no poll required if request awaits kickoff |
| Last result | UI state (ADR-14) | Same; do not require `/api/last-result` |
| Timeout | Client abort **55s** | Keep; API soft timeout 45s |

Do **not** set `NEXT_PUBLIC_API_BASE_URL` usage in this epic.

## StatusLine contract (ADR-15)

On `START`, a client timer cycles stage labels. First label is immediate (`Classifying`). On `COMPLETE` or error, animation stops and the authoritative `steps[]` from the mock `ChatResponse` are shown in the operator strip.

## How to run

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Try:

- Path A: `How do I reset my Acme Cloud password?` → resolve + sources
- Path B: `What is your quantum warranty for the hardware drone?` → escalate + packet
- Path C: check Talk to a human → escalate with `request_human`

## Spec Sync

After each commit that touches `frontend/` or the spec, update the **Spec Sync checklist** in `frontend-funcional-spec.md` (tick boxes + add commit SHA row). Then append an Audit line here.

## Sources

- `project-context/1.define/prd.md` (§6, §10.4)
- `project-context/1.define/sad.md` (§2 Frontend, ADR-03/14/15)
- `.cursor/agents/frontend-eng.md`
- Operator request: Critical Research Workflow (Inputs / Run / Results / History)

## Assumptions

- `setup.md` missing; this epic created the Next.js scaffold to match SAD + existing `frontend/package-lock.json`.
- Form + results on one route satisfies the thin FE slice; full chat transcript is polish.
- Session history is allowed as in-memory UX; SAD “DB/history” remains Future Work.
- Filename `frontend-funcional-spec.md` kept as requested.

## Open Questions

1. Week 4: keep form layout or replace with chat message list without changing stub contracts?
2. Persist History in `localStorage` for demos?
3. Final AI disclosure copy owner (PRD OQ).

## Audit

- **Timestamp**: 2026-08-14T23:10:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe`
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — UI-only mocks; no crew prompts rendered
- **Notes**: Created functional spec, Next.js single-route app, FSM, stub `startRun`/`getRunStatus`, Spec Sync checklist
