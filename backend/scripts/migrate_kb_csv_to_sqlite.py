"""
One-time migration: seeds backend/data/support.db from backend/kb/articles.csv
and populates stub_accounts and stub_orders for HITL demos.

Run from project root:
    python -m backend.scripts.migrate_kb_csv_to_sqlite
"""
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.db import get_connection, init_db

CSV_PATH = os.path.join("backend", "kb", "articles.csv")

CATEGORY_MAP = {
    "01-account-pin": "account",
    "02-billing-invoice": "billing",
    "03-device-shipping": "orders",
    "04-returns-refunds": "orders",
    "05-plan-upgrade": "plans",
    "06-account-email": "account",
    "07-data-usage": "usage",
    "08-roaming": "usage",
    "09-esim": "devices",
    "10-lost-stolen": "devices",
    "11-number-porting": "account",
    "12-voicemail": "account",
}

STUB_ACCOUNTS = [
    {
        "id": "ACC-1001",
        "plan": "Unlimited 5G Plus",
        "tenure_years": 3,
        "balance_due": 0.0,
        "etf_amount": 0.0,
        "outage_date": "2026-08-20",
        "security_flag": 0,
        "notes": "Loyal customer; outage logged 2026-08-20; no ETF (contract ended)",
    },
    {
        "id": "ACC-2002",
        "plan": "Unlimited 4G Basic",
        "tenure_years": 1,
        "balance_due": 45.00,
        "etf_amount": 150.00,
        "outage_date": None,
        "security_flag": 0,
        "notes": "New customer; active contract with $150 ETF; no outage logged",
    },
    {
        "id": "ACC-3003",
        "plan": "Pay-As-You-Go",
        "tenure_years": 2,
        "balance_due": 0.0,
        "etf_amount": 0.0,
        "outage_date": None,
        "security_flag": 1,
        "notes": "Security flag raised; lost SIM reported 2026-08-15; requires ID verification",
    },
]

STUB_ORDERS = [
    {
        "id": "ORD-1001",
        "account_id": "ACC-1001",
        "product": "B-Mobile A55 handset",
        "amount": 299.00,
        "purchase_date": "2026-08-14",
        "eligible_for_refund": 1,
        "notes": "Within 14-day cooling-off; unused; original packaging",
    },
    {
        "id": "ORD-2002",
        "account_id": "ACC-2002",
        "product": "USB-C charging cable",
        "amount": 19.99,
        "purchase_date": "2026-07-01",
        "eligible_for_refund": 0,
        "notes": "Opened accessory; outside 14-day return window",
    },
    {
        "id": "ORD-3003",
        "account_id": "ACC-1001",
        "product": "B-Mobile S22 handset",
        "amount": 599.00,
        "purchase_date": "2026-06-01",
        "eligible_for_refund": 0,
        "notes": "Outside cooling-off period; device shows use",
    },
]


def migrate(db_path: str | None = None) -> None:
    print("Initialising database schema...")
    init_db(db_path)

    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()

    with conn:
        # ── KB articles ──────────────────────────────────────────────────────
        if not os.path.exists(CSV_PATH):
            print(f"WARNING: CSV not found at {CSV_PATH} — skipping KB migration")
        else:
            with open(CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            # Remove stale FTS entries before re-inserting
            conn.execute("DELETE FROM kb_articles")

            for row in rows:
                article_id = row["id"]
                conn.execute(
                    """
                    INSERT INTO kb_articles (id, title, body, category, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        article_id,
                        row["title"],
                        row["body"],
                        CATEGORY_MAP.get(article_id, "general"),
                        now,
                    ),
                )
            print(f"  Migrated {len(rows)} KB articles")
            try:
                conn.execute("INSERT INTO kb_articles_fts(kb_articles_fts) VALUES('rebuild')")
            except sqlite3.Error:
                pass

        # ── Stub accounts ─────────────────────────────────────────────────────
        for acc in STUB_ACCOUNTS:
            conn.execute(
                """
                INSERT OR REPLACE INTO stub_accounts
                (id, plan, tenure_years, balance_due, etf_amount, outage_date, security_flag, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    acc["id"],
                    acc["plan"],
                    acc["tenure_years"],
                    acc["balance_due"],
                    acc["etf_amount"],
                    acc["outage_date"],
                    acc["security_flag"],
                    acc["notes"],
                ),
            )
        print(f"  Seeded {len(STUB_ACCOUNTS)} stub accounts")

        # ── Stub orders ───────────────────────────────────────────────────────
        for order in STUB_ORDERS:
            conn.execute(
                """
                INSERT OR REPLACE INTO stub_orders
                (id, account_id, product, amount, purchase_date, eligible_for_refund, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["id"],
                    order["account_id"],
                    order["product"],
                    order["amount"],
                    order["purchase_date"],
                    order["eligible_for_refund"],
                    order["notes"],
                ),
            )
        print(f"  Seeded {len(STUB_ORDERS)} stub orders")

    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
