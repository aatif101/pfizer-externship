---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T02: Build deterministic indexer over ingested SQLite pages

Expected executor skills: tdd, verify-before-complete, observability. Why: The slice demo requires transforming the existing documents/pages corpus into persisted retrieval state and detecting empty or stale source data before retrieval scoring exists. Do: implement src/retrieval/indexer.py as a provider-free service that reads only documents and pages from SQLite, filters to ingested documents with nonblank page_text, computes a deterministic corpus fingerprint from stable document/page identifiers, filenames, page counts, status, page numbers, and text content, normalizes text for indexing/snippet generation, and writes a new retrieval_index_runs row plus page index rows transactionally. Add status helpers that report missing when no index run exists, built when latest fingerprint matches current corpus, empty when there are no indexable pages, and stale when current fingerprint differs from the latest successful build. Ensure image blobs and provider code are never loaded, page snippets are short verbatim prefixes/safe whitespace-normalized slices, and failures roll back partial page index writes. Add tests for built metadata, empty corpus, blank-page exclusion, stale detection after page text changes, missing status before build, deterministic run ordering, no raw text in diagnostics, and no ingestion/extraction regression. Done when indexer tests prove all S01 runtime states without live secrets.

## Inputs

- `src/db/queries.py`
- `src/db/schema.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `tests/conftest.py`
- `tests/test_extraction_cli.py`

## Expected Output

- `src/retrieval/indexer.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `tests/test_retrieval_indexer.py`

## Verification

./venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py

## Observability Impact

Adds deterministic run metadata and stale/empty/missing status calculations so operators and later Streamlit UI can localize whether failures are source-corpus, stale-index, or build-write problems.
