---
id: S01
parent: M002
milestone: M002
provides:
  - A repeatable retrieval index build command over existing SQLite ingested pages.
  - A status command and typed service helpers for missing, built, empty, and stale states.
  - Safe page-level index rows and snippets for S02 retrieval scoring and evidence snippets.
  - Deterministic corpus fingerprinting to detect stale indexes after source corpus mutation.
  - Regression-proof schema migration that does not break M001 ingestion, extraction, dashboard, or app smoke tests.
requires:
  []
affects:
  - S02
  - S03
  - S04
  - S05
key_files:
  - src/db/schema.py
  - src/retrieval/__init__.py
  - src/retrieval/models.py
  - src/retrieval/repository.py
  - src/retrieval/indexer.py
  - src/retrieval/cli.py
  - src/retrieval/__main__.py
  - tests/test_retrieval_index_repository.py
  - tests/test_retrieval_indexer.py
  - tests/test_retrieval_cli.py
  - tests/test_db.py
  - tests/test_extraction_cli.py
  - tests/test_compliance_dashboard.py
  - tests/test_app.py
key_decisions:
  - Repository DTO outputs exclude raw page text; raw text is accepted only at the repository/indexer input boundary and optional FTS5 storage.
  - FTS5 support is optional and guarded during init_db so SQLite builds without FTS5 still support retrieval index metadata and page rows.
  - Run IDs and corpus fingerprints are deterministic for stable repeatability and stale detection.
  - CLI output is compact key=value operator diagnostics with reason codes and hash prefixes only.
  - CLI preflights existing ingestion tables before initializing retrieval schema, preventing typoed DB paths from creating misleading empty databases.
patterns_established:
  - Provider-free retrieval service boundary under src/retrieval for M002.
  - SQLite-backed index metadata plus page-level snippets as the inspectable source for downstream retrievers.
  - Safe status model for missing, built, empty, and stale retrieval index states.
  - Windows-compatible verification invocation using venv/Scripts/python.exe.
observability_surfaces:
  - python -m src.retrieval status --db-path <db> health/status command.
  - python -m src.retrieval build --db-path <db> build summary command.
  - Persisted retrieval_index_runs metadata: status, run_id, built_at, source doc/page counts, indexed counts, content hash, and reason.
  - Persisted retrieval_index_pages rows with stable doc/page identifiers, display page numbers, normalized snippets, and source hash metadata.
drill_down_paths:
  - .gsd/milestones/M002/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S01/tasks/T02-SUMMARY.md
  - .gsd/milestones/M002/slices/S01/tasks/T03-SUMMARY.md
  - .gsd/milestones/M002/slices/S01/tasks/T04-SUMMARY.md
  - .gsd/exec/add69b82-e8f8-4e1c-9b4d-16a810567b15.stdout
duration: ""
verification_result: passed
completed_at: 2026-05-20T21:06:11.937Z
blocker_discovered: false
---

# S01: Persisted Retrieval Index Setup

**Implemented an offline-safe SQLite retrieval indexing foundation with persisted run metadata, page-level index rows, deterministic corpus fingerprinting, and a repeatable CLI for built, empty, missing, and stale states.**

## What Happened

S01 established the durable retrieval-index boundary needed before ranking, RAG generation, and Streamlit Chat can be trusted. The existing SQLite schema now initializes idempotent retrieval_index_runs and retrieval_index_pages tables plus optional guarded FTS5 support without regressing M001 ingestion/extraction tables. The new src/retrieval package provides typed DTOs for run metadata, page records, corpus fingerprints, status values, and safe display page numbers while preserving the existing internal 0-indexed pages.page_num contract.

A provider-free indexer now reads only ingested documents and nonblank page_text rows from SQLite, normalizes text, computes deterministic corpus fingerprints from stable source fields, persists short safe snippets, writes build metadata and page rows transactionally, and reports missing, built, empty, and stale states without requiring Gemini, Claude, Langfuse, GPU, Qdrant, or network access. The repository hides FTS details and confines raw page text to the indexing boundary; downstream code receives safe metadata, snippets, scores/counts, and hash prefixes rather than full raw page text.

The developer-facing CLI surface is available through python -m src.retrieval with build and status commands. It preflights the database so typoed paths or missing ingestion tables produce safe nonzero diagnostics rather than silently creating empty state, and it prints concise key=value output with status, run_id, indexed document/page counts, source counts, content hash prefix, stale boolean, and reason codes. Tests cover successful builds, missing-index status before build, empty corpora, blank-page exclusion, stale detection after page text mutation, deterministic run IDs/order, transactional rollback, optional FTS behavior, malicious SQL-like filenames/page text, and safe output that excludes raw page text/secrets.

Closeout verification initially failed only because the gate used a POSIX-style ./venv/Scripts/python.exe prefix that is not accepted by the Windows command runner. The same project virtualenv was rerun through the Windows-compatible venv/Scripts/python.exe path and passed the full slice regression.

## Verification

Fresh closeout verification was run through gsd_exec using the project Python 3.11 virtualenv with the Windows-compatible executable path:

`venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_cli.py tests/test_compliance_dashboard.py tests/test_app.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py`

Result: exit code 0; 38 tests passed in 10.27s; no stderr. Evidence artifact: `.gsd/exec/add69b82-e8f8-4e1c-9b4d-16a810567b15.stdout`.

Task-level evidence also passed: repository/schema tests, indexer state tests, CLI tests, module help smoke test, focused retrieval regression, extraction CLI regression, dashboard/app smoke tests, and verbose CLI state tests. The tests explicitly prove built, empty, missing, stale, safe-output, SQL metacharacter safety, optional FTS5, deterministic fingerprinting, transactional rollback, and no regression to existing M001 schema/import surfaces.

## Requirements Advanced

- R005 — Established the persisted page-level text index foundation and safe snippets required before grounded Q&A retrieval and citations can be implemented.
- R008 — Added diagnosable retrieval operations through persisted metadata and CLI reason-coded status/build output without secret leakage.
- R009 — Verified the slice through the project Python 3.11 virtualenv.
- R010 — Kept indexing and CLI provider-free and verified output excludes raw page text, provider responses, API keys, and image blobs.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

The planned POSIX-style command `./venv/Scripts/python.exe ...` failed in the Windows command runner with `'.' is not recognized`; closeout used the same virtualenv through `venv/Scripts/python.exe ...`, which passed. No source changes were required during closeout.

## Known Limitations

S01 intentionally does not implement retrieval ranking, evidence thresholds, RAG answer generation, Streamlit Chat, Qdrant, visual retrieval, or live provider calls. CLI/status output is an operator health surface, not an end-user search API.

## Follow-ups

S02 should consume the persisted retrieval_index_pages rows, safe snippets, display page numbers, status helper, and content hash metadata to implement hybrid retrieval and evidence gating. Future verification commands on Windows should prefer `venv/Scripts/python.exe` or `.\venv\Scripts\python.exe` over `./venv/Scripts/python.exe`.

## Files Created/Modified

- `src/db/schema.py` — Added idempotent retrieval index tables, indexes, snippet migration, and optional guarded FTS5 schema initialization.
- `src/retrieval/__init__.py` — Introduced retrieval package boundary.
- `src/retrieval/models.py` — Added typed retrieval index DTOs and status/fingerprint/page models.
- `src/retrieval/repository.py` — Implemented SQLite repository methods for run metadata, page rows, corpus fingerprints, transactional writes, and optional FTS handling.
- `src/retrieval/indexer.py` — Implemented provider-free deterministic index build/status service over ingested SQLite documents/pages.
- `src/retrieval/cli.py` — Added Typer build/status commands with safe reason-coded output and DB preflight.
- `src/retrieval/__main__.py` — Enabled module execution through python -m src.retrieval.
- `tests/test_retrieval_index_repository.py` — Added repository/schema tests for persistence, idempotence, safety, and FTS behavior.
- `tests/test_retrieval_indexer.py` — Added deterministic indexer tests for built, empty, missing, stale, rollback, ordering, and safe diagnostics.
- `tests/test_retrieval_cli.py` — Added CLI tests for build/status, missing/empty/stale states, missing schema, and sanitized output.
