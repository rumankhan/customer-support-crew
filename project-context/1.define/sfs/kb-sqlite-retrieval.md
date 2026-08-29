# SFS: KB SQLite FTS5 Retrieval

**Feature ID:** SFS-KB-002  
**Status:** Implemented (MVP)  
**PRD anchor:** AC-03 — Grounded answers with refusal  
**SAD anchor:** ADR-13 — KB retrieval with similarity floor; updated to SQLite+FTS5

---

## Purpose

Replace the CSV-backed TF-IDF knowledge base with a SQLite FTS5 database for improved maintainability, zero-server footprint, and support for shared DB access (approvals + stub accounts in same file).

---

## Scope (MVP)

- **In scope:** SQLite FTS5 retrieval replacing CSV TF-IDF; same `RetrieverOutput` contract; migration script; shared `support.db` for KB + approvals + stubs.
- **Out of scope:** Vector embeddings, semantic search, remote database, admin UI for KB editing.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| Search query string | `retrieve_knowledge` task | From classifier intent + entities |
| `KB_DB_PATH` | env | Path to `support.db` (default: `backend/data/support.db`) |
| `KB_SIMILARITY_FLOOR` | env | Score threshold 0–1 (default: 0.35) |
| `KB_TOP_K` | env | Max passages returned (default: 3) |

---

## Schema

```sql
-- Content table
CREATE TABLE kb_articles (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  category TEXT,
  updated_at TEXT
);

-- FTS5 virtual table (content-backed)
CREATE VIRTUAL TABLE kb_articles_fts USING fts5(
  id UNINDEXED,
  title,
  body,
  content='kb_articles',
  content_rowid='rowid'
);
```

---

## Migration

Script: `backend/scripts/migrate_kb_csv_to_sqlite.py`

1. Reads `backend/kb/articles.csv` (12 B-Mobile FAQs)
2. Creates `backend/data/support.db` if not exists
3. Runs `CREATE TABLE IF NOT EXISTS` for all tables
4. Inserts/replaces all CSV rows into `kb_articles`
5. Populates FTS5 index via trigger or rebuild
6. Seeds `stub_accounts` table with demo data
7. Idempotent — safe to run multiple times

---

## Processing

`KBSearchTool._run(query)` in `backend/tools.py`:

1. Open SQLite connection (lazy singleton on `KB_DB_PATH`)
2. Query FTS5: `SELECT id, title, body, rank FROM kb_articles_fts WHERE kb_articles_fts MATCH ? ORDER BY rank LIMIT ?`
3. Normalize FTS BM25 to 0–1: `score = min(1.0, abs(rank) / 10.0)` (more negative BM25 = better match)
4. Filter: `score >= KB_SIMILARITY_FLOOR`
5. Build `passages` and `citations` lists
6. Return JSON matching `RetrieverOutput` schema

---

## Output Contract (unchanged)

`RetrieverOutput`:
```json
{
  "passages": [{"title": "...", "snippet": "...", "score": 0.72}],
  "citations": [{"title": "...", "snippet": "..."}],
  "gap": false
}
```

No changes to `backend/config/tasks.yaml` or `backend/models.py` RetrieverOutput.

---

## Demo Paths (must still pass after migration)

| Path | Query | Expected |
|------|-------|---------|
| A (hit) | "How do I reset my B-Mobile My Account PIN?" | passages from `01-account-pin`, gap=false |
| B (miss) | "What is your quantum warranty for hardware drones?" | gap=true |
| C (escalate) | "I'd rather talk to a person" | handled by request_human flag, not KB |

---

## Acceptance Criteria

| ID | Condition |
|----|-----------|
| KB-AC-01 | Path A PIN query returns passages from `01-account-pin`, `gap=false` |
| KB-AC-02 | Path B “quantum warranty” returns `gap=true` |
| KB-AC-03 | `RetrieverOutput` JSON shape unchanged (passages, citations, gap) |
| KB-AC-04 | Missing DB file maps to `kb_unavailable` (same as former CSV miss) |
| KB-AC-05 | Migration script is idempotent and seeds stub accounts/orders |
| KB-AC-06 | `articles.csv` remains as canonical export; live retrieval uses SQLite FTS5 |

## Validations

| Condition | Handling |
|-----------|----------|
| DB file not found | `FileNotFoundError` → `kb_unavailable` error code (same as CSV path) |
| Empty FTS result | `gap=true`, no passages |
| FTS rank normalization < floor | Filtered out; gap=true if all filtered |
| Concurrent access | SQLite WAL mode; read-only for KB queries |

---

## Env Vars

| Variable | Default | Description |
|----------|---------|-------------|
| `KB_DB_PATH` | `backend/data/support.db` | Shared SQLite database path |
| `KB_SIMILARITY_FLOOR` | `0.35` | Minimum score to include passage |
| `KB_TOP_K` | `3` | Max passages returned |

Old vars (`KB_DIR`, `KB_FILE`) remain for backwards compat but are superseded by `KB_DB_PATH`.

---

## Sources
- PRD §3 AC-03a: resolve path includes `sources_used`
- SAD ADR-13: KB retrieval with similarity floor 0.35
- `backend/kb/articles.csv` — 12 B-Mobile FAQ articles (source of truth for migration)

## Assumptions
- `backend/data/support.db` is gitignored (`*.sqlite`, `*.db` patterns)
- `backend/kb/articles.csv` kept as canonical export reference
- FTS5 rank normalization may need tuning after side-by-side test vs TF-IDF

## Open Questions
- FTS rank → 0–1 mapping formula: adjust `abs(rank) / 10.0` if relevance differs from TF-IDF
- Should we keep sklearn TF-IDF as hybrid fallback? (Not implemented; defer if FTS quality is sufficient)

## Audit
- Persona: @backend.eng
- Action: create-sfs (KB SQLite FTS5 retrieval)
- Timestamp: 2026-08-28
- Runtime: crewai (kb_search tool refactored in-place; RetrieverOutput contract unchanged)
