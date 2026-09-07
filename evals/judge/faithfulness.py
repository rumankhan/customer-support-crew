"""Optional LLM-as-judge for EC-005 reply faithfulness.

Judge model must differ from the model under test (operator 4b).
Calibration against human labels is pending — flag under Open Questions.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

RUBRIC_PATH = Path(__file__).with_name("rubric.md")


def resolve_judge_model(under_test_model: Optional[str] = None) -> str:
    judge = os.getenv("EVAL_JUDGE_MODEL", "gpt-4o")
    if under_test_model and judge == under_test_model:
        # Force a different default if collision
        judge = "gpt-4o" if under_test_model != "gpt-4o" else "gpt-4.1"
    return judge


def build_judge_prompt(reply: str, citations: List[Dict[str, Any]]) -> str:
    rubric = RUBRIC_PATH.read_text(encoding="utf-8") if RUBRIC_PATH.exists() else ""
    cites = json.dumps(citations, ensure_ascii=False, indent=2)
    return (
        f"{rubric}\n\n"
        f"## Citations\n{cites}\n\n"
        f"## Reply under test\n{reply}\n"
    )


def judge_faithfulness(
    reply: str,
    citations: List[Dict[str, Any]],
    *,
    under_test_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call OpenAI-compatible chat completions for a constrained verdict.
    Returns {skipped, verdict, rationale, judge_model, calibrated}.
    """
    if not reply or not citations:
        return {
            "skipped": True,
            "verdict": "n/a",
            "rationale": "No reply or citations to judge",
            "judge_model": None,
            "calibrated": False,
        }

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("EVAL_JUDGE_API_KEY")
    if not api_key:
        return {
            "skipped": True,
            "verdict": None,
            "rationale": "OPENAI_API_KEY / EVAL_JUDGE_API_KEY unset — judge skipped",
            "judge_model": resolve_judge_model(under_test_model),
            "calibrated": False,
        }

    judge_model = resolve_judge_model(under_test_model)
    prompt = build_judge_prompt(reply, citations)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=judge_model,
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a strict faithfulness grader. Output JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = completion.choices[0].message.content or ""
        parsed = _parse_verdict(raw)
        parsed.update({
            "skipped": False,
            "judge_model": judge_model,
            "calibrated": False,
            "raw": raw[:500],
        })
        return parsed
    except Exception as exc:  # noqa: BLE001 — eval harness must not crash suite
        return {
            "skipped": True,
            "verdict": None,
            "rationale": f"Judge call failed: {exc}",
            "judge_model": judge_model,
            "calibrated": False,
        }


def _parse_verdict(raw: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"verdict": "ungrounded", "rationale": f"Unparseable judge output: {raw[:200]}"}
    try:
        data = json.loads(match.group(0))
        verdict = str(data.get("verdict", "ungrounded")).lower()
        if verdict not in {"faithful", "contradicts", "ungrounded", "n/a"}:
            verdict = "ungrounded"
        return {"verdict": verdict, "rationale": str(data.get("rationale", ""))[:500]}
    except json.JSONDecodeError:
        return {"verdict": "ungrounded", "rationale": f"JSON decode failed: {raw[:200]}"}
