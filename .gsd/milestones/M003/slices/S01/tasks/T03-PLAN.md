---
estimated_steps: 11
estimated_files: 2
skills_used: []
---

# T03: Add contract tests for eval schema + repository behaviors (empty states, idempotency)

Why: Downstream slices will rely on this contract; tests prevent accidental schema drift and prove offline-safe behavior.

Do:
- Add `tests/test_eval_db_schema.py` to assert that after `init_db(tmp_db)` the eval tables exist (PRAGMA table_info checks) and that re-running init is safe.
- Add `tests/test_eval_repository.py` to assert:
  - `create_eval_run` is idempotent (no duplicates).
  - `upsert_eval_metric` overwrites/keeps single row under the UNIQUE key.
  - list functions return empty lists when nothing exists.
  - error/complete markers set timestamps/status as expected.
- Use `tempfile.NamedTemporaryFile(delete=False)` or pytest tmp_path to create SQLite DB files.

Done-when:
- `pytest` passes for these tests on Windows Python 3.11 venv.

## Inputs

- `src/db/schema.py`
- `src/db/queries.py`

## Expected Output

- `tests/test_eval_db_schema.py`
- `tests/test_eval_repository.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_eval_db_schema.py tests/test_eval_repository.py -q
