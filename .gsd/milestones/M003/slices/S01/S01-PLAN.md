# S01: Evaluation DB contract and adapters

**Goal:** Define and implement the SQLite evaluation storage contract (gold sets + eval run history + metric rows) plus adapter/query helpers that are Streamlit-safe (idempotent, rerun-friendly) and future-proof for extraction, retrieval, and RAG evaluation slices.
**Demo:** Create or upgrade SQLite schema to include gold labels plus eval run tables, and add query helpers that can insert and list eval runs and metrics without Streamlit rerun duplication.

## Must-Haves

- `init_db()` creates/migrates eval-related tables idempotently on an existing Phase 1/2 DB.
- Code can insert an eval run + metric rows and list recent runs/metrics without duplicating rows on Streamlit reruns.
- Gold sets can be stored and queried (even if empty) without crashing downstream computations.
- New query helpers remain credential-free and do not import provider/LLM code.
- Unit tests cover schema init, insert/list behavior, and empty-state behavior using a temporary SQLite file.

## Proof Level

- This slice proves: contract + integration (SQLite schema + repository boundary)

## Integration Closure

- Extends existing DB boundary in `src/db/schema.py` and `src/db/queries.py`.
- Introduces a dedicated eval repository module under `src/eval/` used by future metric computation code and the Streamlit Eval tab.
- Adds regression tests under `tests/` to lock the contract for downstream slices (S02–S04).

## Verification

- Adds persisted eval run history (run status, timestamps, error_reason) and metric rows that become the primary inspection surface for evaluation failures/empty states in the dashboard.

## Tasks

- [x] **T01: Define eval DB schema and migrations (runs, metrics, gold sets)** `est:1.5h`
  Why: S02–S04 need a stable, queryable contract for evaluation history and gold labels; current `evaluations` table is too underspecified (no run grouping, no gold storage, no status/error fields).
  - Files: `src/db/schema.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_eval_db_schema.py -q

- [x] **T02: Add eval repository/query helpers for insert/list without rerun duplication** `est:2h`
  Why: Streamlit reruns can easily double-insert metrics. We need idempotent helpers and a single module boundary that downstream metric code and the dashboard can call safely.
  - Files: `src/eval/repository.py`, `src/eval/__init__.py`, `src/db/schema.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_eval_repository.py -q

- [x] **T03: Add contract tests for eval schema + repository behaviors (empty states, idempotency)** `est:1.5h`
  Why: Downstream slices will rely on this contract; tests prevent accidental schema drift and prove offline-safe behavior.
  - Files: `tests/test_eval_db_schema.py`, `tests/test_eval_repository.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_eval_db_schema.py tests/test_eval_repository.py -q

## Files Likely Touched

- src/db/schema.py
- src/eval/repository.py
- src/eval/__init__.py
- tests/test_eval_db_schema.py
- tests/test_eval_repository.py
