---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Create extraction_eval_runner.py and offline unit tests

Why: S05 needs a run_extraction_eval function that turns run-scoped extraction_history rows and gold_extraction_labels into per-field and macro precision/recall/F1 eval_metrics. This is the only new module S05 requires; all supporting infrastructure (extraction_metrics, eval repository, tracing) already exists. Do: Mirror the extraction_usage_eval.py skeleton exactly. (1) Create src/eval/extraction_eval_runner.py with @observe(name='extraction_eval_run') on the public function run_extraction_eval(db_path, *, source_run_id, eval_run_id=None, pipeline_label='extraction_eval') -> str. Lifecycle: create_eval_run -> load gold via list_gold_extraction_labels(db_path) -> load preds via list_predicted_extractions_for_run(db_path, source_run_id) -> compute_extraction_field_scores(gold_rows, pred_rows) -> compute_macro_averages(per_field_scores) -> upsert global metrics (extraction.macro.f1, extraction.macro.precision, extraction.macro.recall, no scope) -> upsert scoped metrics (extraction.f1/precision/recall, scope_type='field', scope_id=<field_name>) -> mark_eval_run_complete. Graceful empty-state: if no gold rows OR no predicted rows, complete with no metrics (not error). Catch sqlite3.OperationalError for missing gold_extraction_labels or extraction_history tables and complete with no metrics. Bounded trace metadata (no field values, spans, or raw text): boundary, status, eval_type, run_id, source_run_id, gold_count, pred_count, metric_count, error_class. Use a _EXTRACTION_EVAL_TRACE_ALLOWED_KEYS frozenset and _sanitize_error helper copied from the usage eval pattern. (2) Create tests/test_extraction_eval_runner.py with 6 tests using tmp_path. Each test calls init_db(str(tmp_path/'db.sqlite')) from src.db.schema to create the full schema, then seeds: documents (INSERT INTO documents(doc_id, filename, file_path, page_count)), extraction_runs (INSERT INTO extraction_runs(run_id, ...)), extraction_history rows (run_id, doc_id, field_name, normalized_value, review_state), and gold_extraction_labels rows (doc_id, field_name, expected_value, normalized_value) via direct SQLite INSERT. Tests: test_run_extraction_eval_produces_macro_and_field_metrics; test_run_extraction_eval_with_no_gold_labels_completes_with_no_metrics; test_run_extraction_eval_with_no_predicted_rows_completes_with_no_metrics; test_run_extraction_eval_is_idempotent_on_repeated_calls; test_run_extraction_eval_marks_run_complete_on_success; test_run_extraction_eval_persists_per_field_scoped_metrics. Done when: pytest tests/test_extraction_eval_runner.py passes all 6 tests with exit code 0.

## Inputs

- `src/eval/extraction_usage_eval.py`
- `src/eval/extraction_metrics.py`
- `src/eval/repository.py`
- `src/db/schema.py`
- `src/tracing.py`

## Expected Output

- `src/eval/extraction_eval_runner.py`
- `tests/test_extraction_eval_runner.py`

## Verification

venv\Scripts\python.exe -m pytest -q tests/test_extraction_eval_runner.py

## Observability Impact

Bounded extraction_eval trace observations (gold_count, pred_count, metric_count, status) written via Langfuse @observe decorator. eval_runs rows with eval_type='extraction_eval' and eval_metrics rows with extraction.macro.* and field-scoped extraction.f1/precision/recall queryable from any DB.
