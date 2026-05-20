---
estimated_steps: 7
estimated_files: 2
skills_used: []
---

# T03: Persist and retrieve sample extraction records idempotently

Expected executor skills: tdd, verify-before-complete.

Why: The typed contract is only useful if sample records can round-trip through SQLite using the existing Phase 1 document IDs and page numbering conventions, without requiring Langfuse or real VLM calls.

Do: Add `src/extraction/repository.py` with helpers such as `upsert_extraction_field`, `upsert_extraction_record`, `get_extraction_record`, and `list_compliance_records`. Use only parameterized SQL placeholders. For each `SDFExtractionRecord`, upsert six field-level rows into `extractions` including confidence, 0-indexed source page, bbox JSON, verbatim span, trace_id, normalized value, review state, needs_review, and abstention reason; then upsert one dashboard-ready row into `compliance_records` with document-level values and nullable risk placeholders. Add `tests/test_extraction_persistence.py` using deterministic hand-authored records, `init_db()`, and `insert_document()` from existing query helpers. Cover FK failure for unknown docs, idempotent updates without duplicate rows, SQL-metacharacter round-trips, abstention round-trips, aggregate confidence/review state, and list ordering/shape for S04.

Done when: targeted extraction tests and the full suite pass under the Python 3.11 project venv.

Failure Modes (Q5): missing parent document must raise SQLite FK/integrity failure; malformed model data should be rejected before repository calls; absent Langfuse credentials must be irrelevant because repository only stores optional trace metadata.
Load Profile (Q6): per record persistence is six field upserts plus one compliance row upsert using short-lived SQLite connections; acceptable for demo, but duplicate rows must be prevented by unique keys.
Negative Tests (Q7): malicious vendor/field strings containing quotes and SQL comment markers must round-trip safely; an update of the same doc/field must replace values rather than insert duplicates; abstained expiry date must persist with null value and reason.

## Inputs

- `src/extraction/models.py`
- `src/db/schema.py`
- `src/db/queries.py`
- `tests/conftest.py`

## Expected Output

- `src/extraction/repository.py`
- `tests/test_extraction_persistence.py`

## Verification

./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_schema.py tests/test_extraction_persistence.py -q
./venv/Scripts/python.exe -m pytest -q

## Observability Impact

Persists trace_id, review_state, needs_review, abstention_reason, normalized values, and compliance summary rows so later S03/S04 agents can inspect extraction state directly from SQLite.
