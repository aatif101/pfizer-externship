---
estimated_steps: 14
estimated_files: 2
skills_used: []
---

# T04: Keep Eval tab readable and credential-free for new metrics

---
estimated_steps: 5
estimated_files: 2
skills_used:
  - tdd
  - observability
---

Why: R007 advanced scope includes evaluator-facing readability of stored eval runs/metrics, and R008 requires the dashboard to stay provider-free/no-secrets. The Eval tab already reads persisted metrics only, but new latency/cost/token metric names need clear deterministic formatting and regression coverage.

Do: Update `src/dashboard/eval.py` only if needed to format the new metric names predictably: faithfulness/relevancy as percentages, latency in readable numeric form, cost with stable decimals, and token totals without implying percentages. Keep all logic read-only against `eval_runs`/`eval_metrics`; do not import `src.eval.retrieval_eval_runner`, RAGAS, providers, Langfuse, or any code that computes evals. Extend `tests/test_dashboard_eval_tab.py` to cover rendering/formatting for the new metric names and to assert missing DB/table behavior remains safe.

Done when: dashboard tests prove the Eval tab can display and compare runs containing the new persisted metric names, and no test or code path computes evals on Streamlit rerun.

Threat Surface (Q3): Dashboard shows persisted metadata only; prevent accidental exposure by never reading observation raw payload fields and by preserving the existing missing-table guard.
Requirement Impact (Q4): Supports R007 readability and preserves R008 dashboard no-secrets behavior; re-test dashboard Eval tab.
Failure Modes (Q5): Missing DB/table returns empty state; metric value None renders blank; mixed eval types still require explicit comparison override as before.
Negative Tests (Q7): Missing DB/tables, no metrics for selected run, None values, and cross-type comparison guard.

## Inputs

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`

## Expected Output

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py

## Observability Impact

Improves the human inspection surface for persisted eval metrics without adding new runtime tracing or provider behavior.
