---
id: S01
parent: M003
milestone: M003
provides:
  - SQLite schema contract for eval run history and gold sets.
  - Repository helpers for run lifecycle + metric upserts suitable for Streamlit reruns.
  - Contract tests locking schema/init and repository semantics for S02–S04.
requires:
  []
affects:
  []
key_files:
  - src/db/schema.py
  - src/eval/repository.py
  - src/eval/__init__.py
  - tests/test_eval_db_schema.py
  - tests/test_eval_repository.py
key_decisions:
  - Keep legacy `evaluations` table for back-compat while introducing `eval_runs` + `eval_metrics` as canonical evaluation history tables.
  - Use a unique index using COALESCE(scope_type/scope_id,'') for metric deduping so NULL-scoped metrics are properly deduped under SQLite, and upsert via ON CONFLICT DO UPDATE.
patterns_established:
  - Evaluation persistence lives under `src/eval/` as a credential-free repository boundary decoupled from any provider/LLM code.
  - Streamlit rerun-safety for DB writes is achieved via deterministic dedupe keys + upsert semantics (UNIQUE index + ON CONFLICT DO UPDATE).
  - Empty-state behavior is enforced via repository list helpers returning empty lists and via contract tests.
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-05-21T18:49:40.432Z
blocker_discovered: false
---

# S01: S01

**Implemented the SQLite evaluation storage contract (eval runs, metrics, and gold sets) plus Streamlit-safe repository helpers and contract tests.**

## What Happened

This slice established the DB contract that downstream evaluation slices will rely on.

Work completed:
- Extended `src/db/schema.py` with canonical evaluation history tables: `eval_runs` (run grouping with status, timestamps, params, and error_reason) and `eval_metrics` (metric rows keyed to `run_id`). The legacy `evaluations` table remains for back-compat but is no longer the preferred contract.
- Added gold-set tables to support future extraction and retrieval/RAG evaluation without crashing on empty prerequisites: `gold_extraction_labels`, `gold_retrieval_queries`, and `gold_retrieval_targets`.
- Introduced `src/eval/` as a provider/credential-free persistence boundary. `src/eval/repository.py` implements helpers to create/list runs, mark completion/error, upsert metrics, and read gold tables.
- Ensured Streamlit rerun safety by implementing metric upserts using a unique dedupe index that treats NULL scope values consistently (via COALESCE) and `ON CONFLICT DO UPDATE`, preventing duplicate metric rows.
- Added and validated contract tests that prove idempotent `init_db()` behavior, schema upgrade behavior, empty-state handling, and upsert/idempotency semantics for runs/metrics.

This slice provides a stable, queryable evaluation run history surface and gold-set storage so S02–S04 can compute metrics and render UI without needing provider configuration and without duplicating rows across reruns.

## Verification

All slice-plan verification checks passed.

Commands executed (via gsd_exec runtime=node spawning the project venv Python on Windows):
- venv\\Scripts\\python.exe -m pytest tests/test_eval_db_schema.py -q
- venv\\Scripts\\python.exe -m pytest tests/test_eval_repository.py -q
- venv\\Scripts\\python.exe -m pytest tests/test_eval_db_schema.py tests/test_eval_repository.py -q

Results:
- tests/test_eval_db_schema.py: 2 passed
- tests/test_eval_repository.py: 4 passed
- combined: 6 passed

## Requirements Advanced

- R007 — Established the SQLite-backed evaluation run and gold-set storage contract and repository boundary needed for repeatable extraction/retrieval/RAG metric computation and run history inspection in M003.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

Used gsd_exec runtime=node to spawn Windows venv Python because gsd_exec runtime=bash requires /bin/bash which is not present in this environment.

## Known Limitations

Gold set tables are defined and queryable, but this slice does not populate gold data or compute any metrics; downstream slices will implement those computations and inserts.

## Follow-ups

Implement metric computation and insertion (S02 extraction F1, S03 retrieval/RAG metrics) and wire run history into the Streamlit Eval tab (S04).

## Files Created/Modified

- `src/db/schema.py` — Added eval_runs/eval_metrics and gold label/query/target tables; kept legacy evaluations table for back-compat; added indexes and ensured idempotent init/upgrade behavior.
- `src/eval/repository.py` — Added provider-free SQLite repository helpers for creating/listing eval runs, marking status, upserting metrics with rerun-safe dedupe keys, and listing gold set rows.
- `src/eval/__init__.py` — Introduced eval package export surface.
- `tests/test_eval_db_schema.py` — Contract tests for init_db idempotency and schema upgrade behavior for eval/gold tables.
- `tests/test_eval_repository.py` — Contract tests for run lifecycle helpers, metric upsert deduplication, and empty-state list helpers.
