---
id: T01
parent: S02
milestone: M001
key_files:
  - src/extraction/__init__.py
  - src/extraction/models.py
  - tests/test_extraction_models.py
key_decisions:
  - Modeled required SDF fields as a closed enum and required SDFExtractionRecord.fields to contain exactly those six fields.
  - Required non-abstained fields to include source verbatim_span while permitting abstained fields to omit spans when an abstention reason is present.
duration: ""
verification_result: passed
completed_at: 2026-05-19T22:28:30.867Z
blocker_discovered: false
---

# T01: Added a strict Pydantic v2 SDF extraction contract with validation coverage for required fields, evidence, confidence, review, and abstention states.

**Added a strict Pydantic v2 SDF extraction contract with validation coverage for required fields, evidence, confidence, review, and abstention states.**

## What Happened

Created the new src/extraction package and implemented enum-backed SDF field and review-state models, source evidence validation, field-level extraction validation, and document-level SDFExtractionRecord accessors. The contract enforces exactly the six required SDF fields, rejects malformed confidence/page/bbox/value states before persistence, supports trace/run metadata, and exposes dashboard-friendly aggregate confidence, review state, review flag, and normalized value mappings. Added tests that cover a full valid six-field sample record, an accepted abstained field, and the specified negative validation cases.

## Verification

Ran the task-required command `./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py -q`; all 9 extraction model tests passed. This verifies full-record acceptance, abstention acceptance, and rejection of unknown field names, out-of-range confidence, negative source pages, malformed bbox values, missing non-abstained values, abstention without reason, and missing required record fields.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py -q` | 0 | ✅ pass (9 passed) | 2223ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/__init__.py`
- `src/extraction/models.py`
- `tests/test_extraction_models.py`
