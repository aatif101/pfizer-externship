---
estimated_steps: 1
estimated_files: 10
skills_used: []
---

# T04: Run slice integration regression and document executor evidence

Expected executor skills: verify-before-complete. Why: This slice modifies shared SQLite schema and adds a new runtime boundary, so completion needs proof that the new retrieval path works and existing M001 ingestion/extraction/dashboard tests still import against the migrated schema. Do: run the focused retrieval tests plus representative existing DB, extraction CLI, dashboard, and app smoke tests through ./venv/Scripts/python.exe. If regressions appear, fix only issues caused by S01 changes and keep scope limited to index persistence/CLI; do not implement ranking, answer generation, Streamlit Chat, Qdrant, or live provider calls. Done when the verification command passes and the task summary records the exact command, exit code, and notable safe-output evidence for built/empty/missing/stale states.

## Inputs

- `src/db/schema.py`
- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/retrieval/indexer.py`
- `src/retrieval/cli.py`
- `src/retrieval/__main__.py`
- `tests/test_retrieval_index_repository.py`
- `tests/test_retrieval_indexer.py`
- `tests/test_retrieval_cli.py`
- `tests/test_db.py`
- `tests/test_extraction_cli.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_app.py`

## Expected Output

- `src/db/schema.py`
- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/retrieval/indexer.py`
- `src/retrieval/cli.py`
- `src/retrieval/__main__.py`
- `tests/test_retrieval_index_repository.py`
- `tests/test_retrieval_indexer.py`
- `tests/test_retrieval_cli.py`

## Verification

./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_cli.py tests/test_compliance_dashboard.py tests/test_app.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py

## Observability Impact

Confirms the new status/metadata diagnostics are executable and that shared SQLite migrations remain compatible with existing operator-facing surfaces.
