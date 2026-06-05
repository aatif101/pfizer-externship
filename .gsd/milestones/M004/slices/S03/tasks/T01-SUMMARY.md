---
id: T01
parent: S03
milestone: M004
key_files:
  - src/db/schema.py
  - src/eval/repository.py
  - tests/test_extraction_usage_observations.py
  - tests/test_eval_db_schema.py
key_decisions:
  - Mirrored the existing bounded RAG observation repository pattern for extraction usage, but with extraction-specific run_id/doc_id/stage/status filters and sanitized error_reason only.
  - Kept optional numeric telemetry nullable rather than defaulting missing values to zero, and rejected malformed numeric inputs before DB writes.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:42:18.304Z
blocker_discovered: false
---

# T01: Added a bounded SQLite repository surface for extraction usage observations keyed by run, document, stage, and status.

**Added a bounded SQLite repository surface for extraction usage observations keyed by run, document, stage, and status.**

## What Happened

Added the additive `extraction_usage_observations` table in `src/db/schema.py` with run/document foreign keys, stage/provider/model/status metadata, nullable latency/token/cost fields, trace ID, sanitized error reason, created timestamp, and indexes for run_id, doc_id, stage, status, and run/doc/stage filtering. Extended `src/eval/repository.py` with the frozen `ExtractionUsageObservationRow` type plus `insert_extraction_usage_observation()` and `list_extraction_usage_observations()` helpers. The insert path normalizes nullable numeric fields before opening the write transaction, rejects bools for integer token counts, rejects malformed numeric values and non-finite floats, uses parameterized SQL, and rolls back SQLite failures before surfacing normal repository exceptions. Added focused tests for schema idempotence/indexing/bounded columns, repeated run/doc/stage rows, filters, default list limit, NULL optional metrics, FK rollback, and malformed numeric rejection without partial writes.

## Verification

Ran the required Windows-safe pytest gate via `gsd_exec` node wrapper: `venv\Scripts\python.exe -m pytest -q tests/test_extraction_usage_observations.py tests/test_eval_db_schema.py` passed with 10 tests. Also ran `venv\Scripts\python.exe -m pytest -q tests/test_eval_repository.py` as a regression check because the shared numeric coercion helper was hardened; all 8 tests passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_extraction_usage_observations.py tests/test_eval_db_schema.py` | 0 | ✅ pass | 5749ms |
| 2 | `venv\Scripts\python.exe -m pytest -q tests/test_eval_repository.py` | 0 | ✅ pass | 6711ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/db/schema.py`
- `src/eval/repository.py`
- `tests/test_extraction_usage_observations.py`
- `tests/test_eval_db_schema.py`
