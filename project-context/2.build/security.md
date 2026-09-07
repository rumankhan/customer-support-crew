# Security Assessment — Multi-Agent Customer Support Crew (B-Mobile MVP)

**Persona**: `@security.eng`  
**Action**: `*assess-security` (+ `*scan-secrets`, `*review-deps`, `*document-security`)  
**Scope**: MVP chat + CrewAI backend + Next.js FE + Telegram HITL (local demo)  
**Resolved runtime**: `crewai`  
**Prerequisite**: `qa.md` present (PASS); `evals.md` present (static/fixture PASS)

---

## Executive summary

Secrets hygiene and common injection paths (SQLite parameterization, React text rendering, FTS escaping) look sound for a **local course demo**. **Mitigated (2026-09-06):** `/api/approvals/*` and `/api/last-result` require `X-Operator-Key` matching `OPERATOR_API_KEY` (fail closed if unset); Next.js approvals route injects the key server-side; Telegram refuses to start without bot token + manager chat id; `__main__` binds `127.0.0.1`; Prompt Trace `error_detail` sanitized.

| Severity | Count | Deliver stance |
|----------|------:|----------------|
| Critical | 0 | — |
| High | 0 open (2 mitigated) | Auth gates shipped |
| Medium | 1 residual open (SEC-04 DoS/cost) | Accept localhost; rate-limit before public |
| Low | 2 residual | Track |
| Info | 5+ | Positive controls |

**Verdict:** **PASS (mitigated)** for MVP localhost demo. Chat remains open by design (SAD). Do not expose publicly without rate limits (SEC-04). Ready for `@devops.eng` with SEC-04 noted as accepted residual.

---

## Findings

### HIGH

#### SEC-01 — Unauthenticated policy decide (exploit)

| Field | Detail |
|-------|--------|
| Severity | **High** |
| Asset | `POST /api/approvals/{approval_id}/decide` (`backend/main.py`); proxied by `frontend/app/api/approvals/[...path]/route.ts` |
| Issue | No API key, session, or shared secret. Any client that can open a pending `APR-*` id (from pending list or guess/leak) can **approve or deny** billing credit / ETF waiver demos. |
| Exploit sketch | `GET /api/approvals/pending` → copy id → `POST /api/approvals/{id}/decide` with `{"decision":"approve"}` |
| Impact | Unauthorized policy outcome in customer SSE wait; undermines HITL trust model (ADR-21) |
| Mitigation (route to `@backend.eng`) | Require `X-Operator-Key` / `OPERATOR_API_KEY` (or mTLS) on **all** `/api/approvals/*` mutating routes; optionally disable HTTP decide when Telegram is primary; do not proxy decide from public FE without auth |
| Status | **Mitigated** (2026-09-06) — `Depends(require_operator_key)` on decide |

#### SEC-02 — Unauthenticated approval queue disclosure

| Field | Detail |
|-------|--------|
| Severity | **High** (mitigated) |
| Asset | `GET /api/approvals/pending`, `GET /api/approvals/history`, `GET /api/approvals/{id}/status` |
| Issue | No auth. Leaks stub account/order ids, amounts, reasons, operator notes, and approval state. FE `/operator` and Next proxy inherit the same openness. |
| Impact | Privacy / demo-data disclosure; enables SEC-01 by listing live ids |
| Mitigation | Same operator key on all `/api/approvals/*`; FE proxy injects key server-side |
| Status | **Mitigated** (2026-09-06) |

---

### MEDIUM

#### SEC-03 — `OPERATOR_API_KEY` documented but not enforced

| Field | Detail |
|-------|--------|
| Severity | **Medium** |
| Asset | SAD §3 env matrix / §4 Security; `GET /api/last-result` in `backend/main.py` |
| Issue | SAD specifies optional `OPERATOR_API_KEY` + `X-Operator-Key` for last-result. Implementation returns `last_result` with **no check**. Cross-user leakage of last chat packet on a shared demo host. |
| Mitigation | Implement header check when env set; default deny if key configured; document in `backend.md` |
| Owner | `@backend.eng` |
| Status | **Mitigated** (2026-09-06) — `require_operator_key` on last-result; fail closed if env unset |

#### SEC-04 — Unauthenticated LLM chat → cost / resource DoS

| Field | Detail |
|-------|--------|
| Severity | **Medium** |
| Asset | `POST /api/chat`, `POST /api/chat/stream` |
| Issue | Intentional open chat (SAD). No per-IP rate limit beyond crew `MAX_RPM`. Attacker can burn provider tokens / saturate single-threaded kickoff. |
| Mitigation | Reverse-proxy rate limit; bind localhost; optional demo token; queue/reject when busy (QA already noted concurrent hang) |
| Status | **Accepted for local demo** if host is not public — see Assumptions |

#### SEC-05 — Default bind / `__main__` uses `0.0.0.0`

| Field | Detail |
|-------|--------|
| Severity | **Medium** |
| Asset | `backend/main.py` `uvicorn.run(..., host="0.0.0.0")`; operators may also expose ports |
| Issue | LAN clients can hit open chat + approval APIs (amplifies SEC-01/02/04) |
| Mitigation | Document/run `--host 127.0.0.1` only (matches `RUNNING.md` quick start); remove or guard `0.0.0.0` in `__main__` |
| Owner | `@backend.eng` / `@devops.eng` |
| Status | **Mitigated** (2026-09-06) — `__main__` uses `host="127.0.0.1"` |

#### SEC-06 — Telegram enabled without manager chat allowlist

| Field | Detail |
|-------|--------|
| Severity | **Medium** |
| Asset | `backend/telegram_bot.py` `handle_update` |
| Issue | Auth check is `if manager_id and chat_id != manager_id`. If `TELEGRAM_ENABLED=true` but `TELEGRAM_MANAGER_CHAT_ID` is empty, **any** chat that can talk to the bot can drive approve/deny. |
| Mitigation | Fail closed: refuse polling/notifications unless chat id set; treat empty manager id as hard error at startup |
| Owner | `@backend.eng` |
| Status | **Mitigated** (2026-09-06) — `is_enabled()` requires token + manager chat id; handlers fail closed |

---

### LOW

#### SEC-07 — Prompt injection / policy fabrication

| Field | Detail |
|-------|--------|
| Severity | **Low** (MVP residual) |
| Asset | Crew agents + compose path |
| Issue | Adversarial prompts may try to invent policy. Mitigations: KB floor, refuse/escalate rules, guardrails, eval fixtures E-001/E-003. Not a guarantee under live LLM variance. |
| Mitigation | Keep `*run-evals --live`; expand adversarial set; human spot-check EC-005 |
| Status | Residual accepted for MVP |

#### SEC-08 — Prompt Trace `error_detail` may leak internals

| Field | Detail |
|-------|--------|
| Severity | **Low** |
| Asset | `write_prompt_trace(..., error=str(e))` in `backend/main.py` / streaming |
| Issue | Exception strings written under `LOG_DIR`. Message body truncated to 200 chars (good); raw exception text may include paths. Logs are gitignored. |
| Mitigation | Sanitize `error_detail` to error codes only in traces |
| Status | **Mitigated** (2026-09-06) — truncated + redacted `error_detail` in `write_prompt_trace` |

#### SEC-09 — Next.js approvals proxy path pass-through

| Field | Detail |
|-------|--------|
| Severity | **Low** |
| Asset | `frontend/app/api/approvals/[...path]/route.ts` |
| Issue | Forwards path segments to backend without an auth layer; expands attack surface to same-origin browser callers. Fixed `apiBase` limits SSRF to configured backend (good). |
| Mitigation | Auth at FE route or stop proxying `decide` to browsers |
| Status | **Mitigated** (2026-09-06) — rewrite removed; route injects key; rejects `..` segments |

---

### INFO (positive / no issue)

| ID | Control | Evidence |
|----|---------|----------|
| SEC-I01 | Secrets not committed | `.env` gitignored; `git check-ignore` OK |
| SEC-I02 | Secrets via env only | `llm_config.py`, Telegram token via `os.getenv` |
| SEC-I03 | SQLite queries parameterized | `tools.py` / `approval_service` use `?` placeholders; FTS via `_fts_escape` quoted tokens |
| SEC-I04 | CORS allowlist | localhost:3000 / 127.0.0.1:3000 only |
| SEC-I05 | XSS baseline | Chat reply rendered as React text (`whitespace-pre-wrap`), not `dangerouslySetInnerHTML` |
| SEC-I06 | Telegram chat allowlist when configured | Non-manager chats ignored when `TELEGRAM_MANAGER_CHAT_ID` set |
| SEC-I07 | Tool least privilege | YAML tools limited to kb_search / ticket_stub / stub lookups (eval EC-015) |

---

## Secret scan (`*scan-secrets`)

| Check | Result |
|-------|--------|
| `.env` tracked? | **No** (ignored) |
| Hardcoded live API keys in source | **None found** |
| Placeholder keys in docs | Present in `.env.example`, `RUNNING.md`, setup docs — OK |
| `support.db` / Prompt Trace logs tracked? | **No** (gitignore patterns present) |
| `forbid_committed_secrets` (example config) | Honored in repo hygiene |

---

## Dependency notes (`*review-deps`)

| Stack | Pin / range | Note |
|-------|-------------|------|
| FastAPI | `==0.109.0` | Dated pin — run `pip audit` / GitHub Dependabot before public deploy |
| CrewAI | `>=0.80.0,<1.0.0` | Wide minor range — lock exact version for reproducible prod |
| Next.js | `^15.1.0` | Keep patched; run `npm audit` |
| openai / httpx | requirements / transitive | Telegram uses httpx — keep TLS verify default |

MVP action: record audit command in Deliver runbook; not a code-change blocker for local demo.

---

## Mitigations checklist (no business-logic changes in this assessment)

| Priority | Action | Owner | Status |
|----------|--------|-------|--------|
| P0 | Gate `/api/approvals/*` + `/api/last-result` with `OPERATOR_API_KEY` | `@backend.eng` | **Done** |
| P0 | Telegram fail-closed without manager chat id | `@backend.eng` | **Done** |
| P1 | Bind `127.0.0.1` in `__main__`; FE proxy inject key | `@backend.eng` / `@frontend.eng` | **Done** |
| P2 | Rate-limit chat endpoints at reverse proxy | `@devops.eng` | Open (SEC-04) |
| P2 | `pip audit` / `npm audit` in CI | `@devops.eng` | Open |

---

## Alignment with evals / QA

- Eval EC-014/015 (trace redaction, tool allowlist): **pass** on static suite — does not cover HTTP auth gaps above.
- QA concurrent DoS / proxy hang: related to SEC-04; accepted demo limitation.
- AI disclosure (AC-01): present — transparency control, not access control.

---

## Sources

- `project-context/1.define/prd.md`, `sad.md` (§3 env, §4 Security, §9 EC-*)
- `project-context/2.build/qa.md`, `backend.md`, `frontend.md`, `integration.md`, `evals.md`
- `backend/main.py`, `tools.py`, `telegram_bot.py`, `chat_service.py`, `llm_config.py`
- `frontend/app/api/approvals/[...path]/route.ts`, `ChatWindow.tsx`
- `.gitignore`, `.env.example`
- `aamad.config.example.yml` (`security.require_security_assessment: true`)

## Assumptions

- **Deployment posture:** localhost demo (`127.0.0.1`). Chat endpoints remain open (SAD). Approvals/last-result require `OPERATOR_API_KEY` (mitigated 2026-09-06).
- **SEC-04** (LLM cost DoS) remains an **accepted residual** for open demo chat until reverse-proxy rate limits land in Deliver.
- HITL monetary actions are **stubs** (not live banking).
- Operator key is shared via root `.env` + `frontend/.env.local` (server-side only — never `NEXT_PUBLIC_`).
- Runtime = `crewai`; no MCP/shell tools in agent YAML.

## Open Questions

1. ~~Operator key on approvals~~ — **Resolved:** implemented.
2. Should HTTP `decide` remain (keyed) or Telegram-only for further surface reduction?
3. GDPR / Prompt Trace retention days still TBD (SAD OQ).
4. Deliver: add nginx/Caddy rate limit for `/api/chat*` (SEC-04)?

## Audit

| Field | Value |
|-------|-------|
| Timestamp | 2026-09-06T22:45:00-05:00 |
| Persona id | security-eng |
| Action | assess-security |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai |
| Verdict | CONDITIONAL PASS — localhost demo only; High auth gaps on approvals must not ship publicly unmitigated |
| Prompt Trace | Omitted — assessment artifact; no secret values recorded |
| Adapter rule | `.cursor/rules/adapter-crewai.mdc` |
| Next | Operator accept Assumptions **or** `@backend.eng` fix SEC-01–03/06; then `@devops.eng` `*prepare-release` |

### Audit (append)

| Field | Value |
|-------|-------|
| Timestamp | 2026-09-06T22:55:00-05:00 |
| Persona id | backend-eng / security-eng |
| Action | mitigate SEC-01,02,03,05,06,08,09 |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai |
| Verdict | **PASS (mitigated)** — operator key gates; Telegram fail-closed; localhost bind; trace sanitize |
| Change note | `backend/auth.py`; gated routes in `main.py`; FE approvals proxy injects key; removed approvals rewrite; env examples updated |
| Next | Restart backend + `npm run dev`; `@devops.eng` may proceed with SEC-04 noted |
