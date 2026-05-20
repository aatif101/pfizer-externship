---
estimated_steps: 7
estimated_files: 3
skills_used: []
---

# T01: Add compliance dashboard data adapter and tests

Expected executor skills/frontmatter: estimated_steps: 8; estimated_files: 3; skills_used: [tdd, verify-before-complete].

Why: S04 needs a stable, testable seam between SQLite persistence and Streamlit so the UI can remain read-only, credential-free, and robust when no extraction has run yet.

Do: Create `src/dashboard/__init__.py` and `src/dashboard/compliance.py`. In the module, add `load_compliance_rows(db_path: str) -> list[dict]` wrapping `src.extraction.repository.list_compliance_records` and returning an empty list for missing database/table `sqlite3.OperationalError` cases. Add `format_compliance_rows(rows)` that preserves raw row keys while adding display-safe fields such as `source_page_display` (DB `source_page` + 1 when not null), `source_page_label`, `needs_review_display`, `aggregate_confidence_display`, and risk/review labels suitable for Streamlit. Keep DB semantics unchanged and do not call Gemini/Langfuse/provider code.

Add `tests/test_compliance_dashboard.py` with real SQLite fixture coverage using `init_db`, `insert_document`, and `upsert_extraction_record` patterns from `tests/test_extraction_persistence.py`. Tests must assert that formatted rows expose vendor, doc_type, manufacturing/effective/revision/expiry dates, risk_level, risk_reason, compliance_status, age_days, confidence, review_state, run_id, trace_id, source_verbatim_span, and 1-indexed `source_page_display` for a persisted 0-indexed source page.

Failure Modes (Q5): Missing DB/table returns an empty list; nullable evidence fields produce blank/unknown display labels instead of exceptions.

Negative Tests (Q7): Include empty/missing database behavior, null source evidence, and off-by-one source page display.

Done when: targeted dashboard tests pass without network, credentials, or Streamlit process startup.

## Inputs

- `src/extraction/repository.py`
- `src/db/schema.py`
- `src/db/queries.py`
- `src/extraction/models.py`
- `tests/test_extraction_persistence.py`

## Expected Output

- `src/dashboard/__init__.py`
- `src/dashboard/compliance.py`
- `tests/test_compliance_dashboard.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py -q

## Observability Impact

Creates the dashboard inspection seam: future agents can call adapter tests or inspect formatted rows to diagnose whether failures are persistence, formatting, or rendering issues. Empty/missing DB state becomes deterministic instead of a traceback.
