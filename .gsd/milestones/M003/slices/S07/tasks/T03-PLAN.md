---
estimated_steps: 7
estimated_files: 3
skills_used: []
---

# T03: Trace extraction pipeline diagnostics safely

Expected executor skills: observability, tdd, verify-before-complete.

Why: Extraction is a required R008 phase and src/extraction/pipeline.py already returns safe ExtractionDiagnostics, but the core extract_document boundary has no Langfuse span or metadata update.

Do: Add a Langfuse v3-compatible observe span around extract_document, using the shared no-op-safe helper from T01 for metadata updates. On success, emit only boundary=extraction, status, run_id, doc_id, trace_id, provider_name, page_count, review_state, and needs_review. On DocumentNotFoundError, NoPagesError, NoPageTextError, provider failures, validation failures, or persistence failures, emit only boundary, status=error, run_id/doc_id if safely available, reason_code for known ExtractionPipelineError subclasses, and error_class. Do not include exception message, provider payload, field values, normalized values, verbatim spans, page text, prompts, raw responses, file paths, or secrets. Update tests using the existing fake extraction provider and tmp SQLite fixtures so success metadata is recorded, failure metadata is sanitized, and a raising fake trace context still returns or raises exactly as the extraction pipeline did before.

Failure Modes (Q5): Provider errors or malformed provider payloads can contain secrets or raw responses; trace error metadata must use class and reason code only. Langfuse update failures must not mask extraction validation/persistence outcomes.

Load Profile (Q6): Extraction can process multi-page documents and six fields per document; trace metadata must remain document/run-level and never grow with field count, page text length, or image size.

Negative Tests (Q7): Missing document, no pages or no text, provider exception with secret-looking message, and failing Langfuse context.

Done when: extraction has a tested trace boundary and all prior extraction behavior remains unchanged.

## Inputs

- `src/tracing.py`
- `tests/test_tracing.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_pipeline.py`

## Expected Output

- `src/extraction/pipeline.py`
- `tests/test_tracing.py`
- `tests/test_extraction_pipeline.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_extraction_pipeline.py

## Observability Impact

Adds the missing extraction phase to R008 with safe provider/run diagnostics and explicit failure-path metadata.
