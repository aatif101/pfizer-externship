---
estimated_steps: 15
estimated_files: 1
skills_used: []
---

# T01: Define eval DB schema and migrations (runs, metrics, gold sets)

Why: S02–S04 need a stable, queryable contract for evaluation history and gold labels; current `evaluations` table is too underspecified (no run grouping, no gold storage, no status/error fields).

Do:
- Extend `src/db/schema.py` with explicit eval-focused tables:
  - `eval_runs` (run_id TEXT PK, eval_type TEXT, status TEXT, created_at, completed_at, pipeline_label, params_json, error_reason)
  - `eval_metrics` (metric_id INTEGER PK, run_id FK, metric_name TEXT, metric_value REAL, scope_type TEXT, scope_id TEXT, created_at)
  - Gold sets (minimal but extensible):
    - `gold_extraction_labels` keyed by (doc_id, field_name) with expected_value + optional normalized_value + source_page.
    - `gold_retrieval_queries` keyed by query_id with query_text + optional notes.
    - `gold_retrieval_targets` mapping query_id -> (doc_id, page_num) expected hit.
- Keep the existing `evaluations` table for backward compatibility but stop using it for new code; add a comment marking it legacy.
- Add migration helpers similar to `_migrate_extractions_table` for any new nullable columns/tables needed (idempotent).
- Ensure foreign keys reference existing `documents`/`pages` tables where applicable and that deletions cascade safely.

Done-when:
- Running `init_db()` twice on the same DB succeeds.
- Running `init_db()` on an older DB lacking the new tables succeeds and the new tables exist.

## Inputs

- `src/db/schema.py`
- `pytest.ini`

## Expected Output

- `src/db/schema.py`
- `tests/test_eval_db_schema.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_eval_db_schema.py -q

## Observability Impact

Creates durable eval run + gold-set tables that become the canonical inspection surface for evaluation state.
