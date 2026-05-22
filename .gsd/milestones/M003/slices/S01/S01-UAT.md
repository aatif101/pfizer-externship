# S01: S01 — UAT

**Milestone:** M003
**Written:** 2026-05-21T18:49:40.432Z

# UAT: S01 Evaluation DB contract and adapters

## UAT Type
Developer-facing / evaluator harness (offline, no provider credentials required).

## Preconditions
- Project venv exists and deps installed.
- You can run the project venv Python at `venv\\Scripts\\python.exe`.

## Steps
1. Run the schema contract tests:
   - `venv\\Scripts\\python.exe -m pytest tests/test_eval_db_schema.py -q`
2. Run the repository contract tests:
   - `venv\\Scripts\\python.exe -m pytest tests/test_eval_repository.py -q`
3. Run both together (guards against contract drift across modules):
   - `venv\\Scripts\\python.exe -m pytest tests/test_eval_db_schema.py tests/test_eval_repository.py -q`

## Expected Outcomes
- All tests pass.
- The tests demonstrate:
  - `init_db()` is safe to run repeatedly (idempotent).
  - `init_db()` upgrades an older/minimal schema by creating the eval + gold tables.
  - Creating an eval run is idempotent enough for Streamlit reruns.
  - Upserting metrics does not create duplicates (it overwrites by dedupe key).
  - List helpers return empty lists (not exceptions) when tables are empty.

## Edge Cases to Exercise
- Re-run steps (1)–(3) multiple times; results should remain stable (no duplicate-row or migration errors).

## Not Proven By This UAT
- Actual metric computation for extraction/retrieval/RAG (S02/S03 scope).
- Streamlit UI rendering of eval run history/comparisons (S04 scope).
- Langfuse instrumentation for evaluation operations (R008; later M003 slices).
