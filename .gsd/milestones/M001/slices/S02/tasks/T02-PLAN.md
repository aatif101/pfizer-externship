---
estimated_steps: 7
estimated_files: 3
skills_used: []
---

# T02: Evolve SQLite schema for review state and compliance records

Expected executor skills: tdd, verify-before-complete.

Why: `CREATE TABLE IF NOT EXISTS` will not evolve existing Phase 1 databases, and S04 needs a document-level row instead of pivoting field evidence rows on every dashboard render.

Do: Update `src/db/schema.py` with migration-safe helpers that inspect `PRAGMA table_info` and `ALTER TABLE` the existing `extractions` table to add nullable `review_state`, `abstention_reason`, `normalized_value`, and `updated_at` columns when missing. Add a new `compliance_records` table keyed by `doc_id` with document-level fields (`doc_type`, `vendor_name`, date columns, aggregate confidence, review state, trace_id/run metadata) and nullable future risk/dashboard fields (`risk_level`, `risk_reason`, `age_days`, source_page/source fields as needed). Add indexes for common dashboard/filter paths. Keep FK enforcement and cascade behavior. Extend schema tests or add `tests/test_extraction_schema.py` to prove fresh DB creation and Phase 1-shaped DB migration both produce the required columns/tables.

Done when: tests pass for both a fresh database and an artificially pre-existing Phase 1 database containing old `documents`, `pages`, and `extractions` shapes.

Failure Modes (Q5): existing local DBs may lack new columns; migration helper must be idempotent and safe to run repeatedly. SQLite DDL errors should surface as test failures rather than being swallowed.
Load Profile (Q6): migration runs at DB initialization; table-info checks are constant-size and acceptable. Runtime dashboard queries should have indexes on `doc_id` and risk/review fields.
Negative Tests (Q7): re-running `init_db()` must not duplicate columns; FK insert into `compliance_records` for nonexistent `doc_id` must fail; legacy DB initialization must preserve existing rows.

## Inputs

- `src/db/schema.py`
- `tests/test_db.py`
- `src/extraction/models.py`

## Expected Output

- `src/db/schema.py`
- `tests/test_db.py`
- `tests/test_extraction_schema.py`

## Verification

./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_schema.py -q

## Observability Impact

Adds persisted review/abstention and dashboard summary state that can be inspected directly in SQLite when extraction pipeline runs are incomplete or disputed.
