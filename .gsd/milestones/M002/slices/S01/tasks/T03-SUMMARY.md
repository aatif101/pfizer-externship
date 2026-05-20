---
id: T03
parent: S01
milestone: M002
key_files:
  - src/retrieval/cli.py
  - src/retrieval/__main__.py
  - tests/test_retrieval_cli.py
key_decisions:
  - Retrieval CLI performs a read-only preflight for existing documents/pages tables before the indexer initializes retrieval-specific schema, preventing typoed database paths from creating empty databases.
  - Retrieval CLI output is a compact one-line key=value health surface using safe reason codes and hash prefixes only.
duration: 
verification_result: passed
completed_at: 2026-05-20T21:03:19.010Z
blocker_discovered: false
---

# T03: Added a provider-free retrieval index CLI with build/status commands, safe reason-coded diagnostics, and module execution via python -m src.retrieval.

**Added a provider-free retrieval index CLI with build/status commands, safe reason-coded diagnostics, and module execution via python -m src.retrieval.**

## What Happened

Created `src/retrieval/cli.py` with Typer `build` and `status` commands that require `--db-path`, preflight the target SQLite file for existing ingestion source tables, and then call the existing deterministic indexer. The CLI emits compact key=value diagnostics for status, run_id, indexed_docs, indexed_pages, source_pages, content hash prefixes, stale state, and reason codes while excluding filenames, raw page text, image blobs, provider responses, and secrets. Added `src/retrieval/__main__.py` so developers can run the surface as `python -m src.retrieval`. Added `tests/test_retrieval_cli.py` covering successful build/status, status before build as missing, empty corpus build/status, stale status after source mutation, missing database/schema errors, and SQL-like filename/page text sanitization. The only code correction during verification was moving `RetrievalIndexBuildResult` import from `models.py` to `indexer.py`, where it is defined.

## Verification

Ran the combined retrieval slice test set with the Windows-compatible venv invocation, because the prior gate failure came from `./venv/Scripts/python.exe` being invalid in the current Windows shell. Also smoke-tested the promised module entrypoint with `python -m src.retrieval --help` and confirmed the build/status commands are exposed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py` | 0 | ✅ pass | 4313ms |
| 2 | `venv/Scripts/python.exe -m src.retrieval --help` | 0 | ✅ pass | 607ms |

## Deviations

Used `venv/Scripts/python.exe` instead of `./venv/Scripts/python.exe` for verification because the shell rejected the leading `./` form on Windows.

## Known Issues

None.

## Files Created/Modified

- `src/retrieval/cli.py`
- `src/retrieval/__main__.py`
- `tests/test_retrieval_cli.py`
