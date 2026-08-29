# B-Mobile seed knowledge base

Canonical export: **`articles.csv`** (one FAQ per row). English, fictional consumer carrier.

Columns: `id`, `title`, `body`. Quote fields that contain commas.

Live retrieval uses **SQLite FTS5** in `backend/data/support.db` (seeded from this CSV).

```bash
python -m backend.scripts.migrate_kb_csv_to_sqlite
```

The frontend mock `GET /api/kb` still serves this CSV for offline demos. Live chat uses crew `kb_search`.

**Path A (hit):** `How do I reset my B-Mobile My Account PIN?`  
**Path B (miss):** `What is your quantum warranty for the hardware drone?`  
**Path C:** customer checks **I'd rather talk to a person** (any message).  
**HITL:** `Apply a $25 credit to ACC-1001…` / `credit for outage` — manager decides in Telegram (not this CSV).
