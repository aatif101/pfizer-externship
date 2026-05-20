# S01: Persisted Retrieval Index Setup

**Goal:** Create a repeatable, offline-safe retrieval indexing path that reads ingested SQLite documents/pages, persists inspectable page-level text index state and metadata in the same database, and reports built, empty, missing, and stale corpus/index states without requiring provider secrets.
**Demo:** After this, a developer can run a repeatable index command against a fixture or local database and see persisted index metadata plus clear output for built, empty, missing, and stale states.

## Must-Haves

- Owned requirements: R005 for grounded Q&A preparation, supporting R008 for diagnosable retrieval operations, and R009/R010 for Python 3.11 and secret-safe execution. Demo closure: a developer can initialize a fixture database, build the retrieval index through a command, inspect persisted metadata/page-index rows, see a successful built summary with doc/page counts and content hash, get a clear empty-corpus message for a DB with no indexable pages, get a clear missing-index status before build, and detect stale status after corpus pages change. Q3 Threat Surface: untrusted persisted page text and filenames flow through normalization, hashing, SQLite writes, and CLI output; use parameterized SQL and do not echo raw page text or secrets. Q4 Requirement Impact: reverify existing ingestion/extraction schema tests because schema.py changes; no changes to M001 ingestion/extraction contracts should be required. Q5 Failure Modes: missing DB/table, empty corpus, unavailable FTS5, and write failures must become typed/safe diagnostics. Q6 Load Profile: page text indexing is O(total page text bytes); acceptable for fixture/demo corpora, but batch writes and no image loading are required to avoid 10x corpus memory pressure. Q7 Negative Tests: missing index, empty corpus, blank pages, stale corpus fingerprint, and malicious SQL-like filename/page text must be covered.

## Proof Level

- This slice proves: Integration proof over real SQLite fixture state with deterministic pytest and Typer CLI tests; no live LLM, Langfuse, GPU, Qdrant, or network required.

## Integration Closure

Consumes existing src/db/schema.py, src/db/queries.py, and ingestion page-number contract where pages.page_num is 0-indexed. Introduces src/retrieval as the M002 service boundary plus python -m src.retrieval.cli commands. Leaves scoring/ranking, evidence thresholds, generation, and Streamlit chat rendering for S02-S04.

## Verification

- Persisted retrieval_index_runs metadata exposes status, run_id, built_at, source doc/page counts, content hash, stale comparison data, and safe error reason. CLI output is the primary inspection surface for S01 and must exclude raw page text, provider responses, API keys, and image blobs.

## Tasks

- [x] **T01: Add retrieval index schema and repository contract** `est:2h`
  Expected executor skills: tdd, verify-before-complete. Why: S01 needs a durable, inspectable persistence boundary before any builder or CLI can be trusted, and schema changes must not regress M001 ingestion/extraction tables. Do: extend src/db/schema.py with idempotent retrieval index tables and indexes, including retrieval_index_runs metadata and page-level retrieval_index_pages rows keyed by stable doc_id/page_num; add an FTS5 virtual table for indexed page text when supported and keep the repository API responsible for hiding FTS implementation details. Create src/retrieval package models/repository with typed DTOs for index runs, page records, corpus fingerprint, and status values. Use only parameterized SQL for data values, preserve existing pages.page_num as 0-indexed internally, and expose 1-indexed display_page_num in DTOs for later citations. Add repository tests that create a temporary DB through init_db, assert tables exist, upsert/list page index records, store/load latest metadata, survive repeated init_db calls, and reject/correct SQL metacharacters in filenames/page text without leaking or executing them. Done when the repository test suite and existing DB schema tests pass on the project Python 3.11 venv.
  - Files: `src/db/schema.py`, `src/retrieval/__init__.py`, `src/retrieval/models.py`, `src/retrieval/repository.py`, `tests/test_retrieval_index_repository.py`, `tests/test_db.py`
  - Verify: ./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_retrieval_index_repository.py

- [x] **T02: Build deterministic indexer over ingested SQLite pages** `est:2.5h`
  Expected executor skills: tdd, verify-before-complete, observability. Why: The slice demo requires transforming the existing documents/pages corpus into persisted retrieval state and detecting empty or stale source data before retrieval scoring exists. Do: implement src/retrieval/indexer.py as a provider-free service that reads only documents and pages from SQLite, filters to ingested documents with nonblank page_text, computes a deterministic corpus fingerprint from stable document/page identifiers, filenames, page counts, status, page numbers, and text content, normalizes text for indexing/snippet generation, and writes a new retrieval_index_runs row plus page index rows transactionally. Add status helpers that report missing when no index run exists, built when latest fingerprint matches current corpus, empty when there are no indexable pages, and stale when current fingerprint differs from the latest successful build. Ensure image blobs and provider code are never loaded, page snippets are short verbatim prefixes/safe whitespace-normalized slices, and failures roll back partial page index writes. Add tests for built metadata, empty corpus, blank-page exclusion, stale detection after page text changes, missing status before build, deterministic run ordering, no raw text in diagnostics, and no ingestion/extraction regression. Done when indexer tests prove all S01 runtime states without live secrets.
  - Files: `src/retrieval/indexer.py`, `src/retrieval/models.py`, `src/retrieval/repository.py`, `tests/test_retrieval_indexer.py`
  - Verify: ./venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py

- [x] **T03: Expose retrieval index build and status CLI** `est:2h`
  Expected executor skills: tdd, verify-before-complete, observability. Why: S01 is not complete until developers can exercise the indexing path through a repeatable command and see clear operator output for built, empty, missing, and stale states. Do: add a Typer CLI in src/retrieval/cli.py plus src/retrieval/__main__.py so commands can run as python -m src.retrieval. Provide at least build and status commands with --db-path, safe nonzero exits for missing/empty/unreadable DB states, and concise output including status, run_id when present, indexed_docs, indexed_pages, content_hash prefix, stale true/false, and reason codes without raw page text. Tests should use CliRunner and temporary DBs to cover successful build, status before build as missing, empty corpus build/status, stale status after mutating a page, missing database/table messaging, and SQL-like filename/page text not appearing unsanitized in output. Done when CLI tests and the combined retrieval slice test set pass.
  - Files: `src/retrieval/cli.py`, `src/retrieval/__main__.py`, `src/retrieval/indexer.py`, `tests/test_retrieval_cli.py`
  - Verify: ./venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py

- [x] **T04: Run slice integration regression and document executor evidence** `est:1h`
  Expected executor skills: verify-before-complete. Why: This slice modifies shared SQLite schema and adds a new runtime boundary, so completion needs proof that the new retrieval path works and existing M001 ingestion/extraction/dashboard tests still import against the migrated schema. Do: run the focused retrieval tests plus representative existing DB, extraction CLI, dashboard, and app smoke tests through ./venv/Scripts/python.exe. If regressions appear, fix only issues caused by S01 changes and keep scope limited to index persistence/CLI; do not implement ranking, answer generation, Streamlit Chat, Qdrant, or live provider calls. Done when the verification command passes and the task summary records the exact command, exit code, and notable safe-output evidence for built/empty/missing/stale states.
  - Files: `src/db/schema.py`, `src/retrieval/__init__.py`, `src/retrieval/models.py`, `src/retrieval/repository.py`, `src/retrieval/indexer.py`, `src/retrieval/cli.py`, `src/retrieval/__main__.py`, `tests/test_retrieval_index_repository.py`, `tests/test_retrieval_indexer.py`, `tests/test_retrieval_cli.py`
  - Verify: ./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_cli.py tests/test_compliance_dashboard.py tests/test_app.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py

## Files Likely Touched

- src/db/schema.py
- src/retrieval/__init__.py
- src/retrieval/models.py
- src/retrieval/repository.py
- tests/test_retrieval_index_repository.py
- tests/test_db.py
- src/retrieval/indexer.py
- tests/test_retrieval_indexer.py
- src/retrieval/cli.py
- src/retrieval/__main__.py
- tests/test_retrieval_cli.py
