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
| `billing_credit` | Intent contains credit/goodwill/compensation + entity matches `ACC-\d+` + dollar amount |
| `etf_waiver` | Intent contains cancel/termination/waive + fee/ETF keyword |
| `security_override` | Intent contains reset PIN + lost SIM / no SMS |
| `refund` | Intent contains refund/process return + entity matches `ORD-\d+` |
| `roaming_exception` | Intent contains enable roaming + exception/free |

If no subject entity found → return clarifying question, no HITL.

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

| Action | Pending | Approved | Denied |
|--------|---------|----------|--------|
| Billing credit | "Your credit request is being reviewed by a manager. Please wait…" | "$X credit applied to {account}; appears on next bill." | "Unable to approve credit. {note}. Contact billing for review." |
| ETF waiver | "Your ETF waiver request is being reviewed by a manager. Please wait…" | "Early termination fee waived; plan ends {date}." | "ETF waiver denied per contract terms. {note}." |
| Security override | "Your PIN override request is being reviewed. Please wait…" | "PIN reset authorized; secure link sent to email on file." | "Cannot override SMS verification remotely. Visit store with photo ID." |
| Refund | "Your refund request is being reviewed by a manager. Please wait…" | "Refund of ${amount} approved for {order}." | "Refund denied. {note}." |

---

## Telegram Manager Notification

```
🔔 Approval required — {Action Kind Label}

Account/Order: {subject_id}
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
| HITL-AC-06 | Customer page SpecialistStrip is read-only (no Approve/Deny buttons) |
| HITL-AC-07 | Callbacks from a chat ID other than `TELEGRAM_MANAGER_CHAT_ID` are ignored |
| HITL-AC-08 | Duplicate callbacks are idempotent (already-decided rows ignored) |
| HITL-AC-09 | Missing account/order ID → clarifying question, no HITL |
| HITL-AC-10 | `TELEGRAM_ENABLED=false` → do not wait 300s; customer gets manager-unavailable copy |

## Timing

| Step | Target |
|------|--------|
| Crew + detection | ≤ existing p95 (≤45s) |
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
- SAD ADR-HITL-01 (application-level gate)

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
