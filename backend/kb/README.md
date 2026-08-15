# B-Mobile seed knowledge base

Canonical corpus: **`articles.csv`** (one FAQ per row). English, fictional consumer carrier.

Columns: `id`, `title`, `body`. Quote fields that contain commas.

CrewAI `kb_search` (when the backend exists) should load this file. Until then the frontend stub reads it through mock `GET /api/kb` and `frontend/lib/kb.ts`.

**Path A (hit):** `How do I reset my B-Mobile My Account PIN?`  
**Path B (miss):** `What is your quantum warranty for the hardware drone?`  
**Path C:** customer checks **I'd rather talk to a person** (any message).
