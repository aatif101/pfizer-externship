---
id: T02
parent: S01
milestone: M002
key_files:
  - src/retrieval/indexer.py
  - src/retrieval/models.py
  - src/retrieval/repository.py
  - src/db/schema.py
  - tests/test_retrieval_indexer.py
key_decisions:
  - Run IDs are deterministic from index status plus corpus hash prefix so repeated builds of the same corpus remain stable while stale status compares the latest persisted hash against the current source fingerprint.
  - Page snippets are persisted as short whitespace-normalized prefixes; full page text remains confined to the repository/indexer input boundary and optional FTS table.
duration: 
verification_result: passed
completed_at: 2026-05-20T20:56:57.448Z
blocker_discovered: false
---

# T02: Added a deterministic provider-free retrieval indexer that builds SQLite page index metadata and reports missing, built, empty, and stale corpus states.

**Added a deterministic provider-free retrieval indexer that builds SQLite page index metadata and reports missing, built, empty, and stale corpus states.**

## What Happened

Implemented `src/retrieval/indexer.py` to read only ingested SQLite documents/pages with nonblank text, normalize page text, compute deterministic corpus fingerprints, generate short safe snippets, persist built/empty runs, and provide a non-mutating status helper for missing/built/empty/stale states. Extended retrieval index metadata with snippets and an idempotent migration, plus a transactional repository write path that clears and rewrites current page index rows atomically so failed page writes roll back to the previous inspectable state. Added indexer tests covering built metadata, empty corpus, blank/non-ingested exclusion, stale detection after text changes, rebuild status, deterministic run IDs/page ordering, safe diagnostics, transactional rollback, and extraction CLI regression coverage. The auto-mode verification failure was caused by the Windows shell rejecting `./venv/...`; reran equivalent gates with `venv/Scripts/python.exe` successfully.

## Verification

Verified Python syntax for changed retrieval files, ran the task-specific retrieval repository/indexer suite, reran the original failed auto-mode gate with a shell-compatible venv path, and ran extraction CLI regression tests alongside the new indexer suite. All verification commands passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python - <<'PY'
from pathlib import Path
for p in ['src/retrieval/repository.py','src/retrieval/indexer.py','src/db/schema.py','tests/test_retrieval_indexer.py']:
    compile(Path(p).read_text(), p, 'exec')
    print('compiled', p)
PY` | 0 | ✅ pass | 237ms |
| 2 | `venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py` | 0 | ✅ pass (16 passed) | 3647ms |
| 3 | `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_retrieval_index_repository.py` | 0 | ✅ pass (10 passed) | 2562ms |
| 4 | `venv/Scripts/python.exe -m pytest tests/test_retrieval_indexer.py tests/test_extraction_cli.py` | 0 | ✅ pass (15 passed) | 3929ms |

## Deviations

Used `venv/Scripts/python.exe` instead of `./venv/Scripts/python.exe` for verification because the auto-mode failure showed the latter path form is not accepted by the Windows command runner.

## Known Issues

None.

## Files Created/Modified

- `src/retrieval/indexer.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/db/schema.py`
- `tests/test_retrieval_indexer.py`
