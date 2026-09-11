# Deploy Runbook — Multi-Agent Customer Support Crew (B-Mobile MVP)

**Persona**: `@devops.eng`  
**Actions**: `*prepare-release`, `*define-deploy`, `*document-deploy`  
**Product**: Multi-Agent Customer Support Crew for B-Mobile  
**Release version**: `0.1.0` (MVP course demo)  
**Resolved runtime**: `crewai` (`AAMAD_TARGET_RUNTIME=crewai`)

---

## Release gate (`*prepare-release`)

| Gate | Artifact | Status | Notes |
|------|----------|--------|-------|
| QA | `project-context/2.build/qa.md` | **PASS** | Live Path A (2026-08-26/27); FTS5 + Telegram HITL noted; concurrent kickoff gap accepted for single-user demo |
| Evals | `project-context/2.build/evals.md` | **MVP PASS** / **production_ready false** | Static+fixtures pass; live 2026-09-09 failed Path B/C + Path A p95 68.9s vs 30s |
| Security | `project-context/2.build/security.md` | **PASS (mitigated)** | Present — not an accepted gap. SEC-01–03/05/06/08/09 mitigated 2026-09-06. **SEC-04** (open chat cost/DoS) accepted residual for localhost |
| Config | `aamad.config.yml` | Absent | Honor `aamad.config.example.yml` prefs (`security.require_security_assessment: true` satisfied by security.md) |
| Runtime | Adapter | `crewai` | `.cursor/rules/adapter-crewai.mdc`; packaging uses Python + `backend/main.py` + YAML crew |

**Release scope (in)**  
- FastAPI + CrewAI 4-agent sequential crew (`backend/`)  
- Next.js chat UI + SSE + `/operator` projector (`frontend/`)  
- SQLite FTS5 KB + stub HITL / optional Telegram  
- Local dual-process runbook + optional Docker Compose packaging  
- Prompt Trace under `LOG_DIR`; health on `GET /health`

**Release scope (out / Future Work)**  
- Live CRM/ticketing, public TLS host, IaC, multi-region, APM/OTel dashboards  
- Reverse-proxy rate limits for `/api/chat*` (SEC-04)  
- CI auto-deploy to production; `user-guide.md` (pending `*document-user-guide`)  
- Concurrent multi-crew load beyond single synchronous kickoff

**Version summary**

| Component | Version / pin | Entrypoint |
|-----------|---------------|------------|
| Application | `0.1.0` | Dual process or Compose |
| Backend image | `bmobile-support-backend:0.1.0` | `python -m uvicorn backend.main:app` |
| Frontend image | `bmobile-support-frontend:0.1.0` | `npm run start` (Next.js 15) |
| Runtime | CrewAI (`>=0.80.0,<1.0.0`) | `backend/crew.py` + `config/*.yaml` |
| API surface | FastAPI `0.109.0` | `backend/main.py` (existing — not regenerated) |
| Python deps | `backend/requirements.txt` (existing) | Installed in backend image |

---

## Hosting approach (`*define-deploy`)

Per SAD §3: **smallest MVP target** = local dual process; optional two-container Compose for Week-6 demo packaging. No live cloud provision in this Deliver pass.

### A — Local (default)

| Node | Command (repo root) | Port | Health |
|------|---------------------|------|--------|
| Backend | `python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001` | `127.0.0.1:8001` | `GET /health` → `{status: ok}` |
| Frontend | `cd frontend && npm run dev` | `localhost:3000` | Load `/` |

Canonical operator steps (local + Compose): [`RUNNING.md`](../../RUNNING.md).

### B — Docker Compose (optional)

Artifacts created this Deliver:

| File | Role |
|------|------|
| `Dockerfile` | Python 3.11 + CrewAI/FastAPI backend |
| `frontend/Dockerfile` | Node 20 multi-stage Next.js production image |
| `docker-compose.yml` | Services `backend` + `frontend`; host binds `127.0.0.1` only |
| `.dockerignore` / `frontend/.dockerignore` | Lean build contexts |

```bash
# From repository root — requires filled .env (from .env.example)
docker compose up --build
docker compose down
```

| Service | Published | Internal |
|---------|-----------|----------|
| `backend` | `127.0.0.1:8001` | `0.0.0.0:8001` in container; frontend uses `http://backend:8001` |
| `frontend` | `127.0.0.1:3000` | Next listens on `3000` |

Volumes: Prompt Trace logs, SQLite `backend/data`, KB CSV (read-only).

**Packaging note:** Existing `backend/main.py` and `backend/requirements.txt` are the runtime sources of truth. Deliver did **not** rewrite application logic; images wrap those files for `crewai`.

---

## Environment variable matrix

Reference **names only** from `.env.example` / `frontend/.env.example`. Never commit secret values.

| Variable | Required | Default / example | Used by | Purpose |
|----------|----------|-------------------|---------|---------|
| `AAMAD_TARGET_RUNTIME` | Yes | `crewai` | Backend / Audit | Locked MVP runtime |
| `LLM_PROVIDER` | Yes | `ollama` or `openai` | Backend | Provider switch |
| `OLLAMA_API_KEY` | If ollama | _(operator)_ | Backend | Ollama Cloud key |
| `OLLAMA_BASE_URL` | If ollama | `https://ollama.com/v1` | Backend | API base |
| `OLLAMA_MODEL` | If ollama | e.g. `gemma4:31b` | Backend | Model id |
| `OPENAI_API_KEY` | If openai | _(operator)_ | Backend | OpenAI key |
| `OPENAI_MODEL_LOW` | Optional | `gpt-4o-mini` | Backend | Low tier (ADR-19) |
| `OPENAI_MODEL_MID` | Optional | `gpt-4o-mini` | Backend | Mid tier |
| `OPENAI_MODEL` | Optional | `gpt-4o-mini` | Backend | Fallback |
| `BACKEND_PORT` | Optional | `8001` | Backend | Listen port |
| `NEXT_PUBLIC_API_BASE_URL` | Yes | `http://127.0.0.1:8001` (local) / `http://backend:8001` (compose) | Frontend | Server proxy / rewrite target |
| `OPERATOR_API_KEY` | Yes for ops routes | _(operator; same in root + `frontend/.env.local`)_ | BE + FE proxy | `X-Operator-Key` for approvals + last-result |
| `MAX_ITER` | Optional | `12` | Crew | Agent iteration cap |
| `MAX_RPM` | Optional | `10` | Crew | Rate budget |
| `CHAT_TIMEOUT_SECONDS` | Optional | `180` | Backend | Crew wall-clock |
| `CLASSIFIER_CONFIDENCE_MIN` | Optional | `0.55` | Backend | Classify floor |
| `KB_DIR` / `KB_FILE` | Optional | `backend/kb` / `articles.csv` | Backend | CSV seed |
| `KB_SIMILARITY_FLOOR` | Optional | `0.35` | Backend | Retrieval floor |
| `KB_DB_PATH` | Optional | `backend/data/support.db` | Backend | SQLite FTS5 + stubs |
| `KB_TOP_K` | Optional | `3` | Backend | Top hits |
| `TELEGRAM_ENABLED` | Optional | `false` | Backend | HITL bot |
| `TELEGRAM_BOT_TOKEN` | If Telegram | _(operator)_ | Backend | Bot token |
| `TELEGRAM_MANAGER_CHAT_ID` | If Telegram | _(operator)_ | Backend | Allow-listed chat |
| `HITL_TIMEOUT_SECONDS` | Optional | `300` | Backend | Approval wait |
| `LOG_DIR` | Optional | `project-context/2.build/logs` | Backend | Prompt Trace |
| `CREWAI_TRACING_ENABLED` | Optional | `true` | Backend | Optional AMP dashboard |
| `EVAL_JUDGE_MODEL` / `EVAL_JUDGE_API_KEY` | Optional | — | Evals only | EC-005 judge |

Compose injects `OPERATOR_API_KEY` into the frontend service from the host environment / `.env`.

---

## Install, start, stop, roll back (`*document-deploy`)

### Prerequisites

- Python 3.10+ (3.11 recommended for Docker match) with venv  
- Node.js ≥ 20 and npm  
- LLM credentials for chosen `LLM_PROVIDER`  
- Optional: Docker Desktop / Compose v2 for container path  
- Optional: Telegram bot credentials if `TELEGRAM_ENABLED=true`

### Install (local)

```bash
# Backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Unix: source .venv/bin/activate
pip install -r backend/requirements.txt
copy .env.example .env   # then fill secrets — do not commit .env

# Frontend
cd frontend
npm ci
copy .env.example .env.local   # align NEXT_PUBLIC_API_BASE_URL + OPERATOR_API_KEY
cd ..
```

Seed KB (also runs on backend startup):

```bash
python -m backend.scripts.migrate_kb_csv_to_sqlite
```

### Start (local)

```bash
# Terminal A — bind localhost only (SEC-05)
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001

# Terminal B
cd frontend && npm run dev
```

Verify: `http://127.0.0.1:8001/health`, then `http://localhost:3000`.

### Stop (local)

- Ctrl+C both processes  
- Ensure a single uvicorn (avoid DEF-INT-08 duplicate listeners)  
- Prefer port **8001** when **8000** is contested (DEF-INT-01)

### Start / stop (Compose)

```bash
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8001/health
docker compose logs -f backend
docker compose down          # stop
docker compose down -v       # stop; keep named volumes policy — this compose uses bind mounts
```

### Roll back

1. **Config / image**: `git checkout <known-good-tag-or-commit>`; rebuild Compose images or reinstall `pip`/`npm` pins from that revision.  
2. **Runtime data**: Restore `backend/data/support.db` from a pre-change copy if KB/HITL state must rewind; re-seed from `backend/kb/articles.csv` if needed.  
3. **Secrets**: Rotate `OPERATOR_API_KEY` / provider keys if a bad deploy leaked env files (keys never live in git).  
4. **Smoke after rollback**: `GET /health`; Path A PIN query via UI or `POST /api/chat`; optional `python -m evals.run --static --fixtures`.

No automated production promote/rollback pipeline — manual only until operator authorizes CI/CD live deploy.

---

## Access control (MVP)

| Surface | Posture |
|---------|---------|
| `POST /api/chat`, `POST /api/chat/stream` | **Open** for local demo (SAD) — do not publish to the internet without rate limits (SEC-04) |
| `/api/approvals/*`, `GET /api/last-result` | **`OPERATOR_API_KEY`** via `X-Operator-Key`; unset → **503** (fail closed) |
| Next.js approvals proxy | Injects operator key **server-side**; never expose as `NEXT_PUBLIC_*` |
| Telegram HITL | Requires bot token **and** manager chat id; refuse start if incomplete |
| Bind address | Local/__main__: `127.0.0.1`; Compose host publish: `127.0.0.1:3000` / `127.0.0.1:8001` |
| CORS | `localhost:3000` / `127.0.0.1:3000` allowlist |
| Secrets | Env only; `.env` gitignored; Prompt Trace redacts/truncates |

Enterprise IAM/SSO/network segmentation = Future Work.

---

## Monitoring / logging overview

Aligned with evals.md §7 Production Monitoring Recommendations and SAD §4 Observability.

### MVP signals (shipped)

| Signal | Mechanism |
|--------|-----------|
| Liveness | `GET /health` |
| Per-run audit | `trace_id` + Prompt Trace JSON under `LOG_DIR` |
| Pipeline | `steps[]` + SSE `stage` events; `/operator` for HITL |
| Escalation | `reason_codes` + packet / stub ticket |
| App logs | uvicorn + crew stdout |
| Optional AMP | `CREWAI_TRACING_ENABLED` → app.crewai.com after `crewai login` |

### Trace fields to retain (ops)

- `trace_id`, `LLM_PROVIDER` / resolved model, `decision`, `reason_codes`  
- Wall-clock latency; stop reason (`success` \| `timeout` \| `llm_error` \| `kb_unavailable` \| `customer_request_human`)  
- Tool outcomes: `kb_search` hit/miss, `ticket_stub` id  

### Suggested alert thresholds (not wired — document for Future Work)

| Condition | Severity |
|-----------|----------|
| Error rate > 5% over 15m | Alert |
| p95 latency > `CHAT_TIMEOUT_SECONDS` (180s) | Hard infra |
| Path A p95 latency > 30s | **Production fail / page** (evals EC-006); MVP soft warning |
| Token/cost spike > 150% of baseline | Alert when token metrics exist |

### Dependency audit (operator)

```bash
pip audit -r backend/requirements.txt
cd frontend && npm audit
```

Record results before any public host. Full OTel/Langfuse APM = Future Work.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| FE health/chat hits wrong service / 404 | Port 8000 conflict (DEF-INT-01) | Use `8001`; one uvicorn; align `NEXT_PUBLIC_API_BASE_URL` |
| `decision=escalate`, empty `steps[]`, LLM not found | Bad `OLLAMA_MODEL` / provider | Set model confirmed on provider; restart backend |
| Approvals / last-result **503** | Missing `OPERATOR_API_KEY` | Set same key in root `.env` and `frontend/.env.local`; restart both |
| Telegram never starts | Incomplete HITL env | Need `TELEGRAM_ENABLED=true` + token + manager chat id |
| Compose FE cannot reach API | Wrong API base | Build arg / env `NEXT_PUBLIC_API_BASE_URL=http://backend:8001` |
| Concurrent chat hang / proxy reset | Single-threaded kickoff (QA gap / SEC-04) | Serialize demos; do not load-test MVP |
| Windows EventBus encoding noise | Console code page | `$env:PYTHONIOENCODING='utf-8'` before uvicorn |
| No Prompt Trace file | Failed early / wrong `LOG_DIR` | Confirm writable `project-context/2.build/logs` (Compose volume mounted) |

Demo script and deeper run notes: [`RUNNING.md`](../../RUNNING.md).

---

## Future Work (ops)

- Reverse-proxy rate limit on `/api/chat*` (SEC-04) before any public URL  
- `*configure-cicd` — lint (`next lint` / `tsc`), `npm run build`, `pip audit` / pytest, eval static job  
- `*document-user-guide` → `project-context/3.deliver/user-guide.md`  
- TLS + single-VM public host only with explicit operator authorization  
- OTel / Phoenix or Langfuse; token cost dashboards; multi-replica crew queue  

---

## Sources

- `project-context/1.define/prd.md` (MVP scope, AC-01…06, runtime lock)  
- `project-context/1.define/sad.md` §3 Deployment, §4 Observability / Security  
- `project-context/2.build/qa.md`, `evals.md`, `security.md`, `backend.md`, `frontend.md`, `integration.md`  
- `.env.example`, `frontend/.env.example`, `RUNNING.md`  
- `.cursor/agents/devops-eng.md`, `.cursor/rules/adapter-crewai.mdc`, `.cursor/rules/delivery-workflow.mdc`  
- `aamad.config.example.yml` (`security.require_security_assessment: true`)  
- Packaging: `Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `backend/main.py`, `backend/requirements.txt`

## Assumptions

- Operator accepts localhost / Compose-on-localhost posture; chat remains open by design.  
- **security.md is present** (PASS mitigated); SEC-04 residual accepted for demo — not treated as missing-assessment gap.  
- **evals.md is present**; monitoring section above translates §7 recommendations (alerts not yet automated).  
- No `aamad.config.yml` in repo — example config preferences applied where relevant.  
- Hosting target for this Deliver: local workstation (± Docker Desktop); ports **3000** / **8001**; health `GET /health`.  
- Live cloud deploy **not** authorized — configs and runbook only.  
- `backend/main.py` and `backend/requirements.txt` pre-existed; Deliver wraps them rather than regenerating business logic.

## Open Questions

1. Should Deliver add nginx/Caddy rate limits for `/api/chat*` before any non-localhost demo (security.md OQ / SEC-04)?  
2. Preferred CI cadence for `evals.run --static --fixtures` (each PR vs nightly)?  
3. Authorize a public single-VM host + TLS in a follow-up Deliver, or remain local-only for the course?  
4. Proceed with `*document-user-guide` and `*configure-cicd` in the next DevOps pass?  
5. GDPR / Prompt Trace retention days still TBD (SAD / security OQ).

## Audit

| Field | Value |
|-------|-------|
| Timestamp | 2026-09-06T23:04:46-05:00 |
| Persona id | devops-eng |
| Action | prepare-release + define-deploy + document-deploy |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai (env + `.env` + adapter default) |
| QA gate | PASS (`qa.md`) |
| Security gate | Present — PASS (mitigated); SEC-04 accepted residual |
| Evals gate | Present — course PASS (static + fixtures) |
| Artifacts written | `Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `.dockerignore`, `frontend/.dockerignore`, `project-context/3.deliver/deploy.md`; `.env.example` + `CHAT_TIMEOUT_SECONDS` |
| Prompt Trace | Omitted — packaging/runbook only; no LLM prompts; no secret values |
| Adapter rule | `.cursor/rules/adapter-crewai.mdc` |
| Live deploy | Not executed (operator authorization required) |
| Next | Optional `*configure-cicd`, `*document-user-guide`; operator may `docker compose up --build` or continue via `RUNNING.md` |

### Audit (append)

| Field | Value |
|-------|-------|
| Timestamp | 2026-09-06T23:23:49-05:00 |
| Persona id | devops-eng |
| Action | document-sync (RUNNING.md + README MVP run section; push packaging) |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai |
| Change note | Docs aligned for local + Compose URLs; Docker artifacts committed |
| Prompt Trace | Omitted — docs only; no secrets |

### Audit (append)

| Field | Value |
|-------|-------|
| Timestamp | 2026-09-10T21:25:00-05:00 |
| Persona id | qa-eng |
| Action | run-evals (production Path A p95 alert) |
| Resolved `AAMAD_TARGET_RUNTIME` | crewai |
| Change note | Path A p95 &gt; 30s is a production fail (was MVP warning-only) |
