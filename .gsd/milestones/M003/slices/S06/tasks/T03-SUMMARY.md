---
id: T03
parent: S06
milestone: M003
key_files:
  - src/eval/retrieval_eval_runner.py
  - src/eval/operational_metrics.py
  - tests/test_retrieval_eval_optional_metrics.py
key_decisions:
  - Use the source retrieval/index run ID, not the newly-created eval run ID, to load pre-existing bounded RAG observations for optional metric aggregation.
  - Keep optional observation storage absent-safe only for the explicit missing `rag_eval_observations` table case; malformed numeric data remains a real computation error recorded through sanitized eval_run failure state.
  - Rename optional operational and quality metric names to the canonical `rag.*` namespace required by the task plan.
duration: 
verification_result: passed
completed_at: 2026-05-27T20:44:19.249Z
blocker_discovered: false
---

# T03: Wired retrieval eval runs to persist provider-free optional RAG latency, cost, token, faithfulness, and relevancy metrics from bounded observations.

**Wired retrieval eval runs to persist provider-free optional RAG latency, cost, token, faithfulness, and relevancy metrics from bounded observations.**

## What Happened

Updated the optional metrics integration in `src/eval/retrieval_eval_runner.py` so retrieval eval runs load bounded `rag_eval_observations` for the source retrieval/index run, aggregate them through `src/eval/operational_metrics.py`, and persist global `eval_metrics` rows on the new eval run. The integration keeps core retrieval recall and citation accuracy behavior unchanged, performs a single optional observation load when optional flags are enabled, treats a missing observation table as an explicit optional no-op, and lets malformed numeric observation data fail visibly while recording the sanitized `eval_runs.error_reason`. Metric constants were moved to the canonical `rag.*` namespace requested by the task plan. Tests now prove populated observation rows create optional metrics, unrelated source runs are ignored, absent optional storage is a no-op, RAGAS is not imported for base behavior, malformed observations mark sanitized runner errors, and existing retrieval eval metrics still pass.

## Verification

Ran the task verification command for optional metrics and retrieval eval runner tests, then ran adjacent repository/schema tests that cover observation persistence and bounded schema behavior. Both commands passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py` | 0 | ✅ pass — 12 passed | 6700ms |
| 2 | `venv/Scripts/python.exe -m pytest -q tests/test_eval_repository.py tests/test_eval_db_schema.py` | 0 | ✅ pass — 10 passed | 4300ms |

## Deviations

Added adjacent repository/schema verification beyond the task's explicit command because the runner now depends on observation repository behavior and missing-table optionality.

## Known Issues

None.

## Files Created/Modified

- `src/eval/retrieval_eval_runner.py`
- `src/eval/operational_metrics.py`
- `tests/test_retrieval_eval_optional_metrics.py`
