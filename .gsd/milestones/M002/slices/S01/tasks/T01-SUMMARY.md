---
id: T01
parent: S01
milestone: M002
key_files:
  - src/db/schema.py
  - src/retrieval/__init__.py
  - src/retrieval/models.py
  - src/retrieval/repository.py
  - tests/test_retrieval_index_repository.py
key_decisions:
  - Repository DTO outputs intentionally exclude raw page text; only the repository input boundary receives text for hashing and optional FTS5 synchronization.
  - FTS5 creation is optional and guarded during `init_db` so the retrieval schema remains usable on SQLite builds without FTS5.
duration: 
verification_result: passed
completed_at: 2026-05-20T20:48:01.865Z
blocker_discovered: false
---

# T01: Added an idempotent SQLite retrieval index schema plus a typed repository contract for run metadata, page index records, corpus fingerprints, and optional FTS5 synchronization.

**Added an idempotent SQLite retrieval index schema plus a typed repository contract for run metadata, page index records, corpus fingerprints, and optional FTS5 synchronization.**

## What Happened

Extended `src/db/schema.py` with `retrieval_index_runs` and `retrieval_index_pages` tables, retrieval indexes, and guarded optional FTS5 virtual table creation so initialization remains repeatable and offline-safe even on SQLite builds without FTS5. Created the `src/retrieval` package with typed DTOs for status values, corpus fingerprints, run metadata, raw page-index inputs, and safe page records. Implemented repository methods for computing corpus fingerprints, saving/loading latest run metadata, upserting/listing page index rows, checking FTS availability, and hiding raw indexed page text from DTO outputs while preserving 0-indexed `page_num` and exposing 1-indexed `display_page_num`. Added repository tests covering table creation, repeated `init_db`, run metadata round-trip, page upsert/list behavior, idempotent updates, corpus hashing, SQL metacharacter safety, and optional FTS query behavior.

## Verification

Ran the task-specified pytest target with the project venv: `./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_retrieval_index_repository.py`; all 10 tests passed. Also ran a small repository inspection diagnostic confirming changed file sizes and that the safe returned page column list does not include `page_text`.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_retrieval_index_repository.py` | 0 | ✅ pass | 3565ms |
| 2 | `./venv/Scripts/python.exe - <<'PY' ... changed file summary and safe-column inspection ... PY` | 0 | ✅ pass | 176ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/db/schema.py`
- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `tests/test_retrieval_index_repository.py`
