---
id: T01
parent: S05
milestone: M001
key_files:
  - tests/test_s05_end_to_end_proof.py
key_decisions:
  - Use an in-test dependency-free raw PDF generator instead of committing a generated fixture or relying on tests/fixtures/sample.pdf.
duration: ""
verification_result: passed
completed_at: 2026-05-20T19:17:20.533Z
blocker_discovered: false
---

# T01: Added and verified the S05 realistic offline PDF ingestion-to-extraction-to-dashboard proof test.

**Added and verified the S05 realistic offline PDF ingestion-to-extraction-to-dashboard proof test.**

## What Happened

Added `tests/test_s05_end_to_end_proof.py`, a deterministic final-assembly proof that generates a realistic one-page SDF PDF at runtime, ingests it with the real Docling ingestion path, verifies persisted page text contains all required SDF spans, runs the real extraction pipeline with a credential-free fake provider grounded in those spans, persists extraction and compliance rows, verifies amber risk and age metadata, and checks dashboard adapter formatting.

## Verification

Ran `venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py -q`; result: 1 passed, 15 warnings in 53.65s.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py -q` | 0 | ✅ pass | 58400ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `tests/test_s05_end_to_end_proof.py`
