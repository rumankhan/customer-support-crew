"""
Eval gate profiles for the B-Mobile support crew.

MVP numbers come from operator answers 2026-09-06 (OQ #11–#13).
Production numbers are PRD/SAD values promoted to course gates — not fitted
to a prototype score. Cost stays control-only: PRD §7 has no $/ticket figure.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional

# PRD §5 / SAD §4 Reliability — automated FAQ path (Path A), excluding HITL wait.
PATH_A_P95_MS = float(os.getenv("EVAL_PRODUCTION_P95_MS", "30000"))
CHAT_TIMEOUT_SECONDS = float(os.getenv("CHAT_TIMEOUT_SECONDS", "180"))
LATENCY_CATEGORIES = frozenset({"path_a_resolve"})
PROFILES = frozenset({"mvp", "production"})


def resolve_profile(explicit: Optional[str] = None) -> str:
    raw = (explicit or os.getenv("EVAL_PROFILE") or "production").strip().lower()
    if raw not in PROFILES:
        return "production"
    return raw


def profile_config(name: str) -> Dict[str, Any]:
    if name == "mvp":
        return {
            "name": "mvp",
            "require_live_for_ready": False,
            "live_fails_course_pass": False,
            "latency_course_pass": False,
            "path_a_p95_ms": PATH_A_P95_MS,
            "chat_timeout_seconds": CHAT_TIMEOUT_SECONDS,
            "cost": "control_only",
            "judge_blocks": False,
        }
    return {
        "name": "production",
        "require_live_for_ready": True,
        "live_fails_course_pass": True,
        "latency_course_pass": True,
        "path_a_p95_ms": PATH_A_P95_MS,
        "chat_timeout_seconds": CHAT_TIMEOUT_SECONDS,
        "cost": "control_only",
        "judge_blocks": False,
    }


def nearest_rank_percentile(values: List[float], percentile: float) -> Optional[float]:
    """Inclusive nearest-rank percentile (p in 0–100). Empty → None."""
    if not values:
        return None
    xs = sorted(float(v) for v in values)
    k = max(1, math.ceil((percentile / 100.0) * len(xs)))
    return xs[k - 1]


def path_a_latencies(live_section: Dict[str, Any]) -> List[float]:
    out: List[float] = []
    for item in live_section.get("items") or []:
        if item.get("category") != "path_a_resolve":
            continue
        grade = item.get("grade") or {}
        ms = grade.get("latency_ms")
        if isinstance(ms, (int, float)):
            out.append(float(ms))
    return out


def live_latency_gate(live_section: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """EC-006 Path A p95 and EC-008 timeout. HITL Path C is excluded from p95."""
    latencies = path_a_latencies(live_section)
    p95 = nearest_rank_percentile(latencies, 95)
    timeout_ms = float(cfg["chat_timeout_seconds"]) * 1000.0
    over_timeout = [
        {"id": item.get("id"), "latency_ms": (item.get("grade") or {}).get("latency_ms")}
        for item in live_section.get("items") or []
        if isinstance((item.get("grade") or {}).get("latency_ms"), (int, float))
        and float((item.get("grade") or {})["latency_ms"]) > timeout_ms
    ]
    p95_ok = p95 is None or p95 < float(cfg["path_a_p95_ms"])
    timeout_ok = len(over_timeout) == 0
    graded = bool(cfg.get("latency_course_pass"))
    return {
        "ec": "EC-006",
        "category": "path_a_resolve",
        "n": len(latencies),
        "p95_ms": p95,
        "threshold_ms": float(cfg["path_a_p95_ms"]),
        "p95_ok": p95_ok,
        "ec008_timeout_ok": timeout_ok,
        "over_timeout": over_timeout,
        "graded": graded,
        "pass": (p95_ok and timeout_ok) if graded else True,
        "note": (
            "Path A p95 is a production course gate (PRD §5). "
            "Path C / HITL wait is excluded. EC-007 TTFB remains monitoring until an SSE harness exists."
        ),
    }


def evaluate_gates(sections: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    course_pass  — gate for this profile's requested sections
    production_ready — promotion bar (static + fixtures + live + Path A p95)
    """
    static_ok = bool((sections.get("static") or {}).get("pass")) if "static" in sections else False
    fixtures_ok = bool((sections.get("fixtures") or {}).get("pass")) if "fixtures" in sections else False
    live = sections.get("live")
    live_ran = isinstance(live, dict) and "items" in live and not live.get("error")
    live_ok = bool(live.get("pass")) if live_ran else False

    latency = None
    latency_ok = True
    latency_ready_ok = True
    if live_ran:
        prod_slo = live_latency_gate(live, profile_config("production"))
        latency_ready_ok = bool(prod_slo["pass"])
        latency_ok = latency_ready_ok if cfg.get("latency_course_pass") else True
        latency = dict(prod_slo)
        latency["graded"] = bool(cfg.get("latency_course_pass"))
        latency["pass"] = latency_ok
        latency["production_pass"] = latency_ready_ok
        live = dict(live)
        live["latency_slo"] = latency
        sections["live"] = live

    blockers: List[str] = []
    if "static" in sections and not static_ok:
        blockers.append("static")
    if "fixtures" in sections and not fixtures_ok:
        blockers.append("fixtures")
    if live_ran and not live_ok:
        blockers.append("live_items")
    if live_ran and not latency_ready_ok:
        blockers.append("path_a_p95_or_timeout")
    if not live_ran:
        blockers.append("live_not_run")

    course = True
    if "static" in sections:
        course = course and static_ok
    if "fixtures" in sections:
        course = course and fixtures_ok
    if live_ran and cfg.get("live_fails_course_pass"):
        course = course and live_ok and latency_ok
    # Health-error live section does not fail MVP course pass; it does block production_ready.
    if live and live.get("error") and cfg.get("live_fails_course_pass") and cfg.get("require_live_for_ready"):
        # --live explicitly requested but API down: fail production course pass
        course = False
        if "live_not_run" not in blockers:
            blockers.append("live_unavailable")

    production_ready = (
        static_ok
        and fixtures_ok
        and live_ran
        and live_ok
        and latency_ready_ok
    )
    return {
        "course_pass": course,
        "production_ready": production_ready,
        "blockers": blockers,
        "latency_slo": latency,
    }
