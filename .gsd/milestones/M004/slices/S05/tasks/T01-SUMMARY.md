---
id: T01
parent: S05
milestone: M004
key_files:
  - src/eval/extraction_eval_runner.py
  - tests/test_extraction_eval_runner.py
key_decisions:
  - Mirrored extraction_usage_eval.py skeleton exactly — same frozenset/sanitize_error pattern, same lifecycle shape, same graceful-empty-state and OperationalError catch strategy
  - Per-field metrics use metric_name='extraction.f1/precision/recall' with scope_type='field', scope_id=field_name; macro metrics use 'extraction.macro.f1/precision/recall' with no scope — consistent with eval_metrics schema
duration: 
verification_result: passed
completed_at: 2026-06-07T23:18:41.796Z
blocker_discovered: false
---

# T01: Created extraction_eval_runner.py with @observe-decorated run_extraction_eval and 6 passing offline unit tests covering macro/field metrics, empty-state graceful completion, idempotency, and run completion marking.

**Created extraction_eval_runner.py with @observe-decorated run_extraction_eval and 6 passing offline unit tests covering macro/field metrics, empty-state graceful completion, idempotency, and run completion marking.**

## What Happened

Read all input files (extraction_usage_eval.py, extraction_metrics.py, repository.py, schema.py) to understand the existing patterns before writing anything. Created src/eval/extraction_eval_runner.py mirroring the extraction_usage_eval.py skeleton exactly: @observe(name='extraction_eval_run') decorator, _EXTRACTION_EVAL_TRACE_ALLOWED_KEYS frozenset with boundary/status/eval_type/run_id/source_run_id/gold_count/pred_count/metric_count/error_class, _sanitize_error helper, and a public run_extraction_eval(db_path, *, source_run_id, eval_run_id=None, pipeline_label='extraction_eval') -> str. Lifecycle: create_eval_run → load gold via list_gold_extraction_labels → load preds via list_predicted_extractions_for_run → compute_extraction_field_scores → compute_macro_averages → upsert global metrics (extraction.macro.f1/precision/recall, no scope) → upsert scoped metrics (extraction.f1/precision/recall, scope_type='field', scope_id=field_name) → mark_eval_run_complete. Graceful empty-state: if gold_count==0 or pred_count==0, completes with no metrics. sqlite3.OperationalError for missing tables caught in _load_optional_gold_labels and _load_optional_predicted_extractions helpers. Created tests/test_extraction_eval_runner.py with 6 tests using tmp_path: all seed data via direct SQLite INSERT after init_db. All 6 tests passed in 3.62s.

## Verification

Ran pytest -q tests/test_extraction_eval_runner.py via gsd_exec with node runtime. Exit code 0. Output: 6 passed in 3.62s.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_extraction_eval_runner.py` | 0 | 6 passed | 5349ms |

## Deviations

none

## Known Issues

none

## Files Created/Modified

- `src/eval/extraction_eval_runner.py`
- `tests/test_extraction_eval_runner.py`
