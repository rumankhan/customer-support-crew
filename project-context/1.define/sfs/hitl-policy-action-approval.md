# SFS: HITL Policy Action Approval

**Feature ID:** SFS-HITL-001  
**Status:** Implemented (MVP)  
**PRD anchor:** P2 — Autonomous CRM mutations; MRD §3 HITL required for policy exceptions  
**SAD anchor:** ADR-HITL-01 (Application-level approval gate, not CrewAI human_input)

---

## Purpose

When a customer requests a policy-exception action (goodwill billing credit, ETF waiver, etc.), the system proposes the action and routes it through a human manager for approval via Telegram before executing the stub mutation. The customer waits synchronously in the web chat.

---

## Scope (MVP)

- **In scope:** Billing credit, ETF waiver (primary demos). Security override, refund, roaming exception (alternate scripts, same code path).
- **Out of scope:** Real CRM/billing mutations, multi-turn negotiation, role-based authz, SSO.

---

## HITL vs. Escalation

| Pattern | Trigger | Manager action | Customer outcome |
|---------|---------|----------------|-----------------|
| **HITL approval (new)** | Customer requests policy action (credit, waiver) | Approve/Deny on **Telegram** | Approved/denied in-chat |
| **Escalation (existing)** | Angry, low confidence, "talk to human" | Read packet; handle in CRM | Specialist handoff + stub ticket |

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| `ChatRequest.message` | Customer | Contains action request + subject ID |
| `ClassifierOutput.intent` | query_classifier agent | Must indicate policy action |
| `ClassifierOutput.entities` | query_classifier agent | Should include account/order ID |
| Stub account context | `backend/data/support.db` — `stub_accounts` table | Tenure, outage flags, ETF amount |
| `TELEGRAM_BOT_TOKEN` | env | Required when `TELEGRAM_ENABLED=true` |
| `TELEGRAM_MANAGER_CHAT_ID` | env | Chat ID that can approve |

---

## Action Detection (Post-Classifier Heuristic)

Implemented in `backend/chat_service.py` — `detect_policy_action()`:

| `action_kind` | Detection criteria |
|---------------|-------------------|
| `billing_credit` | Credit/goodwill/compensation/outage language. Account (`ACC-*`) and dollar amount optional |
| `etf_waiver` | Cancel/termination/waive + fee/ETF language. Account and amount optional |
| `security_override` | Reset PIN + lost SIM / no SMS |
| `refund` | Refund/process return + `ORD-*` |
| `roaming_exception` | Enable roaming + exception/free |

Vague credit/fee lines (`credit for outage`, `can you waive my fee`) still open HITL. If account **or** amount is missing, assign **lookup # 1–100** (`subject_id` `REF-{n}` when no account; proposed amount `$n` when no dollars). If both account and amount are present, no lookup #.

---

## Processing Flow

```
1. Customer sends message
2. Crew runs: classify → retrieve_knowledge → compose_response → triage_and_escalate
3. chat_service.detect_policy_action() checks classifier output + message
4. If policy action detected:
   a. approval_service.create_approval() writes pending row to SQLite
   b. telegram_bot.notify_manager() sends message + inline Approve/Deny buttons
   c. Streaming: push SSE event approval_required { approval_id, action_kind, reply_pending }
   d. Streaming: enter wait loop polling approval row every 2s (max 300s)
5. Manager taps Approve or Deny on Telegram
   a. Telegram callback → approval_service.decide_approval()
   b. Waiter asyncio.Event is set
6. Streaming: push SSE event approval_decided { approval_id, outcome, reply }
7. Customer chat displays final approved/denied message
```

---

## Outputs

### SSE Events (new)

**`approval_required`**
```json
{
  "trace_id": "...",
  "approval_id": "APR-xxxx",
  "action_kind": "billing_credit",
  "reply_pending": "Your credit request is being reviewed by a manager..."
}
```

**`approval_decided`**
```json
{
  "trace_id": "...",
  "approval_id": "APR-xxxx",
  "outcome": "approved",
  "reply": "$25 credit applied to ACC-1001; appears on next bill."
}
```

### ChatResponse Extension
```
decision: "resolve" | "escalate" | "pending_approval"
approval: ApprovalRequest | null
```

### SQLite Row (`approval_requests`)
```
id, session_id, trace_id, action_kind, subject_id, amount, reason,
context_json, status, operator_note, decided_by, telegram_message_id,
created_at, decided_at
```

---

## Customer-Facing Copy

| Action | Pending | Approved | Denied (manager reason) | Denied (`/skip`) |
|--------|---------|----------|-------------------------|------------------|
| Billing credit | Looking that up… manager reviewing $X for {reason} | `Your request was approved and we are crediting you $X for {reason}.` | `Your request was not approved. We are unable to credit you $X for {reason}.` + manager note | Billing boilerplate |
| ETF waiver | Looking that up… manager reviewing waive $X | Waiver approved (or credit copy if they asked for a credit) | `Your request was not approved. Reason: {note}` | Early-termination boilerplate |

---

## Telegram Manager Notification

```
🔔 Approval required — {Action Kind Label}

Account/Order: {subject_id}
Lookup #: {n}   ← when assigned (vague credit/fee)
Amount: ${amount}
Reason: {reason}

Customer said:
"{customer_message}"

Context:
• Tenure: {tenure}
• {context_flags}
• KB: {kb_citations}

Ref: {approval_id} | Trace: {trace_id}

[✅ Approve]  [❌ Deny]
```

### Bot Commands
| Command | Response |
|---------|----------|
| `/pending` | Lists all pending approvals with short summary |
| `/history` | Last 10 approved/denied decisions |
| `/detail APR-xxxxxxxx` | Full request |
| After Deny | Bot asks for a reason, or `/skip` |

---

## Validations and Error Handling

| Condition | Handling |
|-----------|----------|
| `TELEGRAM_ENABLED=false` | Log warning; resolve with "manager unavailable, contact billing" copy |
| Missing subject ID | Return clarifying question, skip HITL |
| Approval timeout (300s) | Push `approval_timeout` SSE; reply "Still under review, we'll follow up" |
| Duplicate Telegram callback | Idempotent — ignore if already decided |
| Wrong chat ID in callback | Reject; log security warning |
| DB write failure | Fall back to escalate with system_error reason code |

---

## Acceptance Criteria

| ID | Condition |
|----|-----------|
| HITL-AC-01 | Info-only questions (e.g. return policy) resolve from KB with no approval row |
| HITL-AC-02 | “Apply a $25 credit to ACC-1001…” creates pending approval and Telegram notification with Approve/Deny |
| HITL-AC-03 | “Cancel my plan and waive the $150 ETF on ACC-2002” creates `etf_waiver` pending approval |
| HITL-AC-04 | Manager Approve on Telegram → customer chat shows approved copy via SSE `approval_decided` |
| HITL-AC-05 | Manager Deny on Telegram → customer chat shows denied copy (optional note) |
| HITL-AC-06 | Customer page `/` has **no** specialist strip; operator detail on **`/operator`** only |
| HITL-AC-07 | Callbacks from a chat ID other than `TELEGRAM_MANAGER_CHAT_ID` are ignored |
| HITL-AC-08 | Duplicate callbacks are idempotent (already-decided rows ignored) |
| HITL-AC-09 | Missing account/order ID → clarifying question, no HITL |
| HITL-AC-10 | `TELEGRAM_ENABLED=false` → do not wait 300s; customer gets manager-unavailable copy |

## Timing

| Step | Target |
|------|--------|
| Crew + detection | ≤ `CHAT_TIMEOUT_SECONDS` (default 180s); HITL wait ≤ `HITL_TIMEOUT_SECONDS` (300s) |
| Telegram notification delivery | ~1s (long-polling mode) |
| Manager decision (demo) | Manual — typically <60s in demo |
| Approval timeout | 300s (configurable `HITL_TIMEOUT_SECONDS`) |
| Poll interval | 2s |

---

## Security (MVP)

- Accept Telegram callbacks only from `TELEGRAM_MANAGER_CHAT_ID`
- Store `decided_by: "telegram:{user_id}"` for audit
- Never expose bot token to frontend
- Approval mutations are stub-only (no real billing)

---

## Sources
- PRD §6 Future Features: autonomous CRM mutations, refunds
- MRD §3: HITL required for policy exceptions, regulated decisions
- SAD ADR-21 (Telegram HITL); ADR-HITL-01 application-level gate

## Assumptions
- Single manager DM; group chat requires `chat_id` of group
- Telegram long-polling runs inside FastAPI lifespan (no ngrok needed for local dev)
- Stub mutations only; no real billing/CRM integration

## Open Questions
- Should timeout trigger auto-escalate or auto-deny? (Current: neutral pending message)
- Should we support multiple manager chat IDs for group approval?

## Audit
- Persona: @backend.eng
- Action: create-sfs (HITL policy action approval)
- Timestamp: 2026-08-28
- Runtime: crewai (application-level gate; no CrewAI human_input used)

### Audit (append)
- Persona: @backend.eng
- Action: sync-docs
- Timestamp: 2026-08-28T23:45:00-05:00
- Notes: Vague credit/fee → lookup # 1–100; deny reason vs `/skip` copy
