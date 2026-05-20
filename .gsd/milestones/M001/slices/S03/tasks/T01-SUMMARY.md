---
id: T01
parent: S03
milestone: M001
key_files:
  - src/extraction/risk.py
  - tests/test_extraction_risk.py
  - tests/test_extraction_persistence.py
  - src/extraction/models.py
  - src/extraction/repository.py
key_decisions:
  - Use calendar-year anniversary cutoffs for 2-year and 3-year SDF risk thresholds while persisting actual elapsed `age_days`.
duration: ""
verification_result: passed
completed_at: 2026-05-20T04:44:06.354Z
blocker_discovered: false
---

# T01: Added and verified conservative SDF risk metadata computation and SQLite round-trip assertions for dashboard compliance rows.

**Added and verified conservative SDF risk metadata computation and SQLite round-trip assertions for dashboard compliance rows.**

## What Happened

Implemented the remaining T01 behavior around document risk metadata. The extraction models and repository already carried `risk_reason` and `age_days`, and repository upsert/reconstruction already used them; I fixed the stale persistence assertion so `list_compliance_records()` must expose the persisted risk fields instead of nulls. I reviewed the existing pure `src/extraction/risk.py` implementation, corrected its threshold classification to use calendar-year anniversary cutoffs for the two-year and three-year policy boundaries, and kept `age_days` as the actual elapsed day count. This preserves conservative handling for expired, malformed, missing, abstained, and future dates while avoiding leap-year misclassification.

## Verification

Ran the authoritative T01 pytest suite for extraction models, persistence, and risk policy: `venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_persistence.py tests/test_extraction_risk.py -q` passed with 24 tests. Also ran schema verification due the task's requirement-impact note: `venv/Scripts/python.exe -m pytest tests/test_extraction_schema.py -q` passed with 5 tests.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_persistence.py tests/test_extraction_risk.py -q` | 0 | ✅ pass | 2560ms |
| 2 | `venv/Scripts/python.exe -m pytest tests/test_extraction_schema.py -q` | 0 | ✅ pass | 1929ms |

## Deviations

The model/repository risk fields and `src/extraction/risk.py` already existed before this task execution. Work focused on correcting the remaining stale persistence assertion and leap-year threshold behavior rather than creating those files from scratch.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/risk.py`
- `tests/test_extraction_risk.py`
- `tests/test_extraction_persistence.py`
- `src/extraction/models.py`
- `src/extraction/repository.py`
