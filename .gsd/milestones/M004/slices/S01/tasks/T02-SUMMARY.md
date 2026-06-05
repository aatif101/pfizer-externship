---
id: T02
parent: S01
milestone: M004
key_files:
  - src/extraction/repository.py
  - tests/test_extraction_persistence.py
key_decisions:
  - Kept run-history writes additive and repository-owned, with record.run_id=None preserving latest-only compatibility.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:11:41.477Z
blocker_discovered: false
---

# T02: Added repository-owned extraction run history persistence and query APIs while preserving latest-write extraction behavior.

**Added repository-owned extraction run history persistence and query APIs while preserving latest-write extraction behavior.**

## What Happened

Updated src/extraction/repository.py to add the ExtractionRunSummary dataclass and run-scoped inspection helpers: get_extraction_record_for_run(), list_compliance_records_for_run(), and list_extraction_run_summaries(). upsert_extraction_record() now keeps the existing latest extractions/compliance_records writes and, when record.run_id is present, also upserts extraction_runs, six extraction_history rows, and one compliance_record_history row in the same transaction. The latest and historical record reads share an internal reconstruction helper so selected-run reads and latest reads cannot drift in field parsing. record.run_id=None remains latest-only compatibility and does not create run/history rows.

## Verification

Ran the focused Windows-safe pytest command via gsd_exec runtime=node spawning venv/Scripts/python.exe. The suite passed: 31 tests covering extraction persistence and extraction pipeline behavior. New tests prove two run IDs for the same document are independently queryable, latest tables contain only the newest six field rows plus one compliance row, history row counts are additive, same run/doc upserts are idempotent, run-filtered compliance rows match latest dashboard shape, run summaries expose bounded metadata/counts, None run IDs skip history, and hostile SQL metacharacter field values persist safely in history.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_extraction_persistence.py tests/test_extraction_pipeline.py` | 0 | ✅ pass — 31 passed | 10129ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/repository.py`
- `tests/test_extraction_persistence.py`
