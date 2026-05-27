---
id: T04
parent: S06
milestone: M003
key_files:
  - src/dashboard/eval.py
  - tests/test_dashboard_eval_tab.py
key_decisions:
  - Use presentation-only metric-name token detection in the Eval dashboard rather than importing aggregation constants from eval runner/operational metric modules, preserving the credential-free read-only dashboard boundary.
duration: 
verification_result: passed
completed_at: 2026-05-27T20:46:37.865Z
blocker_discovered: false
---

# T04: Kept the Eval tab credential-free while adding deterministic display formatting for persisted RAG quality, latency, cost, and token metrics.

**Kept the Eval tab credential-free while adding deterministic display formatting for persisted RAG quality, latency, cost, and token metrics.**

## What Happened

Updated `src/dashboard/eval.py` to recognize persisted optional RAG metric names by presentation-safe tokens only. Faithfulness and answer relevancy continue to render as percentages, latency metrics render with millisecond units, cost metrics render with fixed USD precision, and token metrics render as integer totals. The Eval tab remains read-only against `eval_runs` and `eval_metrics` through repository helpers; no eval runner, RAGAS, provider, Langfuse, observation payload, or computation path was added to Streamlit reruns. Extended `tests/test_dashboard_eval_tab.py` with regression coverage for the new metric families, comparison deltas, `None` metric values rendering blank, missing-table safety, and a provider/evaluator import guard.

## Verification

Ran the task-required focused dashboard test file and then the S06 regression set covering eval schema, optional metric aggregation/persistence, and dashboard display. Both commands passed. Behavior verified: missing DB/table returns empty state; no metrics renders an info state through existing coverage; `None` values render blank; cross-type comparison guard remains covered; new metric names render without percentage leakage for latency/cost/tokens; dashboard source does not import evaluator/provider modules.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\\Scripts\\python.exe -m pytest -q tests/test_dashboard_eval_tab.py` | 0 | ✅ pass | 7316ms |
| 2 | `venv\\Scripts\\python.exe -m pytest -q tests/test_eval_db_schema.py tests/test_retrieval_eval_optional_metrics.py tests/test_dashboard_eval_tab.py` | 0 | ✅ pass | 9380ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`
