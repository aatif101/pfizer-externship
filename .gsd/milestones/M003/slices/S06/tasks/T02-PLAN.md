---
estimated_steps: 14
estimated_files: 2
skills_used: []
---

# T02: Implement pure optional metric aggregation

---
estimated_steps: 6
estimated_files: 2
skills_used:
  - tdd
  - observability
---

Why: The current optional latency/cost path uses unsupported SQLite percentile functions and has no real faithfulness/relevancy source. Pure Python aggregation makes optional metrics deterministic, testable, and absent-safe.

Do: Add `src/eval/operational_metrics.py` with pure functions that accept bounded observation rows or simple numeric structures and return metric-name/value pairs. Compute latency average/p50/p95 in Python, cost total/average where cost rows exist, token input/output/total sums where token rows exist, and faithfulness/answer_relevancy averages where precomputed numeric values exist. Return no metric for an empty input list or for a metric family with no non-null source values; do not emit misleading zeroes. Keep all functions provider-free and free of SQLite side effects.

Done when: unit tests cover percentile behavior, null/empty inputs, cost/token totals, and faithfulness/relevancy averages without importing RAGAS or provider SDKs.

Requirement Impact (Q4): Advances R007 metric coverage while preserving R008 no-secrets behavior; re-test optional metrics and ensure no provider dependency is introduced.
Failure Modes (Q5): Empty or all-null observations return an empty metric set; malformed numeric values should be rejected or ignored according to explicit tests rather than swallowed broadly.
Load Profile (Q6): Per-run aggregation is O(n) over bounded observation rows; 10x row growth first affects in-memory list size, not external services.
Negative Tests (Q7): Empty list, all-null columns, one-row percentile boundaries, unsorted latency rows, and missing cost/token fields.

## Inputs

- `src/eval/repository.py`
- `tests/test_retrieval_eval_optional_metrics.py`

## Expected Output

- `src/eval/operational_metrics.py`
- `tests/test_retrieval_eval_optional_metrics.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_retrieval_eval_optional_metrics.py

## Observability Impact

Defines canonical numeric metric names and deterministic aggregation semantics so future agents can diagnose missing optional metrics as missing input data rather than hidden provider failures.
