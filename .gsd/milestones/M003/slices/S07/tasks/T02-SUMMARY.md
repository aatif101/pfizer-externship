---
id: T02
parent: S07
milestone: M003
key_files:
  - src/pipeline/ingest.py
  - src/pipeline/db_writer.py
  - tests/test_tracing.py
  - tests/test_ingest.py
key_decisions:
  - Centralized ingestion/storage trace writes through `safe_update_current_trace` with strict boundary-local allowlists instead of direct Langfuse context calls.
duration: 
verification_result: passed
completed_at: 2026-05-27T21:00:02.031Z
blocker_discovered: false
---

# T02: Hardened ingestion and SQLite storage Langfuse trace updates behind no-op-safe allowlisted metadata helpers.

**Hardened ingestion and SQLite storage Langfuse trace updates behind no-op-safe allowlisted metadata helpers.**

## What Happened

Replaced direct Langfuse context updates in `ingest_document` and `write_document_to_db` with boundary-local wrappers around `safe_update_current_trace`. The ingestion span now emits started/completed/failed operational metadata without paths or raw exception text, and storage emits started/completed/failed operational metadata while preserving existing DB behavior for empty page text and missing image blobs. Added tests for the ingestion/storage allowlist, trace-update no-op behavior, invalid-PDF failure metadata, and lightweight ingestion/storage success paths that avoid real Docling conversion.

## Verification

Ran the required Windows-native pytest command via `gsd_exec` using Node to spawn `venv\\Scripts\\python.exe -m pytest -q tests/test_tracing.py tests/test_ingest.py`; it passed with 20 tests. Also ran a targeted Node scan confirming `src/pipeline/ingest.py` and `src/pipeline/db_writer.py` no longer import/use direct `langfuse_context.update_current_trace` calls.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_tracing.py tests/test_ingest.py` | 0 | ✅ pass — 20 passed, 18 warnings in 92.19s | 97134ms |
| 2 | `node scan for direct langfuse_context.update_current_trace in src/pipeline/ingest.py and src/pipeline/db_writer.py` | 0 | ✅ pass — no direct langfuse_context update calls found | 69ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/pipeline/ingest.py`
- `src/pipeline/db_writer.py`
- `tests/test_tracing.py`
- `tests/test_ingest.py`
