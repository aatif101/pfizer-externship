---
estimated_steps: 23
estimated_files: 5
skills_used: []
---

# T02: Load ingested pages and prove fake-provider pipeline persistence

---
estimated_steps: 8
estimated_files: 5
skills_used:
  - tdd
  - observability
  - verify-before-complete
---

Why: The critical S03 integration risk is converting provider output into the exact six-field model, validating source grounding, computing risk, and persisting a dashboard-ready row. Prove that path first with a fake provider and temp SQLite DB.

Do:
1. Add typed page/document read helpers in `src/db/queries.py` or a new extraction loader module. Fetch document metadata plus ordered pages by `doc_id`, including `page_num`, `page_text`, and optionally image bytes, with 0-indexed page numbers preserved.
2. Add `src/extraction/providers.py` with a small provider protocol/data shape that the pipeline can call; include no live Gemini dependency in this task.
3. Add `src/extraction/pipeline.py` orchestration for `extract_document(db_path, doc_id, provider, settings/date overrides...)`.
4. Normalize provider field payloads into all six `ExtractedField` instances, synthesizing abstentions for missing fields before constructing `SDFExtractionRecord`.
5. Validate non-abstained source spans against cited page text using whitespace/case-tolerant matching. Missing spans should not persist as confident facts; downgrade to needs-review or abstain with a non-secret reason.
6. Apply low-confidence review policy using a named threshold parameter, compute risk via `src/extraction/risk.py`, assign a generated `run_id`, preserve optional `trace_id`, and upsert through `upsert_extraction_record()`.
7. Add `tests/test_extraction_pipeline.py` happy-path integration: initialize temp DB, insert one document and realistic SDF-style page text, fake provider returns all six fields with spans, run pipeline, assert six field rows and one compliance row with risk metadata/source evidence/run metadata.

Threat Surface (Q3): Provider payload and page text are untrusted. SQL remains parameterized. Do not log full page text, raw provider payloads, image blobs, or secrets.
Requirement Impact (Q4): Advances R002, R003, R004, and R008. Re-verify ingestion assumptions around `documents`/`pages` and extraction persistence.
Failure Modes (Q5): Missing document/pages returns typed extraction failure, not crash. Missing fields become abstentions. Span mismatch becomes needs-review/abstention. DB failures rollback via repository.
Load Profile (Q6): One provider call per document plus one DB read and seven DB upsert statements. At 10x document load, provider rate limits and SQLite write serialization are first constraints; keep all-doc extraction sequential for now.
Negative Tests (Q7): Empty page list, empty page text, missing required field, span mismatch, low confidence threshold boundary, and invalid page number.

Done when the offline fake-provider pipeline test proves the full read -> normalize -> ground -> risk -> persist loop.

## Inputs

- `src/db/queries.py`
- `src/extraction/models.py`
- `src/extraction/repository.py`
- `src/extraction/risk.py`
- `tests/test_extraction_risk.py`

## Expected Output

- `src/db/queries.py`
- `src/extraction/providers.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_pipeline.py`
- `src/extraction/__init__.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_extraction_risk.py tests/test_extraction_pipeline.py -q

## Observability Impact

Introduces run-level extraction diagnostics through generated `run_id`, typed failure states/exceptions, and persisted review/abstention outcomes while maintaining no-page-text logging.
