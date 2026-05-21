---
id: T02
parent: S01
milestone: M003
key_files:
  - src/eval/repository.py
  - src/eval/__init__.py
  - tests/test_eval_repository.py
key_decisions:
  - Use a unique index with COALESCE(scope_type/scope_id,'') so NULL-scoped (global) metrics are deduped correctly under SQLite.
duration: 
verification_result: passed
completed_at: 2026-05-21T18:03:36.489Z
blocker_discovered: false
---

# T02: Added Streamlit-safe eval repository helpers for creating/listing eval runs, upserting metrics without duplication, and reading gold-set tables.

**Added Streamlit-safe eval repository helpers for creating/listing eval runs, upserting metrics without duplication, and reading gold-set tables.**

## What Happened

- Created a new `src/eval` package to hold evaluation persistence helpers decoupled from any provider/LLM code.
- Implemented `src/eval/repository.py` with a small repository boundary over SQLite using `src/db/schema._connect` and parameterized SQL only.
- Added run lifecycle helpers (`create_eval_run`, `mark_eval_run_complete`, `mark_eval_run_error`) using `INSERT OR IGNORE` and deterministic status updates.
- Added `upsert_eval_metric` with a dedupe unique index (`uq_eval_metrics_dedupe`) and `ON CONFLICT DO UPDATE` so Streamlit reruns overwrite instead of duplicating metric rows; used COALESCE() in the uniqueness key to handle NULL scope values (SQLite treats NULLs as distinct in UNIQUE constraints).
- Implemented list helpers for eval runs/metrics and read-only list helpers for gold extraction/retrieval tables; all functions return empty lists on empty DBs.

## Verification

Ran pytest for the new repository test module to confirm eval runs are created idempotently, metric upserts dedupe across reruns, and gold-set list helpers return empty lists on empty databases.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_eval_repository.py -q` | 0 | ✅ pass | 860ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/eval/repository.py`
- `src/eval/__init__.py`
- `tests/test_eval_repository.py`
