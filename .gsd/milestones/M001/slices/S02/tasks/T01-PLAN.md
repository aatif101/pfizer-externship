---
estimated_steps: 7
estimated_files: 3
skills_used: []
---

# T01: Define typed extraction contract and validation tests

Expected executor skills: tdd, verify-before-complete.

Why: S03 needs a strict contract before any VLM wiring, and R002 requires six structured SDF fields with confidence and source evidence rather than ad-hoc dictionaries.

Do: Create `src/extraction/` with Pydantic v2 models: `SDFFieldName` enum for `doc_type`, `vendor_name`, `manufacturing_date`, `effective_date`, `revision_date`, `expiry_date`; `ReviewState` enum for `pending`, `needs_review`, `reviewed`, `abstained`; `SourceEvidence` with non-negative 0-indexed `page_num`, optional JSON-serializable bbox, and optional/required `verbatim_span` based on field state; `ExtractedField` with raw value, optional normalized value/date, confidence constrained to 0..1, evidence, review state, `needs_review` convenience behavior, optional abstention reason, and validators that reject a missing value unless the field is abstained with a reason; and `SDFExtractionRecord` for one document containing exactly the six required fields, aggregate confidence/review state, optional trace/run metadata, and dashboard-friendly accessors.

Done when: model tests prove acceptance of a full six-field sample record and an abstained field, and rejection of unknown field names, invalid confidence, negative source pages, malformed bbox, and missing value without abstention.

Failure Modes (Q5): malformed LLM output later should fail validation before DB writes; no external dependencies or timeouts in this task.
Load Profile (Q6): model construction is per document/field and trivial for demo-scale corpora.
Negative Tests (Q7): unknown field, confidence below 0 or above 1, negative `page_num`, non-list/non-dict bbox, absent field value without `ReviewState.ABSTAINED`, and abstention without reason.

## Inputs

- `pyproject.toml`

## Expected Output

- `src/extraction/__init__.py`
- `src/extraction/models.py`
- `tests/test_extraction_models.py`

## Verification

./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py -q

## Observability Impact

Adds explicit trace/run metadata and review-state fields to the in-memory contract so later pipeline failures can distinguish pending, needs-review, reviewed, and abstained values.
