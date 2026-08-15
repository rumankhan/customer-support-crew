# Frontend Epic Log

**Persona**: `@frontend.eng`  
**Action**: `*develop-fe`  
**Status**: Thin Critical Research Workflow UI complete (mocks + B-Mobile seed KB)  
**Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)

---

## What was built

Single-route Next.js App Router app at `frontend/` for **B-Mobile** customer help (fictional carrier). Page order: disclosure → **chat window** → Status → For specialists → Coming later stubs.

| Section | Implementation |
|---------|----------------|
| Chat | `components/ChatWindow.tsx` — You (right) / B-Mobile (left) bubbles; composer at bottom |
| Composer | `components/InputsForm.tsx` (compact) — question, **I'd rather talk to a person**, **Get help**, **Start new conversation** (when the thread is not empty) |
| Status | `components/RunStatus.tsx` under the chat — Ready / Looking that up / Finished |
| For specialists | `components/SpecialistStrip.tsx` — last `ChatResponse` (`decision`, `reason_codes`, `steps[]`, packet) |
| Session thread | In-memory `history[]` rendered as chat turns (no separate History list). **Start new conversation** clears the thread (`RESET` → idle) |
| Spec | `project-context/2.build/frontend-funcional-spec.md` (includes Spec Sync checklist) |

Stub services (no live backend):

- `startRun` / `getRunStatus` in `lib/services/runService.ts`
- Re-exported from `lib/api.ts` as the Integration hook point
- Dummy retrieval: `lib/kb.ts` + mock `GET /api/kb` reads `backend/kb/articles.csv` (12 B-Mobile rows, overlap floor 0.35)
- Mock `ChatResponse` payloads in `lib/mockResponse.ts` for demo paths A/B/C

Also included because PRD/SAD require them for the FE epic:

- AI disclosure banner (`AC-01`)
- Optimistic local stage labels (Understanding your question → Searching help articles → Writing a reply → Checking next steps) — **no SSE**
- Visible Future Work stubs: Voice, CSAT dashboard, Live ticketing

## Stack

- Next.js 15 App Router, React 19, TypeScript, Tailwind CSS 3
- Light theme; Source Sans 3 + Source Serif 4 via `next/font`
- Local React state only (no Redux)
- Port **3000** (`npm run dev` in `frontend/`)

## SAD layout mapping

| SAD path | This epic |
|----------|-----------|
| `app/page.tsx` | Disclosure, ChatWindow, RunStatus, SpecialistStrip, FutureWorkStubs |
| `components/*` | ChatWindow, InputsForm, RunStatus, SpecialistStrip, DisclosureBanner, FutureWorkStubs |
| `lib/types.ts` | `ChatRequest` / `ChatResponse` aligned to SAD §2 |
| `lib/api.ts` | Stub re-exports; Integration replaces with `fetch` |
| `lib/mockResponse.ts` | Path A/B/C mocks |
| `lib/kb.ts` | Parses `articles.csv` + `searchKb()` |
| `lib/uiCopy.ts` | Customer-facing labels |
| `app/api/kb/route.ts` | Mock-only read of `backend/kb/articles.csv` |

**Chat transcript in one card.** Operator later asked for bubbles (You right, B-Mobile left) instead of a separate Answer card. Stub contracts (`startRun` / `ChatResponse`) unchanged.

## Mock vs Integration hook points

| Call | FE epic (now) | Integration epic |
|------|----------------|------------------|
| Get help | `startRun()` in-memory stub | `POST ${NEXT_PUBLIC_API_BASE_URL}/api/chat` |
| Poll / wait | `getRunStatus()` stub (~1.8s) | Single non-streaming JSON; no poll required if request awaits kickoff |
| Last result | UI state (ADR-14) | Same; do not require `/api/last-result` |
| Timeout | Client abort **55s** | Keep; API soft timeout 45s |

Do **not** set `NEXT_PUBLIC_API_BASE_URL` usage in this epic. Mock `GET /api/kb` only reads the seed CSV; Integration does not keep that route as the product API.

## StatusLine contract (ADR-15)

On `START`, a client timer cycles stage labels. First label is immediate (**Understanding your question**). On `COMPLETE` or error, animation stops; `steps[]` from the mock `ChatResponse` are in **For specialists**. While running, the chat also shows a B-Mobile pending bubble with the same stage label.

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

## Spec Sync

After each commit that touches `frontend/` or the spec, update the **Spec Sync checklist** in `frontend-funcional-spec.md` (tick boxes + add commit SHA row). Then append an Audit line here.

## Sources

- `project-context/1.define/prd.md` (§6, §10.4)
- `project-context/1.define/sad.md` (§2 Frontend, ADR-03/14/15)
- `.cursor/agents/frontend-eng.md`
- Operator request: chat window (bubbles) + specialist strip; same FSM/stubs as the original Inputs / Run / Results slice

## Assumptions

- `setup.md` missing; this epic created the Next.js scaffold to match SAD + existing `frontend/package-lock.json`.
- Chat bubbles on `/` satisfy SAD “Web chat UI (`/`)”. Stub I/O unchanged.
- Session thread is in-memory; SAD “DB/history” remains Future Work. **Start new conversation** clears the tab thread only.
- Filename `frontend-funcional-spec.md` kept as requested.

## Open Questions

1. Persist the session thread in `localStorage` for demos?
2. Final AI disclosure copy owner (PRD OQ).

## Audit

- **Timestamp**: 2026-08-14T23:10:00-05:00
- **Persona**: `frontend-eng`
- **Action**: `develop-fe`
- **Resolved runtime**: `crewai` (default; `AAMAD_TARGET_RUNTIME` unset)
- **Prompt Trace**: omitted — UI-only mocks; no crew prompts rendered
- **Notes**: Created functional spec, Next.js single-route app, FSM, stub `startRun`/`getRunStatus`, Spec Sync checklist

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
