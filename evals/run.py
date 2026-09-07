#!/usr/bin/env python3
"""
Eval runner for B-Mobile Multi-Agent Customer Support Crew.

Usage (from repo root):
  python -m evals.run --static
  python -m evals.run --live --base-url http://127.0.0.1:8001
  python -m evals.run --fixtures
  python -m evals.run --all

Implements SAD §9 EC-* contract. Latency ECs are monitoring-only (operator OQ#13d).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from evals.checks.config_checks import run_config_checks
from evals.checks.response_checks import grade_response
from evals.judge.faithfulness import judge_faithfulness

DATASET_DIR = Path(__file__).parent / "dataset"
RESULTS_DIR = Path(__file__).parent / "results"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_dataset() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for path in sorted(DATASET_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def post_chat(base_url: str, message: str, request_human: bool, timeout: float) -> tuple[Dict[str, Any], float]:
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/api/chat"
    body = json.dumps({
        "message": message,
        "request_human": request_human,
        "disclosure_acknowledged": True,
        "session_id": f"eval-{int(time.time())}",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            latency_ms = (time.perf_counter() - start) * 1000
            return json.loads(raw), latency_ms
    except urllib.error.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw), latency_ms
        except json.JSONDecodeError:
            return {
                "decision": "escalate",
                "reply": raw[:500],
                "sources_used": [],
                "steps": [],
                "trace_id": "http-error",
                "error": {"code": "http_error", "message": str(exc)},
                "meta": {"ai_disclosure": True},
            }, latency_ms


def health_ok(base_url: str) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def load_fixtures() -> Dict[str, Dict[str, Any]]:
    """Map item id -> ChatResponse-like dict for offline grading."""
    path = FIXTURES_DIR / "chat_responses.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def run_static() -> Dict[str, Any]:
    checks = run_config_checks()
    by_ec: Dict[str, List[bool]] = defaultdict(list)
    for c in checks:
        by_ec[c["ec"]].append(c["ok"])
    ec_pass = {ec: all(vals) for ec, vals in by_ec.items()}
    return {
        "mode": "static",
        "pass": all(c["ok"] for c in checks),
        "checks": checks,
        "ec_pass": ec_pass,
    }


def run_items(
    items: List[Dict[str, Any]],
    *,
    mode: str,
    base_url: Optional[str],
    timeout: float,
    with_judge: bool,
) -> Dict[str, Any]:
    fixtures = load_fixtures() if mode == "fixtures" else {}
    per_item: List[Dict[str, Any]] = []
    by_category: Dict[str, List[bool]] = defaultdict(list)
    ec_agg: Dict[str, List[Optional[bool]]] = defaultdict(list)

    under_test = os.getenv("OLLAMA_MODEL") or os.getenv("OPENAI_MODEL_MID") or os.getenv("OPENAI_MODEL")

    for item in items:
        item_id = item["id"]
        latency_ms: Optional[float] = None
        response: Dict[str, Any]

        if mode == "live":
            assert base_url
            response, latency_ms = post_chat(
                base_url, item["message"], bool(item.get("request_human")), timeout
            )
        elif mode == "fixtures":
            if item_id not in fixtures:
                per_item.append({
                    "id": item_id,
                    "category": item.get("category"),
                    "pass": False,
                    "error": "missing fixture",
                })
                by_category[item.get("category", "?")].append(False)
                continue
            response = fixtures[item_id]
            latency_ms = fixtures.get(f"{item_id}__latency_ms")  # type: ignore[assignment]
            if not isinstance(latency_ms, (int, float)):
                latency_ms = None
        else:
            raise ValueError(mode)

        grade = grade_response(item, response, latency_ms=latency_ms, course_pass_latency=False)

        judge_result = None
        if with_judge and response.get("decision") == "resolve" and (response.get("sources_used") or []):
            judge_result = judge_faithfulness(
                response.get("reply") or "",
                response.get("sources_used") or [],
                under_test_model=under_test,
            )
            # Uncalibrated: do not fail course pass on judge alone
            grade["judge"] = judge_result
            if judge_result and not judge_result.get("skipped"):
                grade["ec_results"]["EC-005"] = judge_result.get("verdict") == "faithful"
                grade["ec_results"]["EC-005_calibrated"] = False

        ok = grade["pass"]
        by_category[item.get("category", "?")].append(ok)
        for ec, val in grade.get("ec_results", {}).items():
            ec_agg[ec].append(val)

        per_item.append({
            "id": item_id,
            "category": item.get("category"),
            "pass": ok,
            "grade": grade,
            "response_summary": {
                "decision": response.get("decision"),
                "sources": len(response.get("sources_used") or []),
                "error": response.get("error"),
                "trace_id": response.get("trace_id"),
            },
        })

    cat_summary = {
        cat: {"pass": sum(1 for x in vals if x), "total": len(vals), "all_pass": all(vals)}
        for cat, vals in by_category.items()
    }
    return {
        "mode": mode,
        "pass": all(i["pass"] for i in per_item) if per_item else False,
        "items": per_item,
        "by_category": cat_summary,
        "ec_agg": {ec: _summarize_ec(vals) for ec, vals in ec_agg.items()},
    }


def _summarize_ec(vals: List[Optional[bool]]) -> Dict[str, Any]:
    graded = [v for v in vals if v is not None]
    if not graded:
        return {"status": "not_graded", "pass": None, "n": 0}
    return {"status": "graded", "pass": all(graded), "n": len(graded), "passed": sum(1 for v in graded if v)}


def write_results(payload: Dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"eval-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = RESULTS_DIR / "latest.json"
    latest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AAMAD eval suite")
    parser.add_argument("--static", action="store_true", help="Config/security/cost checks only")
    parser.add_argument("--fixtures", action="store_true", help="Grade against evals/fixtures")
    parser.add_argument("--live", action="store_true", help="Call live POST /api/chat")
    parser.add_argument("--all", action="store_true", help="static + fixtures (and live if healthy)")
    parser.add_argument("--base-url", default=os.getenv("NEXT_PUBLIC_API_BASE_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("CHAT_TIMEOUT_SECONDS", "180")) + 30)
    parser.add_argument("--judge", action="store_true", help="Enable EC-005 LLM judge when keys available")
    parser.add_argument("--limit", type=int, default=0, help="Limit dataset items (0=all)")
    args = parser.parse_args()

    if not any([args.static, args.fixtures, args.live, args.all]):
        args.all = True

    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runtime": os.getenv("AAMAD_TARGET_RUNTIME", "crewai"),
        "operator": {
            "cost": "control_only",
            "latency_course_pass": False,
            "dataset": "synthetic",
            "judge": "different_model_uncalibrated",
        },
        "sections": {},
    }

    if args.static or args.all:
        report["sections"]["static"] = run_static()

    items = load_dataset()
    if args.limit and args.limit > 0:
        items = items[: args.limit]

    if args.fixtures or args.all:
        report["sections"]["fixtures"] = run_items(
            items, mode="fixtures", base_url=None, timeout=args.timeout, with_judge=args.judge
        )

    if args.live or (args.all and health_ok(args.base_url)):
        if not health_ok(args.base_url):
            report["sections"]["live"] = {
                "mode": "live",
                "pass": False,
                "error": f"GET {args.base_url}/health failed — start backend first",
            }
        else:
            report["sections"]["live"] = run_items(
                items,
                mode="live",
                base_url=args.base_url,
                timeout=args.timeout,
                with_judge=args.judge,
            )
    elif args.live:
        report["sections"]["live"] = {
            "mode": "live",
            "pass": False,
            "error": f"GET {args.base_url}/health failed",
        }

    # Overall course pass: static must pass; fixtures if present; live if present and not skipped
    course = True
    for key, section in report["sections"].items():
        if key == "live" and section.get("error"):
            continue
        if "pass" in section:
            course = course and bool(section["pass"])
    report["course_pass"] = course

    out = write_results(report)
    print(json.dumps({"course_pass": course, "results": str(out), "sections": list(report["sections"].keys())}, indent=2))
    for name, section in report["sections"].items():
        print(f"\n== {name} pass={section.get('pass')} ==")
        if name == "static":
            for c in section.get("checks", []):
                mark = "OK" if c["ok"] else "FAIL"
                print(f"  [{mark}] {c['ec']} {c['id']}: {c['detail']}")
        if name in ("fixtures", "live") and "by_category" in section:
            for cat, stats in section["by_category"].items():
                print(f"  {cat}: {stats['pass']}/{stats['total']} pass")
        if section.get("error"):
            print(f"  ERROR: {section['error']}")

    return 0 if course else 1


if __name__ == "__main__":
    raise SystemExit(main())
