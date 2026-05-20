---
estimated_steps: 1
estimated_files: 6
skills_used: []
---

# T01: Add retrieval index schema and repository contract

Expected executor skills: tdd, verify-before-complete. Why: S01 needs a durable, inspectable persistence boundary before any builder or CLI can be trusted, and schema changes must not regress M001 ingestion/extraction tables. Do: extend src/db/schema.py with idempotent retrieval index tables and indexes, including retrieval_index_runs metadata and page-level retrieval_index_pages rows keyed by stable doc_id/page_num; add an FTS5 virtual table for indexed page text when supported and keep the repository API responsible for hiding FTS implementation details. Create src/retrieval package models/repository with typed DTOs for index runs, page records, corpus fingerprint, and status values. Use only parameterized SQL for data values, preserve existing pages.page_num as 0-indexed internally, and expose 1-indexed display_page_num in DTOs for later citations. Add repository tests that create a temporary DB through init_db, assert tables exist, upsert/list page index records, store/load latest metadata, survive repeated init_db calls, and reject/correct SQL metacharacters in filenames/page text without leaking or executing them. Done when the repository test suite and existing DB schema tests pass on the project Python 3.11 venv.

## Inputs

- `src/db/schema.py`
- `src/db/queries.py`
- `tests/conftest.py`
- `tests/test_db.py`

## Expected Output

- `src/db/schema.py`
- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `tests/test_retrieval_index_repository.py`

## Verification

./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_retrieval_index_repository.py

## Observability Impact

Adds durable DB inspection surfaces for index runs and indexed page rows, including status and safe error fields that future agents can query without reading raw page text from logs.
