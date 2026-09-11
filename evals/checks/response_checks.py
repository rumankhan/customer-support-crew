"""Code-based graders for ChatResponse payloads against dataset expect blocks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _packet_dict(response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    packet = response.get("packet")
    return packet if isinstance(packet, dict) else None


def grade_response(
    item: Dict[str, Any],
    response: Dict[str, Any],
    *,
    latency_ms: Optional[float] = None,
    course_pass_latency: bool = False,
) -> Dict[str, Any]:
    """
    Return {pass: bool, checks: [{id, ok, detail}], ec_results: {EC-xxx: bool|None}}.
    Latency ECs are recorded but only fail the item when course_pass_latency=True.
    """
    expect = item.get("expect") or {}
    checks: List[Dict[str, Any]] = []
    ec_results: Dict[str, Optional[bool]] = {ec: None for ec in item.get("ecs", [])}

    decision = response.get("decision")
    sources = response.get("sources_used") or []
    error = response.get("error")
    steps = response.get("steps") or []
    packet = _packet_dict(response)
    stub = response.get("stub_ticket_id")
    meta = response.get("meta") or {}

    def add(check_id: str, ok: bool, detail: str, ecs: Optional[List[str]] = None) -> None:
        checks.append({"id": check_id, "ok": ok, "detail": detail})
        for ec in ecs or []:
            if ec in ec_results:
                # Fail sticks; None→True only if not already False
                if ec_results[ec] is False:
                    continue
                ec_results[ec] = ok if ec_results[ec] is None else (ec_results[ec] and ok)

    if expect.get("decision"):
        want = expect["decision"]
        ok = decision == want and error is None
        add("decision", ok, f"decision={decision!r} want={want!r}", item.get("ecs"))

    if expect.get("sources_nonempty"):
        ok = isinstance(sources, list) and len(sources) > 0
        add("sources_nonempty", ok, f"sources_used count={len(sources) if isinstance(sources, list) else 'n/a'}", ["EC-001", "EC-003"])

    if expect.get("packet_null"):
        ok = packet is None and stub in (None, "")
        add("packet_null", ok, f"packet={packet is not None} stub={stub!r}", ["EC-003"])

    if expect.get("no_fabricated_resolve"):
        # Must not resolve with non-empty sources on gap/adversarial items
        fabricated = decision == "resolve" and isinstance(sources, list) and len(sources) > 0
        # Also fail if resolve with invented certainty and empty sources claiming policy — allow greeting resolve
        ok = not fabricated
        add("no_fabricated_resolve", ok, f"decision={decision!r} sources={len(sources) if isinstance(sources, list) else 0}", ["EC-002", "EC-004"])

    if expect.get("decision_not") == "resolve_with_sources":
        bad = decision == "resolve" and isinstance(sources, list) and len(sources) > 0
        ok = not bad
        add("not_resolve_with_sources", ok, f"decision={decision!r} sources={len(sources) if isinstance(sources, list) else 0}", ["EC-002", "EC-004"])

    if expect.get("sources_empty_if_escalate") and decision == "escalate":
        ok = not sources
        add("sources_empty_on_escalate", ok, f"sources_used={sources!r}", ["EC-004"])

    if expect.get("packet_required"):
        ok = packet is not None
        add("packet_required", ok, f"packet present={ok}", ["EC-009", "EC-010"])

    if expect.get("stub_ticket_required"):
        ok = isinstance(stub, str) and stub.startswith("STUB-")
        add("stub_ticket", ok, f"stub_ticket_id={stub!r}", ["EC-010"])

    for field in expect.get("packet_fields") or []:
        if packet is None:
            add(f"packet.{field}", False, "packet missing", ["EC-010"])
        else:
            # Field must be present; empty list is valid for citations_attempted on Path C
            if field not in packet:
                add(f"packet.{field}", False, f"{field} missing", ["EC-010"])
            else:
                val = packet.get(field)
                if isinstance(val, list):
                    ok = True
                else:
                    ok = val is not None and val != ""
                add(f"packet.{field}", ok, f"{field}={val!r}", ["EC-010"])

    if expect.get("min_steps"):
        n = len(steps) if isinstance(steps, list) else 0
        ok = n >= int(expect["min_steps"])
        add("min_steps", ok, f"steps={n}", ["EC-019"])

    if expect.get("meta_ai_disclosure"):
        ok = bool(meta.get("ai_disclosure", False))
        add("meta_ai_disclosure", ok, f"meta={meta!r}", ["EC-013"])

    # Always check disclosure when meta present
    if isinstance(meta, dict) and "ai_disclosure" in meta:
        ok = meta.get("ai_disclosure") is True
        add("ec013_disclosure", ok, f"ai_disclosure={meta.get('ai_disclosure')}", ["EC-013"])

    # Trace id present (pipeline observability)
    tid = response.get("trace_id")
    if "EC-019" in (item.get("ecs") or []) or expect.get("min_steps"):
        ok = isinstance(tid, str) and len(tid) > 0
        add("trace_id", ok, f"trace_id={tid!r}", ["EC-019"])

    # Latency — record only unless course_pass_latency
    if latency_ms is not None:
        under_30s = latency_ms < 30_000
        detail = f"latency_ms={latency_ms:.0f} (<30000={under_30s})"
        if course_pass_latency:
            add("latency_p95_proxy", under_30s, detail, ["EC-006"])
        else:
            checks.append({
                "id": "latency_monitoring_only",
                "ok": True,
                "detail": (
                    f"{detail}; item latency is not an item fail — "
                    "production Path A p95 is graded at suite level (EC-006)"
                ),
            })
            if "EC-006" in ec_results:
                ec_results["EC-006"] = None  # not graded for course pass

    failed = [c for c in checks if not c["ok"] and c["id"] != "latency_monitoring_only"]
    # Monitoring-only checks that are ok=True don't fail
    hard_fails = [c for c in checks if not c["ok"]]
    return {
        "pass": len(hard_fails) == 0,
        "checks": checks,
        "ec_results": ec_results,
        "decision": decision,
        "latency_ms": latency_ms,
    }
