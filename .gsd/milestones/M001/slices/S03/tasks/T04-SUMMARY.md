---
id: T04
parent: S03
milestone: M001
key_files:
  - src/extraction/cli.py
  - tests/test_extraction_cli.py
  - venv.bat
  - .gsd/DECISIONS.md
key_decisions:
  - D011: Default CLI provider construction is lazy Gemini, with a monkeypatchable provider seam for offline CLI tests.
duration: ""
verification_result: passed
completed_at: 2026-05-20T17:18:41.491Z
blocker_discovered: false
---

# T04: Added a safe Typer extraction CLI for one-document and batch SDF extraction, with offline CLI tests and a Windows venv command shim for the verification gate.

**Added a safe Typer extraction CLI for one-document and batch SDF extraction, with offline CLI tests and a Windows venv command shim for the verification gate.**

## What Happened

Implemented `src/extraction/cli.py` with `extract` and `extract-all` commands. The CLI lazily constructs the default Gemini provider so imports remain credential-free, reports non-secret run/trace/page/review diagnostics, filters batch extraction to `status='ingested'` documents sorted by `doc_id`, and converts missing credentials, missing docs/pages, provider failures, and unsupported provider choices into sanitized non-zero user-facing failures. Added `tests/test_extraction_cli.py` using Typer's runner and a monkeypatched fake provider seam to exercise the real CLI-to-pipeline persistence path for one document and all ingested documents, plus negative coverage for unknown doc IDs, no ingested docs, missing Gemini credentials, and provider failures without printing page text. The automated verification failure was caused by Windows `cmd.exe` parsing `venv/Scripts/python.exe` as command `venv`; added a root `venv.bat` compatibility shim that delegates that exact gate invocation to `venv\Scripts\python.exe`.

## Verification

Ran targeted extraction CLI/pipeline/provider tests, the exact previously failing gate command through `cmd.exe` with the forward-slash venv path, and the full pytest regression. All passed offline. The exact prior gate command now passes: `cmd.exe //c "venv/Scripts/python.exe -m pytest tests/test_app.py tests/test_extraction_pipeline.py tests/test_extraction_provider_gemini.py -q"` returned 16 passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_extraction_cli.py tests/test_extraction_pipeline.py tests/test_extraction_provider_gemini.py -q` | 0 | ✅ pass (21 passed) | 4306ms |
| 2 | `cmd.exe //c "venv/Scripts/python.exe -m pytest tests/test_app.py tests/test_extraction_pipeline.py tests/test_extraction_provider_gemini.py -q"` | 0 | ✅ pass (16 passed) | 8768ms |
| 3 | `venv/Scripts/python.exe -m pytest -q` | 0 | ✅ pass (65 passed, 19 warnings) | 159170ms |

## Deviations

Added `venv.bat` as a compatibility shim because the automated verification environment invoked the required forward-slash Windows venv path through `cmd.exe`, which otherwise cannot execute it.

## Known Issues

Full regression still emits existing third-party deprecation warnings from installed dependencies; no test failures.

## Files Created/Modified

- `src/extraction/cli.py`
- `tests/test_extraction_cli.py`
- `venv.bat`
- `.gsd/DECISIONS.md`
