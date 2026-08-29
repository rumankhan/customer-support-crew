"""
SQLite database layer for B-Mobile support app.
Manages KB articles (FTS5), stub accounts/orders, and HITL approval requests.
All tables share a single backend/data/support.db file.
"""
import os
import sqlite3
from typing import Optional

# Default DB path; override via KB_DB_PATH env var
DEFAULT_DB_PATH = os.path.join("backend", "data", "support.db")


def get_db_path() -> str:
    return os.getenv("KB_DB_PATH", DEFAULT_DB_PATH)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and row_factory set."""
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    conn = get_connection(db_path)
    with conn:
        # ── KB articles ──────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_articles (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                body       TEXT NOT NULL,
                category   TEXT,
                updated_at TEXT
            )
        """)

        # FTS5 virtual table backed by kb_articles
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS kb_articles_fts USING fts5(
                id   UNINDEXED,
                title,
                body,
                content='kb_articles',
                content_rowid='rowid'
            )
        """)

        # Triggers to keep FTS index in sync with kb_articles
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS kb_articles_ai
            AFTER INSERT ON kb_articles BEGIN
                INSERT INTO kb_articles_fts(rowid, id, title, body)
                VALUES (new.rowid, new.id, new.title, new.body);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS kb_articles_ad
            AFTER DELETE ON kb_articles BEGIN
                INSERT INTO kb_articles_fts(kb_articles_fts, rowid, id, title, body)
                VALUES ('delete', old.rowid, old.id, old.title, old.body);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS kb_articles_au
            AFTER UPDATE ON kb_articles BEGIN
                INSERT INTO kb_articles_fts(kb_articles_fts, rowid, id, title, body)
                VALUES ('delete', old.rowid, old.id, old.title, old.body);
                INSERT INTO kb_articles_fts(rowid, id, title, body)
                VALUES (new.rowid, new.id, new.title, new.body);
            END
        """)

        # ── Stub accounts ─────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stub_accounts (
                id            TEXT PRIMARY KEY,
                plan          TEXT NOT NULL,
                tenure_years  INTEGER NOT NULL DEFAULT 0,
                balance_due   REAL NOT NULL DEFAULT 0.0,
                etf_amount    REAL NOT NULL DEFAULT 0.0,
                outage_date   TEXT,
                security_flag INTEGER NOT NULL DEFAULT 0,
                notes         TEXT
            )
        """)

        # ── Stub orders ───────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stub_orders (
                id                  TEXT PRIMARY KEY,
                account_id          TEXT,
                product             TEXT NOT NULL,
                amount              REAL NOT NULL,
                purchase_date       TEXT NOT NULL,
                eligible_for_refund INTEGER NOT NULL DEFAULT 1,
                notes               TEXT
            )
        """)

        # ── HITL approval requests ────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS approval_requests (
                id                  TEXT PRIMARY KEY,
                session_id          TEXT,
                trace_id            TEXT,
                action_kind         TEXT NOT NULL,
                subject_id          TEXT NOT NULL,
                amount              REAL,
                reason              TEXT,
                context_json        TEXT,
                status              TEXT NOT NULL DEFAULT 'pending'
                                        CHECK(status IN ('pending','approved','denied')),
                operator_note       TEXT,
                decided_by          TEXT,
                telegram_message_id INTEGER,
                created_at          TEXT NOT NULL,
                decided_at          TEXT
            )
        """)

    conn.close()


def ensure_database(db_path: Optional[str] = None) -> None:
    """Create schema and seed KB/stubs if the articles table is empty."""
    path = db_path or get_db_path()
    init_db(path)
    conn = get_connection(path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM kb_articles").fetchone()["n"]
    finally:
        conn.close()
    if count == 0:
        from backend.scripts.migrate_kb_csv_to_sqlite import migrate
        migrate(path)
