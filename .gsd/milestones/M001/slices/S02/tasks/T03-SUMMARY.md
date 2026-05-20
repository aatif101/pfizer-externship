---
id: T03
parent: S02
milestone: M001
key_files:
  - src/extraction/repository.py
  - tests/test_extraction_persistence.py
key_decisions:
  - Use SQLite foreign-key enforcement rather than pre-checks so missing parent documents raise `sqlite3.IntegrityError` at the repository boundary.
  - Use deterministic compliance ordering by non-null expiry date, expiry date ascending, vendor name, then doc_id for S04 dashboard consumption.
  - Persist document-level source evidence from expiry date when available, otherwise from the first non-abstained field so abstained expiry records still have inspectable source context.
duration: ""
verification_result: passed
completed_at: 2026-05-19T22:46:58.353Z
blocker_discovered: false
---

# T03: Added idempotent SQLite persistence and retrieval helpers for validated SDF extraction records.

**Added idempotent SQLite persistence and retrieval helpers for validated SDF extraction records.**

## What Happened

Implemented `src/extraction/repository.py` with field-level and document-level persistence helpers: `upsert_extraction_field`, `upsert_extraction_record`, `get_extraction_record`, and `list_compliance_records`. Each validated `SDFExtractionRecord` now persists exactly six rows in `extractions` plus one dashboard-ready row in `compliance_records`, carrying trace/run metadata, confidence, source page, bbox JSON, verbatim evidence, normalized values, review state, needs-review flags, and abstention reasons. Added deterministic persistence tests covering FK rejection for missing documents, idempotent updates, SQL metacharacter round-trips, abstention persistence, aggregate compliance review state, single-field replacement, and S04-oriented list ordering/shape. The auto-gate failure was due to the command form `./venv/Scripts/python.exe` being interpreted by a Windows shell; the same checks pass with `venv/Scripts/python.exe` in this environment.

## Verification

Verified targeted extraction contract/schema/persistence tests, the prior failing schema/database gate test set, and the full repository pytest suite using the project Python 3.11 venv. Targeted T03 tests passed with 21 tests. The previously failed gate set passed with 8 tests. The full suite passed with 36 tests; only third-party deprecation warnings were emitted.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_schema.py tests/test_extraction_persistence.py -q` | 0 | ✅ pass — 21 passed | 3078ms |
| 2 | `venv/Scripts/python.exe -m pytest -q` | 0 | ✅ pass — 36 passed, 19 warnings | 101042ms |
| 3 | `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_schema.py -q` | 0 | ✅ pass — 8 passed | 2356ms |

## Deviations

Used `venv/Scripts/python.exe` instead of `./venv/Scripts/python.exe` for verification because the latter is not recognized by the Windows command shell used by the auto-gate. No product-code deviation from the task plan.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/repository.py`
- `tests/test_extraction_persistence.py`
