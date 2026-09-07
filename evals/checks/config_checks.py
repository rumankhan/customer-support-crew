"""Static config / security / cost checks (no LLM call)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
AGENTS_YAML = BACKEND / "config" / "agents.yaml"
CREW_PY = BACKEND / "crew.py"
TOOLS_PY = BACKEND / "tools.py"


ALLOWED_TOOLS = {"kb_search", "ticket_stub", "account_lookup", "order_lookup"}


def run_config_checks() -> List[Dict[str, Any]]:
    """Return list of {id, ec, ok, detail} for EC-011, EC-015, EC-016, EC-017, EC-018."""
    results: List[Dict[str, Any]] = []

    # EC-016 max_iter
    max_iter_env = int(os.getenv("MAX_ITER", "12"))
    ok = max_iter_env <= 12
    results.append({
        "id": "max_iter_env",
        "ec": "EC-016",
        "ok": ok,
        "detail": f"MAX_ITER={max_iter_env} (threshold <=12)",
    })
    crew_text = CREW_PY.read_text(encoding="utf-8") if CREW_PY.exists() else ""
    ok_crew = "max_iter" in crew_text and 'MAX_ITER' in crew_text
    results.append({
        "id": "max_iter_wired",
        "ec": "EC-016",
        "ok": ok_crew,
        "detail": "crew.py binds max_iter from MAX_ITER" if ok_crew else "max_iter wiring missing",
    })

    # EC-017 MAX_RPM
    max_rpm = int(os.getenv("MAX_RPM", "10"))
    results.append({
        "id": "max_rpm_env",
        "ec": "EC-017",
        "ok": max_rpm > 0,
        "detail": f"MAX_RPM={max_rpm} (honored when crew constructed)",
    })
    ok_rpm = "max_rpm" in crew_text and "MAX_RPM" in crew_text
    results.append({
        "id": "max_rpm_wired",
        "ec": "EC-017",
        "ok": ok_rpm,
        "detail": "crew.py binds max_rpm from MAX_RPM" if ok_rpm else "max_rpm wiring missing",
    })

    # EC-018 model tiers in agents.yaml
    if AGENTS_YAML.exists():
        agents = yaml.safe_load(AGENTS_YAML.read_text(encoding="utf-8")) or {}
        tiers = {name: cfg.get("model_tier") for name, cfg in agents.items() if isinstance(cfg, dict)}
        mid_ok = tiers.get("response_specialist") == "mid"
        low_agents = ["query_classifier", "knowledge_retriever", "escalation_manager"]
        low_ok = all(tiers.get(a) == "low" for a in low_agents)
        results.append({
            "id": "model_tiers",
            "ec": "EC-018",
            "ok": mid_ok and low_ok,
            "detail": f"tiers={tiers}",
        })
        # no per-agent OPENAI_MODEL_* in repo code beyond LOW/MID
        llm_cfg = (BACKEND / "llm_config.py").read_text(encoding="utf-8") if (BACKEND / "llm_config.py").exists() else ""
        banned = re.findall(r"OPENAI_MODEL_(CLASSIFIER|RETRIEVER|ESCALATION|RESPONSE)", llm_cfg + crew_text)
        results.append({
            "id": "no_per_agent_model_env",
            "ec": "EC-018",
            "ok": len(banned) == 0,
            "detail": f"banned refs={banned or 'none'}",
        })
    else:
        results.append({
            "id": "agents_yaml_missing",
            "ec": "EC-018",
            "ok": False,
            "detail": str(AGENTS_YAML),
        })

    # EC-015 tool least privilege
    if AGENTS_YAML.exists():
        agents = yaml.safe_load(AGENTS_YAML.read_text(encoding="utf-8")) or {}
        declared: List[str] = []
        for cfg in agents.values():
            if isinstance(cfg, dict):
                declared.extend(cfg.get("tools") or [])
        unknown = sorted(set(declared) - ALLOWED_TOOLS)
        results.append({
            "id": "yaml_tools_allowlist",
            "ec": "EC-015",
            "ok": len(unknown) == 0,
            "detail": f"tools={sorted(set(declared))} unknown={unknown}",
        })

    tools_text = TOOLS_PY.read_text(encoding="utf-8") if TOOLS_PY.exists() else ""
    # Heuristic: no shell / mcp tool registration names
    risky = []
    for token in ("ShellTool", "MCPServer", "subprocess.run", "os.system("):
        if token in tools_text:
            risky.append(token)
    results.append({
        "id": "no_shell_mcp_tools",
        "ec": "EC-015",
        "ok": len(risky) == 0,
        "detail": f"risky_tokens={risky or 'none'}",
    })

    # EC-011 no biometric emotion tools
    bio = []
    for token in ("biometric", "face_recog", "emotion_api", "webcam"):
        if token in tools_text.lower() or token in (AGENTS_YAML.read_text(encoding="utf-8").lower() if AGENTS_YAML.exists() else ""):
            bio.append(token)
    results.append({
        "id": "no_biometric_emotion",
        "ec": "EC-011",
        "ok": len(bio) == 0,
        "detail": f"hits={bio or 'none'}",
    })

    # EC-014 — Prompt Trace redaction pattern present
    chat_svc = BACKEND / "chat_service.py"
    text = chat_svc.read_text(encoding="utf-8") if chat_svc.exists() else ""
    redact_ok = "write_prompt_trace" in text and ("truncat" in text.lower() or "[:200]" in text or "200" in text)
    results.append({
        "id": "prompt_trace_redaction",
        "ec": "EC-014",
        "ok": redact_ok,
        "detail": "write_prompt_trace truncation/redaction heuristics",
    })

    return results
