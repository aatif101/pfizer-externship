---
id: T02
parent: S03
milestone: M001
key_files:
  - src/db/queries.py
  - src/extraction/providers.py
  - src/extraction/pipeline.py
  - src/extraction/__init__.py
  - tests/test_extraction_pipeline.py
key_decisions:
  - Keep provider integration behind a dependency-free protocol for T02; live Gemini/Claude adapters remain out of scope.
  - Treat ungrounded provider facts conservatively by abstaining rather than persisting confident values when cited spans/pages do not validate against stored page text.
  - Use a named low-confidence threshold where confidence below the threshold becomes needs_review and values at the threshold remain pending.
duration: ""
verification_result: passed
completed_at: 2026-05-20T07:55:01.662Z
blocker_discovered: false
---

# T02: Added an offline fake-provider SDF extraction pipeline that loads ingested pages, normalizes six fields, validates source spans, computes risk, and persists dashboard-ready rows.

**Added an offline fake-provider SDF extraction pipeline that loads ingested pages, normalizes six fields, validates source spans, computes risk, and persists dashboard-ready rows.**

## What Happened

Implemented typed document/page loading helpers in `src/db/queries.py`, a dependency-free provider protocol in `src/extraction/providers.py`, and `extract_document()` orchestration in `src/extraction/pipeline.py`. The pipeline generates a non-secret run ID, loads ordered 0-indexed pages, rejects missing/empty page text with typed failures, calls a fake-compatible provider protocol, normalizes provider payloads into exactly the six SDF fields, synthesizes abstentions for missing values/evidence/invalid pages/span mismatches, marks low-confidence fields for review, computes conservative risk metadata, and persists through `upsert_extraction_record()`. Added integration tests that initialize a temp SQLite DB, insert realistic SDF-style page text, exercise the fake provider path, and assert field rows, compliance row values, source evidence, risk metadata, trace/run metadata, abstentions, low-confidence boundary behavior, and typed failure modes.

## Verification

Ran the task-level verification with a shell-safe virtualenv path: `./venv/Scripts/python.exe -m pytest tests/test_extraction_risk.py tests/test_extraction_pipeline.py -q`, which passed 16 tests. Then ran the broader auto-gate equivalent including model and persistence tests with the same corrected path: `./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_persistence.py tests/test_extraction_risk.py tests/test_extraction_pipeline.py -q`, which passed 32 tests. The original verification failure was due to Bash not resolving `venv/Scripts/python.exe` without a leading `./`, not a test failure.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `./venv/Scripts/python.exe -m pytest tests/test_extraction_risk.py tests/test_extraction_pipeline.py -q` | 0 | ✅ pass (16 passed) | 1070ms |
| 2 | `./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_persistence.py tests/test_extraction_risk.py tests/test_extraction_pipeline.py -q` | 0 | ✅ pass (32 passed) | 1670ms |

## Deviations

Used `./venv/Scripts/python.exe` for verification because the provided Bash command `venv/Scripts/python.exe ...` failed path resolution in this environment. Added the provider protocol and pipeline as planned; no live Gemini dependency was introduced.

## Known Issues

None.

## Files Created/Modified

- `src/db/queries.py`
- `src/extraction/providers.py`
- `src/extraction/pipeline.py`
- `src/extraction/__init__.py`
- `tests/test_extraction_pipeline.py`
