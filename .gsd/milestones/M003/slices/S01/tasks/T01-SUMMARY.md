---
id: T01
parent: S01
milestone: M003
key_files:
  - src/db/schema.py
  - tests/test_eval_db_schema.py
key_decisions:
  - Keep existing `evaluations` table as legacy/back-compat, but introduce `eval_runs` + `eval_metrics` as the canonical evaluation history contract going forward.
duration: 
verification_result: passed
completed_at: 2026-05-21T18:00:59.917Z
blocker_discovered: false
---

# T01: Extended SQLite schema with eval_runs/eval_metrics and gold-label tables plus idempotent init/upgrade coverage tests.

**Extended SQLite schema with eval_runs/eval_metrics and gold-label tables plus idempotent init/upgrade coverage tests.**

## What Happened

- Updated `src/db/schema.py` to add evaluation-focused tables: `eval_runs` (run grouping + status + timestamps + params/error) and `eval_metrics` (per-metric rows keyed to run_id).
- Added minimal, extensible gold-set storage tables: `gold_extraction_labels`, `gold_retrieval_queries`, and `gold_retrieval_targets` (with cascading deletes and a FK to existing `pages(doc_id,page_num)` for target hits).
- Marked the existing `evaluations` table as legacy (backward compatible) and added indexes for new tables.
- Added `tests/test_eval_db_schema.py` to ensure `init_db()` is safe to run repeatedly and will upgrade a minimally-provisioned older schema by creating the new tables.

## Verification

- Ran `pytest` for the new schema tests.
- Confirmed `init_db()` is idempotent (can run twice on the same DB).
- Confirmed `init_db()` can upgrade a legacy-ish DB (with required pre-existing extraction columns for current indexes) and that the new eval/gold tables exist after init.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_eval_db_schema.py -q` | 0 | ✅ pass | 560ms |

## Deviations

Used direct `venv/Scripts/python.exe -m pytest ...` via the `bash` tool for verification because `gsd_exec` uses /bin/bash which is not present in this Windows environment.

## Known Issues

None.

## Files Created/Modified

- `src/db/schema.py`
- `tests/test_eval_db_schema.py`
