---
id: T01
parent: S01
milestone: M004
key_files:
  - src/db/schema.py
  - tests/test_extraction_run_history_schema.py
key_decisions:
  - Preserved existing `extractions` and `compliance_records` definitions unchanged and added run-scoped history as additive tables with bounded metadata only.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:07:47.898Z
blocker_discovered: false
---

# T01: Added additive SQLite run-history schema for extraction runs, field history, and compliance history without changing latest-write extraction tables.

**Added additive SQLite run-history schema for extraction runs, field history, and compliance history without changing latest-write extraction tables.**

## What Happened

Updated `src/db/schema.py` to create `extraction_runs`, `extraction_history`, and `compliance_record_history` tables alongside the existing `extractions` and `compliance_records` latest-write tables. The new history tables use foreign keys to `documents` and `extraction_runs` with cascade delete, preserve bounded extraction/compliance metadata, include uniqueness constraints for per-run document field/compliance records, and add run-ordering plus run/document lookup indexes. Added `tests/test_extraction_run_history_schema.py` to validate table and index creation, idempotent initialization, the confidentiality boundary for forbidden raw-content/path columns, and FK rejection for missing parent run/document identities.

## Verification

Ran the required verification command through `gsd_exec` with a node wrapper invoking `venv\Scripts\python.exe -m pytest -q tests/test_extraction_run_history_schema.py tests/test_db.py`. The suite passed with 8 tests, confirming fresh DB initialization, idempotency, latest DB compatibility, no forbidden history columns, and FK enforcement for orphaned history rows.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_extraction_run_history_schema.py tests/test_db.py` | 0 | ✅ pass | 3586ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/db/schema.py`
- `tests/test_extraction_run_history_schema.py`
