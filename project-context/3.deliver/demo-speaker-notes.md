# Peer demo — speaker notes

Open [`demo-presentation.html`](demo-presentation.html) in a browser. `F` fullscreen · `N` notes · `P` PDF.

**Timebox:** 4 min story · 8 min live chat · 8 min “how it works” · 5 min Q&A

This deck is the **product** talk first, then the machinery. Architecture weeds (ADRs, env vars, eval IDs) stay in the SAD unless someone asks.

**Prep**

1. Chat at `http://localhost:3000`, backend healthy on 8001.
2. One conversation at a time.
3. Ask the room up front if they want the Telegram credit path.

## Run of show

| # | Slide | Say | Don’t |
|---|--------|-----|--------|
| 1 | Title | Ask who has repeated their story to a human after a bot. That is the product. | CrewAI, ports, AAMAD |
| 2 | The moment | Bad handoffs feel like starting over. We refuse to do that. | Recite market TAM |
| 3 | Three people | Customer, inheriting agent, manager for money | “Personas” jargon |
| 4 | What you’ll see | Set up four feelings, then **leave the deck** | Explain the stack first |
| 5 | Live PIN | Be the customer. Point at disclosure, progress, sources. | Narrate FastAPI / SSE |
| 6 | Miss + human | A miss is a win. Talk-to-person must work. Optional $25 credit. | Call them Path B/C unless asked |
| 7 | Four agents | Understand → look up → write → decide. Name the four jobs and their tools. | YAML, `max_iter` |
| 8 | Models | One Gemma tonight (or gpt-4o-mini). YAML has low/mid for later. Fail = human. | LiteLLM, env cascade |
| 9 | Guardrails | Off-topic = polite no, no specialist pitch. Three layers: YAML, Python, UI. | Recite function names |
| 10 | HITL | Money waits. Telegram Approve/Deny. Not the same as talk-to-human. | Call it a fifth agent |
| 11 | What else | Disclosure, live stages, citations, packet, FTS, fail-open. One pass. | Dump the SAD |
| 12 | Straight talk | Works in class. Slow, one-at-a-time, not public-internet ready. | EC-001…019 bingo |
| 13 | Further | Sit beside Zendesk. Fix trust and wait before features. | Seat-based pricing tables |
| 14 | Close | Don’t make them start over. Take questions. | Dump the SAD |

## Live copy-paste

| Feeling | Type this |
|---------|-----------|
| We know it | `How do I reset my B-Mobile My Account PIN?` (keep it calm) |
| We don’t | `What is your quantum warranty for the hardware drone?` |
| Human | Talk-to-person + a billing complaint |
| Manager | `Apply a $25 credit to ACC-1001 for the outage last week` |
| Off-topic | `What is the capital of France?` (guardrail: no specialist pitch) |

## If they ask for weeds

- **Agents:** `query_classifier` → `knowledge_retriever` (`kb_search`) → `response_specialist` → `escalation_manager` (`ticket_stub`). Sequential, no delegation.
- **Model:** Ollama Cloud `gemma4:31b` for all four jobs tonight. YAML still tags low/mid. Switch provider in `.env` and restart. Failure → retry, then human — no silent OpenAI hop.
- **HITL:** After the crew. Detects credit / ETF / PIN override / refund / roaming. Customer waits on SSE. Manager taps Telegram. Timeout does not grant money.
- **Guardrails:** Classifier `out_of_scope` + `apply_out_of_scope_reply_policy()` strips “talk to a human.” Citations re-checked against FTS. `STUB-*` tickets only.
- **Stack:** Next.js chat → SSE API → four sequential agents. Details: `project-context/1.define/sad.md`.
- **Why not production:** wait time, one chat at a time, one over-confident miss, open chat must not be public.

## If something breaks

Stay in the customer story: “This is the fail-open — we’d rather offer a person than guess.” Then check: one in-flight chat, backend on 8001, Telegram off if HITL is hanging.
