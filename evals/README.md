# Eval suite

Implements SAD §9 evaluation criteria (`EC-001`…`EC-019`) for the B-Mobile support crew.

| Doc | Purpose |
|-----|---------|
| [`RUNNING.md` § Evals](../RUNNING.md#evals-quality-gates) | **How to run** (static / fixtures / live) |
| [`project-context/2.build/evals.md`](../project-context/2.build/evals.md) | Strategy, thresholds, results, monitoring handoff |
| [`project-context/1.define/sad.md`](../project-context/1.define/sad.md) §9 | Pass/fail contract |

```bash
# From repository root
python -m evals.run --static --fixtures --profile mvp
python -m evals.run --all --profile production --base-url http://127.0.0.1:8001
```

Default profile is **production** (live + Path A p95 < 30s when live runs). `--profile mvp` keeps the course demo bar (static + fixtures). See `RUNNING.md` for flags and env vars.
