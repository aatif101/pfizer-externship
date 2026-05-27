---
id: T03
parent: S07
milestone: M003
key_files:
  - src/extraction/pipeline.py
  - tests/test_extraction_pipeline.py
key_decisions:
  - Extraction trace updates use src.tracing.safe_update_current_trace with an extraction-specific allowlist and never include provider messages, payloads, field values, page text, file paths, prompts, raw responses, or secrets.
duration: 
verification_result: passed
completed_at: 2026-05-27T21:06:08.480Z
blocker_discovered: false
---

# T03: Added safe Langfuse extraction tracing around extract_document with sanitized success and failure diagnostics.

**Added safe Langfuse extraction tracing around extract_document with sanitized success and failure diagnostics.**

## What Happened

Wrapped src.extraction.pipeline.extract_document in a Langfuse-compatible observe boundary and routed trace metadata through the shared safe_update_current_trace helper with an extraction-specific allowlist. Success traces now emit only document/run-level diagnostics: boundary, status, run_id, doc_id, trace_id, provider_name, page_count, review_state, and needs_review. Failure traces emit status=error with run_id/doc_id when safely representable, error_class, and reason_code only for typed ExtractionPipelineError subclasses, while preserving the original return/raise behavior. Added extraction pipeline tests for success trace metadata, missing document, no pages, no text, provider exceptions with secret-looking messages, malformed provider results, and failing trace contexts.

## Verification

Ran the required Windows-native pytest command via gsd_exec using node to spawn venv\Scripts\python.exe. Final verification passed: 28 tests passed across tests/test_tracing.py and tests/test_extraction_pipeline.py. During implementation, two over-strict test fixture/assertion issues were corrected before the final passing run: allowing the legitimate no_page_text reason code and using a non-secret-like run_id when asserting sanitizer-preserved run IDs.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_extraction_pipeline.py` | 0 | ✅ pass (28 passed) | 8743ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/pipeline.py`
- `tests/test_extraction_pipeline.py`
