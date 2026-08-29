"""
Tools for Multi-Agent Customer Support Crew.
- kb_search: SQLite FTS5 retrieval over support.db (replaces CSV TF-IDF, SAD ADR-13)
- account_lookup: Stub account context for HITL demos
- order_lookup: Stub order context for HITL demos
- ticket_stub: In-memory stub ticket creation
"""
import json
import os
import sqlite3
import uuid
from typing import Any, Optional

from crewai.tools import BaseTool
from pydantic import Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared DB helper
# ─────────────────────────────────────────────────────────────────────────────

_db_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    """Lazy singleton SQLite connection."""
    global _db_conn
    if _db_conn is None:
        from backend.db import get_connection, ensure_database
        db_path = os.getenv("KB_DB_PATH", os.path.join("backend", "data", "support.db"))
        ensure_database(db_path)
        _db_conn = get_connection(db_path)
    return _db_conn


# ─────────────────────────────────────────────────────────────────────────────
# KBSearchTool — SQLite FTS5
# ─────────────────────────────────────────────────────────────────────────────

class KBSearchTool(BaseTool):
    """
    Knowledge Base Search Tool using SQLite FTS5 full-text search.
    Replaces CSV+TF-IDF; same RetrieverOutput contract (SAD ADR-13).
    """
    name: str = "kb_search"
    description: str = (
        "Search the B-Mobile knowledge base for relevant FAQ articles. "
        "Provide a query string and receive grounded passages with citations. "
        "Returns passages above similarity threshold or gap=true if none found."
    )

    similarity_floor: float = Field(default=0.35)
    top_k: int = Field(default=3)

    def __init__(self, **kwargs):
        similarity_floor = float(os.getenv("KB_SIMILARITY_FLOOR", "0.35"))
        top_k = int(os.getenv("KB_TOP_K", "3"))
        super().__init__(similarity_floor=similarity_floor, top_k=top_k, **kwargs)

    def _run(self, query: str, top_k: int = 3) -> str:
        """
        Search KB and return JSON string matching RetrieverOutput schema.
        Falls back to CSV+TF-IDF path via FileNotFoundError if DB unavailable.
        """
        if not query or not query.strip():
            return '{"passages": [], "citations": [], "gap": true}'

        effective_top_k = top_k or self.top_k

        try:
            conn = _get_conn()
            # FTS5 MATCH with BM25 ranking (lower rank = more relevant)
            rows = conn.execute(
                """
                SELECT a.id, a.title, a.body, bm25(kb_articles_fts) AS rank
                FROM kb_articles_fts
                JOIN kb_articles AS a ON a.rowid = kb_articles_fts.rowid
                WHERE kb_articles_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (_fts_escape(query), effective_top_k),
            ).fetchall()
        except sqlite3.Error as exc:
            raise FileNotFoundError(f"KB database unavailable: {exc}") from exc

        results = []
        for row in rows:
            # FTS5 bm25: more negative = better match. Map |bm25| into 0–1.
            raw_rank = float(row["rank"])
            score = min(1.0, abs(raw_rank) / 10.0)
            if score < self.similarity_floor:
                continue

            body = row["body"]
            snippet = body[:200] + "..." if len(body) > 200 else body
            results.append(
                {
                    "title": row["title"],
                    "snippet": snippet,
                    "score": round(score, 3),
                }
            )

        gap = len(results) == 0
        citations = [{"title": r["title"], "snippet": r["snippet"]} for r in results]
        return json.dumps({"passages": results, "citations": citations, "gap": gap}, indent=2)


_FTS_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "how",
        "do",
        "i",
        "my",
        "a",
        "an",
        "to",
        "of",
        "in",
        "on",
        "is",
        "your",
        "you",
        "what",
        "with",
        "or",
        "be",
        "at",
        "from",
    }
)


def _fts_escape(query: str) -> str:
    """
    Convert user query to a safe FTS5 MATCH expression.
    Content tokens are AND-combined so weak keyword overlap does not match.
    """
    import re
    cleaned = re.sub(r"[^\w\s]", " ", query)
    tokens = [
        t for t in cleaned.split()
        if len(t) >= 2 and t.lower() not in _FTS_STOP
    ]
    if not tokens:
        return '""'
    return " AND ".join(f'"{t}"' for t in tokens)


# ─────────────────────────────────────────────────────────────────────────────
# AccountLookupTool
# ─────────────────────────────────────────────────────────────────────────────

class AccountLookupTool(BaseTool):
    """
    Look up stub account context for HITL policy-action demos.
    Returns account details (plan, tenure, ETF, outage) as JSON.
    """
    name: str = "account_lookup"
    description: str = (
        "Look up B-Mobile stub account details by account ID (e.g. ACC-1001). "
        "Returns plan, tenure, ETF amount, outage flags and notes for policy decisions."
    )

    def _run(self, account_id: str) -> str:
        account_id = (account_id or "").strip().upper()
        if not account_id:
            return json.dumps({"found": False, "error": "No account ID provided"})
        try:
            conn = _get_conn()
            row = conn.execute(
                "SELECT * FROM stub_accounts WHERE id = ?", (account_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            return json.dumps({"found": False, "error": str(exc)})

        if not row:
            return json.dumps({"found": False, "account_id": account_id})

        return json.dumps(
            {
                "found": True,
                "account_id": row["id"],
                "plan": row["plan"],
                "tenure_years": row["tenure_years"],
                "balance_due": row["balance_due"],
                "etf_amount": row["etf_amount"],
                "outage_date": row["outage_date"],
                "security_flag": bool(row["security_flag"]),
                "notes": row["notes"],
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# OrderLookupTool
# ─────────────────────────────────────────────────────────────────────────────

class OrderLookupTool(BaseTool):
    """
    Look up stub order context for HITL refund/return demos.
    Returns order details (product, amount, purchase date, eligibility) as JSON.
    """
    name: str = "order_lookup"
    description: str = (
        "Look up B-Mobile stub order details by order ID (e.g. ORD-1001). "
        "Returns product, amount, purchase date, and refund eligibility."
    )

    def _run(self, order_id: str) -> str:
        order_id = (order_id or "").strip().upper()
        if not order_id:
            return json.dumps({"found": False, "error": "No order ID provided"})
        try:
            conn = _get_conn()
            row = conn.execute(
                "SELECT * FROM stub_orders WHERE id = ?", (order_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            return json.dumps({"found": False, "error": str(exc)})

        if not row:
            return json.dumps({"found": False, "order_id": order_id})

        return json.dumps(
            {
                "found": True,
                "order_id": row["id"],
                "account_id": row["account_id"],
                "product": row["product"],
                "amount": row["amount"],
                "purchase_date": row["purchase_date"],
                "eligible_for_refund": bool(row["eligible_for_refund"]),
                "notes": row["notes"],
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# TicketStubTool (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class TicketStubTool(BaseTool):
    """
    Stub ticket creation tool for escalations.
    Creates in-memory stub ticket with STUB- prefix.
    """
    name: str = "ticket_stub"
    description: str = (
        "Create a stub support ticket for escalated cases. "
        "Accepts escalation context and returns a stub ticket ID. "
        "This is a no-op stub for MVP - no live ticketing system integration."
    )

    def _run(self, context: str = "") -> str:
        return f"STUB-{uuid.uuid4().hex[:8].upper()}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool instances for crew configuration
# ─────────────────────────────────────────────────────────────────────────────

kb_search_tool = KBSearchTool()
account_lookup_tool = AccountLookupTool()
order_lookup_tool = OrderLookupTool()
ticket_stub_tool = TicketStubTool()
