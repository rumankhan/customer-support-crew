# B-Mobile knowledge base — CSV seed vs SQLite live

## Clear split (read this first)

| | **You edit** | **The app searches** |
|---|--------------|----------------------|
| **What** | FAQ text | Full-text index |
| **Where** | `backend/kb/articles.csv` | `backend/data/support.db` (SQLite **FTS5**) |
| **When used** | Authoring, git, re-seed | Every live `kb_search` in the crew |
| **ADR** | Seed/export | **ADR-20** (replaces ADR-13 TF-IDF-over-CSV for live path) |

```text
articles.csv  --seed/migrate-->  support.db (FTS5)  --kb_search-->  grounded passages
     ^ edit here                      ^ runtime only
```

- **Do** change FAQs in the CSV, then restart the backend (or run migrate).
- **Do not** expect chat to read the CSV directly — live chat never opens `articles.csv` for search.
- **CSV columns:** `id`, `title`, `body` (RFC4180; quote fields with commas). English, fictional B-Mobile carrier.

```bash
python -m backend.scripts.migrate_kb_csv_to_sqlite
```

`ensure_database()` on API startup also creates/seeds `support.db` from this CSV.

The frontend mock `GET /api/kb` may still read the CSV for offline FE stubs. Live chat uses crew `kb_search` → SQLite only.

**Path A (hit):** `How do I reset my B-Mobile My Account PIN?`  
**Path B (miss):** `What is your quantum warranty for the hardware drone?`  
**Path C:** customer checks **I'd rather talk to a person** (any message).  
**HITL:** `Apply a $25 credit to ACC-1001…` / `credit for outage` — manager decides in Telegram (not this CSV).
