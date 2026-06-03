---
estimated_steps: 4
estimated_files: 2
skills_used: []
---

# T01: Add additive run history schema

Expected executor skills for task plan frontmatter: tdd, verify-before-complete.

Why: R011 depends on durable run-scoped storage, but D021 requires preserving the validated latest-write `extractions` and `compliance_records` tables instead of rewriting their keys.

Do: In `src/db/schema.py`, add `CREATE TABLE IF NOT EXISTS` definitions for `extraction_runs`, `extraction_history`, and `compliance_record_history`. Keep existing `extractions` and `compliance_records` definitions unchanged. Add indexes for run ordering and run/doc lookup. Use foreign keys from history rows to `documents` and `extraction_runs`, with cascade delete. Keep columns bounded to extraction/compliance metadata already persisted today: run id, doc id, field names, values, normalized values, review state, trace id, source page/bbox/verbatim span, compliance risk fields, timestamps, status, document count, and field count. Do not add prompt, page_text, image_blob, provider payload, file contents, PDF, secret, or local artifact path columns. Add schema tests in `tests/test_extraction_run_history_schema.py` that initialize a fresh DB, assert the three tables and key indexes exist, assert history tables can be initialized idempotently, assert no forbidden raw-content columns exist, and assert FK enforcement rejects history for a missing parent run/doc.

Done when: Fresh DB initialization creates the additive history surface, repeated initialization is safe, latest-write schema remains compatible, and the schema tests prove the confidentiality boundary.

## Inputs

- `src/db/schema.py`
- `tests/test_db.py`
- `.gsd/REQUIREMENTS.md`
- `.gsd/DECISIONS.md`

## Expected Output

- `src/db/schema.py`
- `tests/test_extraction_run_history_schema.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_run_history_schema.py tests/test_db.py

## Observability Impact

Introduces inspectable SQLite run-history tables and indexes. Negative tests should prove malformed/missing parent identities fail through FK enforcement rather than creating orphaned history.
