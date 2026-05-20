---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T03: Expose retrieval index build and status CLI

Expected executor skills: tdd, verify-before-complete, observability. Why: S01 is not complete until developers can exercise the indexing path through a repeatable command and see clear operator output for built, empty, missing, and stale states. Do: add a Typer CLI in src/retrieval/cli.py plus src/retrieval/__main__.py so commands can run as python -m src.retrieval. Provide at least build and status commands with --db-path, safe nonzero exits for missing/empty/unreadable DB states, and concise output including status, run_id when present, indexed_docs, indexed_pages, content_hash prefix, stale true/false, and reason codes without raw page text. Tests should use CliRunner and temporary DBs to cover successful build, status before build as missing, empty corpus build/status, stale status after mutating a page, missing database/table messaging, and SQL-like filename/page text not appearing unsanitized in output. Done when CLI tests and the combined retrieval slice test set pass.

## Inputs

- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/retrieval/indexer.py`
- `src/extraction/cli.py`
- `tests/test_extraction_cli.py`

## Expected Output

- `src/retrieval/cli.py`
- `src/retrieval/__main__.py`
- `src/retrieval/indexer.py`
- `tests/test_retrieval_cli.py`

## Verification

./venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py

## Observability Impact

Makes retrieval index health inspectable from a stable CLI surface with reason-coded safe messages suitable for future dashboard setup checks.
