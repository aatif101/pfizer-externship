# S02: Extraction contract and persistence

**Goal:** Establish the Phase 2 extraction contract and SQLite persistence foundation: typed SDF extraction records validate required fields, evidence, confidence, review/abstention state, and deterministic sample records round-trip through field-level and dashboard-ready document-level tables.
**Demo:** A typed extraction schema can represent required SDF fields, source evidence, confidence, and review state for sample records.

## Must-Haves

- Owned requirement: R002. Supporting/preparatory requirements: R003, R004, R008. Demo outcome: with no VLM or Langfuse credentials, tests can construct a sample SDFExtractionRecord containing the six required fields, include source page/span evidence and an abstention, persist it for an existing document, fetch it back, and list a dashboard-ready compliance record row. Verification commands: `./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_schema.py tests/test_extraction_persistence.py -q` and `./venv/Scripts/python.exe -m pytest -q`. Threat Surface (Q3): untrusted extracted text and vendor strings will be written to SQLite, so all persistence must use parameterized queries and tests must cover SQL metacharacter round-trips; no auth or network/API calls are introduced. Requirement Impact (Q4): R002 is directly advanced; R003/R004 are prepared via nullable risk/dashboard columns; R009/D001 remain binding through Python 3.11 venv commands; D002 remains binding by not reading ignored local provider settings. Failure Modes (Q5): malformed extraction records must fail Pydantic validation before persistence; nonexistent doc_id must fail FK checks; absent Langfuse credentials must not affect persistence. Load Profile (Q6): per document, six field upserts plus one compliance record upsert; SQLite is adequate for demo corpus, but use idempotent upserts and indexed doc_id paths. Negative Tests (Q7): unknown fields, invalid confidence, negative page numbers, missing value without abstention, malformed bbox, FK violations, and malicious SQL-like values.

## Proof Level

- This slice proves: Contract plus persistence integration proof. Real runtime required: yes, via Python 3.11 pytest against temporary SQLite databases. Human/UAT required: no.

## Integration Closure

Upstream consumed: Phase 1 `documents` and `pages` persistence conventions, especially existing `doc_id` and 0-indexed `pages.page_num`. New wiring introduced: `src/extraction` typed models and repository helpers, schema evolution for `extractions`, and a new `compliance_records` document-level table. Remaining before end-to-end milestone usability: S03 must wire real extractor calls into these models/repository, and S04 must render `compliance_records` in Streamlit with risk coloring/source links.

## Verification

- Extraction persistence will carry `trace_id`, field-level `review_state`, `needs_review`, `abstention_reason`, normalized values, and document-level aggregate/review/risk placeholders. Future agents can inspect SQLite tables (`extractions`, `compliance_records`) and repository test failures without requiring Langfuse credentials. Redaction boundary: do not log verbatim page text or secret-bearing settings; verbatim spans are persisted only as explicit evidence fields.

## Tasks

- [x] **T01: Define typed extraction contract and validation tests** `est:1h`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/extraction/__init__.py`, `src/extraction/models.py`, `tests/test_extraction_models.py`
  - Verify: ./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py -q

- [x] **T02: Evolve SQLite schema for review state and compliance records** `est:1h`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/db/schema.py`, `tests/test_db.py`, `tests/test_extraction_schema.py`
  - Verify: ./venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_schema.py -q

- [x] **T03: Persist and retrieve sample extraction records idempotently** `est:1.5h`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/extraction/repository.py`, `tests/test_extraction_persistence.py`
  - Verify: ./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_schema.py tests/test_extraction_persistence.py -q
./venv/Scripts/python.exe -m pytest -q

## Files Likely Touched

- src/extraction/__init__.py
- src/extraction/models.py
- tests/test_extraction_models.py
- src/db/schema.py
- tests/test_db.py
- tests/test_extraction_schema.py
- src/extraction/repository.py
- tests/test_extraction_persistence.py
