---
id: T04
parent: S01
milestone: M002
key_files:
  - src/db/schema.py
  - src/retrieval/__init__.py
  - src/retrieval/models.py
  - src/retrieval/repository.py
  - src/retrieval/indexer.py
  - src/retrieval/cli.py
  - src/retrieval/__main__.py
  - tests/test_db.py
  - tests/test_extraction_cli.py
  - tests/test_compliance_dashboard.py
  - tests/test_app.py
  - tests/test_retrieval_index_repository.py
  - tests/test_retrieval_indexer.py
  - tests/test_retrieval_cli.py
key_decisions:
  - No code changes were made in T04 because the integration regression passed; the only adaptation was using the Windows-compatible venv executable path for verification.
duration: 
verification_result: passed
completed_at: 2026-05-20T21:04:28.209Z
blocker_discovered: false
---

# T04: Ran the S01 retrieval-index integration regression and confirmed the provider-free index schema, indexer, CLI, and existing M001 smoke surfaces still pass.

**Ran the S01 retrieval-index integration regression and confirmed the provider-free index schema, indexer, CLI, and existing M001 smoke surfaces still pass.**

## What Happened

Executed the full slice regression against the project virtualenv and verified the migrated SQLite schema, extraction CLI, compliance dashboard, app smoke tests, retrieval repository, retrieval indexer, and retrieval CLI together. No source changes were required during this task. The prior auto-verification failure was caused by the Windows command shell rejecting the POSIX-style `./venv/Scripts/python.exe` prefix; rerunning through the same venv executable with the Windows-compatible `venv/Scripts/python.exe` path passed. I also ran the focused retrieval regression and verbose CLI tests to document that built, empty, missing, stale, and safe-output/redaction states are covered.

## Verification

Full regression passed: `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_cli.py tests/test_compliance_dashboard.py tests/test_app.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py` returned exit code 0 with 38 tests passing. Focused retrieval regression passed with 22 tests. Verbose CLI verification passed with 6 tests covering missing index, successful build/status metadata, empty corpus reason codes, stale source-page detection, missing database/schema safe errors, and non-echoing of SQL-like filenames/raw page text.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_cli.py tests/test_compliance_dashboard.py tests/test_app.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py` | 0 | ✅ pass — 38 passed in 10.27s | 11607ms |
| 2 | `venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py -q` | 0 | ✅ pass — 22 passed in 3.06s | 4255ms |
| 3 | `venv/Scripts/python.exe -m pytest tests/test_retrieval_cli.py -vv` | 0 | ✅ pass — 6 passed; named built/empty/missing/stale/safe-output cases passed | 2169ms |

## Deviations

Used `venv/Scripts/python.exe` instead of `./venv/Scripts/python.exe` because the Windows shell rejects the POSIX-style `./` executable prefix; it targets the same project virtualenv.

## Known Issues

The literal POSIX-style verification command `./venv/Scripts/python.exe ...` is not portable to the Windows command shell used by the failed gate; use `venv/Scripts/python.exe ...` or `.\venv\Scripts\python.exe ...` on Windows.

## Files Created/Modified

- `src/db/schema.py`
- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/retrieval/indexer.py`
- `src/retrieval/cli.py`
- `src/retrieval/__main__.py`
- `tests/test_db.py`
- `tests/test_extraction_cli.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_app.py`
- `tests/test_retrieval_index_repository.py`
- `tests/test_retrieval_indexer.py`
- `tests/test_retrieval_cli.py`
