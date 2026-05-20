---
id: T02
parent: S02
milestone: M001
key_files:
  - src/db/schema.py
  - tests/test_db.py
  - tests/test_extraction_schema.py
key_decisions:
  - Create post-migration indexes for extraction review fields after nullable ALTER TABLE migrations so legacy Phase 1 databases initialize successfully.
  - Represent compliance_records date/source/risk fields as nullable SQLite scalar columns for dashboard readiness while preserving FK cascade to documents.
duration: ""
verification_result: passed
completed_at: 2026-05-19T22:34:48.305Z
blocker_discovered: false
---

# T02: Added migration-safe Phase 2 SQLite extraction columns and a document-level compliance_records table with dashboard/filter indexes.

**Added migration-safe Phase 2 SQLite extraction columns and a document-level compliance_records table with dashboard/filter indexes.**

## What Happened

Updated `src/db/schema.py` so `init_db()` creates the Phase 2 schema on fresh databases and safely evolves Phase 1-shaped databases. The migration path inspects `PRAGMA table_info(extractions)` and applies nullable `ALTER TABLE` statements for `review_state`, `abstention_reason`, `normalized_value`, and `updated_at` only when missing. Added `compliance_records` keyed by `doc_id` with document-level SDF fields, aggregate confidence/review metadata, trace/run metadata, and nullable dashboard/risk placeholders. Preserved FK enforcement and document cascade behavior. Added schema tests for fresh DB creation, legacy Phase 1 migration preserving rows, idempotent re-runs, FK rejection for unknown documents, and compliance cascade on document deletion. During verification, a legacy migration failure exposed that indexes depending on migrated columns were created too early; moved those indexes to a post-migration step.

## Verification

Ran the task-plan verification suite using the Windows-compatible venv path: `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_schema.py -q` passed with 8 tests. Also ran the extended regression suite including T01 extraction model tests: `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_schema.py tests/test_extraction_models.py -q` passed with 17 tests. The original gate form `./venv/Scripts/python.exe ...` is not valid in this Windows command environment, so verification used `venv/Scripts/python.exe`.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_schema.py -q` | 0 | ✅ pass (8 passed) | 2669ms |
| 2 | `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_schema.py tests/test_extraction_models.py -q` | 0 | ✅ pass (17 passed) | 3175ms |

## Deviations

Used `venv/Scripts/python.exe` instead of the plan's `./venv/Scripts/python.exe` because the gate showed the leading `./` is not recognized in this Windows environment.

## Known Issues

None.

## Files Created/Modified

- `src/db/schema.py`
- `tests/test_db.py`
- `tests/test_extraction_schema.py`
