"""
Quick validation for SQLite FTS KB + HITL heuristics (no LLM).
Run from project root: python -m backend.scripts.validate_kb_hitl
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.db import ensure_database
from backend.tools import KBSearchTool
from backend.approval_service import detect_policy_action


def main() -> int:
    ensure_database()
    tool = KBSearchTool()

    pin = json.loads(tool._run("How do I reset my B-Mobile My Account PIN?"))
    print("Path A (PIN):", "HIT" if not pin["gap"] else "MISS", [p["title"] for p in pin["passages"]])
    if pin["gap"] or not any("PIN" in p["title"] or "pin" in p["title"].lower() for p in pin["passages"]):
        print("FAIL: expected PIN article")
        return 1

    miss = json.loads(tool._run("What is your quantum warranty for the hardware drone?"))
    print("Path B (gap):", "GAP" if miss["gap"] else "UNEXPECTED HIT", [p["title"] for p in miss["passages"]])
    if not miss["gap"]:
        print("FAIL: expected retrieval gap")
        return 1

    credit = detect_policy_action(
        "Apply a $25 credit to ACC-1001 for the outage last week",
        "billing credit",
        ["ACC-1001"],
    )
    print("HITL credit:", credit)
    if not credit or credit["action_kind"] != "billing_credit":
        print("FAIL: expected billing_credit")
        return 1

    etf = detect_policy_action(
        "Cancel my plan and waive the $150 ETF on ACC-2002",
        "etf waiver",
        ["ACC-2002"],
    )
    print("HITL ETF:", etf)
    if not etf or etf["action_kind"] != "etf_waiver":
        print("FAIL: expected etf_waiver")
        return 1

    vague_credit = detect_policy_action("credit for outage", "billing", [])
    print("HITL vague credit:", vague_credit)
    if (
        not vague_credit
        or vague_credit["action_kind"] != "billing_credit"
        or vague_credit.get("lookup_number") is None
        or not (1 <= int(vague_credit["lookup_number"]) <= 100)
    ):
        print("FAIL: expected billing_credit with lookup 1-100")
        return 1

    vague_fee = detect_policy_action("can you waive my fee", "waiver", [])
    print("HITL vague fee:", vague_fee)
    if (
        not vague_fee
        or vague_fee["action_kind"] != "etf_waiver"
        or vague_fee.get("lookup_number") is None
    ):
        print("FAIL: expected etf_waiver with lookup number")
        return 1

    info = detect_policy_action("What is your return policy?", "returns", [])
    print("Info-only:", info)
    if info is not None:
        print("FAIL: info-only should not HITL")
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
