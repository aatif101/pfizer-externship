---
estimated_steps: 15
estimated_files: 3
skills_used: []
---

# T02: Add eval repository/query helpers for insert/list without rerun duplication

Why: Streamlit reruns can easily double-insert metrics. We need idempotent helpers and a single module boundary that downstream metric code and the dashboard can call safely.

Do:
- Create `src/eval/repository.py` (credential-free) that uses `src/db/schema._connect` and only parameterized SQL.
- Implement helpers:
  - `create_eval_run(db_path, run_id, eval_type, pipeline_label, params: dict) -> None` (INSERT OR IGNORE)
  - `mark_eval_run_complete(db_path, run_id)`, `mark_eval_run_error(db_path, run_id, error_reason)`
  - `upsert_eval_metric(db_path, run_id, metric_name, metric_value, scope_type=None, scope_id=None)` using a UNIQUE constraint such as (run_id, metric_name, scope_type, scope_id)
  - `list_eval_runs(db_path, limit=50)` and `list_eval_metrics(db_path, run_id)` returning typed dataclasses or dicts for UI.
  - Gold set CRUD reads:
    - `list_gold_extraction_labels(db_path)`
    - `list_gold_retrieval_queries(db_path)` and `list_gold_retrieval_targets(db_path, query_id)`
- Ensure functions behave deterministically on empty DB / empty tables (return empty lists).

Done-when:
- A run can be created, metrics upserted twice without duplication, and listed back in order.
- All SQL uses placeholders; no provider imports; works offline.

## Inputs

- `src/db/schema.py`
- `src/db/queries.py`

## Expected Output

- `src/eval/repository.py`
- `src/eval/__init__.py`
- `tests/test_eval_repository.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_eval_repository.py -q

## Observability Impact

Provides a stable adapter seam for recording eval run status/errors and metric rows for later UI visibility.
