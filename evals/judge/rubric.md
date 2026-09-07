# Faithfulness judge rubric (EC-005)

## Verdict labels (constrained)
- `faithful` — reply is supported by the cited passages; no contradictory policy/pricing claims
- `contradicts` — reply asserts facts that conflict with citations
- `ungrounded` — reply asserts material policy/pricing not present in citations
- `n/a` — item is escalate/refuse/error; faithfulness not applicable

## Rules
1. Only use provided citations/passages as evidence.
2. Ignore tone/style unless it changes factual claims.
3. Prefer `faithful` when the reply is a reasonable paraphrase of citations.
4. Output JSON only: `{"verdict": "...", "rationale": "..."}`.

## Calibration
Human-labeled calibration set: **not provided** (operator gap 4b).
Do not treat uncalibrated judge scores as Deliver blockers; report agreement TBD under Open Questions.
