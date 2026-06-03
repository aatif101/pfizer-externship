---
estimated_steps: 5
estimated_files: 2
skills_used: []
---

# T02: Persist and query extraction run history

Expected executor skills for task plan frontmatter: tdd, verify-before-complete.

Why: The slice demo is not true until the repository can write latest compatibility rows and run-scoped historical rows in one transaction, then reconstruct both latest and selected-run records independently.

Do: In `src/extraction/repository.py`, add an `ExtractionRunSummary` dataclass and repository helpers: `get_extraction_record_for_run(db_path, run_id, doc_id)`, `list_compliance_records_for_run(db_path, run_id)`, and `list_extraction_run_summaries(db_path)`. Keep `upsert_extraction_field()`, `get_extraction_record()`, and `list_compliance_records()` behavior compatible. Update `upsert_extraction_record()` so, when `record.run_id` is present, it first upserts `extraction_runs`, then upserts six `extraction_history` rows keyed by `(run_id, doc_id, field_name)`, then upserts one `compliance_record_history` row keyed by `(run_id, doc_id)`, all in the same transaction as the existing latest rows. Treat `record.run_id is None` as latest-only compatibility and skip history. Reuse existing placeholder-based SQL, `_field_from_row()`, `_json_or_none()`, `_scalar_to_db()`, `_preferred_document_evidence()`, and parsing helpers where practical. Consider extracting an internal record reconstruction helper so latest and run-scoped reads cannot diverge.

Add tests to `tests/test_extraction_persistence.py` proving: two different run IDs for the same doc are both queryable with different vendor/date/trace values; latest-write tables show only the newest values and still contain six extraction rows plus one compliance row; history has twelve field rows plus two compliance rows; re-running the same run/doc is idempotent rather than duplicating history; `list_compliance_records_for_run()` returns the same dashboard row shape as latest rows but filtered by run; `list_extraction_run_summaries()` reports bounded metadata and counts; `record.run_id=None` writes only latest rows; hostile SQL metacharacter field values persist safely in history.

Done when: The repository is the single SQLite boundary for run-scoped history and the focused tests prove independent historical reads plus latest compatibility.

## Inputs

- `src/extraction/repository.py`
- `src/extraction/models.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_persistence.py`
- `tests/test_extraction_pipeline.py`
- `src/db/schema.py`
- `tests/test_extraction_run_history_schema.py`

## Expected Output

- `src/extraction/repository.py`
- `tests/test_extraction_persistence.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_persistence.py tests/test_extraction_pipeline.py

## Observability Impact

Adds run-summary and run-filtered inspection APIs that future dashboard and evaluation code can call without provider imports. Failure modes to cover: missing parent documents raise FK errors, incomplete six-field history returns `None`, and `None` run IDs do not create ambiguous fake history.
