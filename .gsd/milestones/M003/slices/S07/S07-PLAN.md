# S07: Implement R008 Langfuse tracing

**Goal:** Implement R008 Langfuse tracing across ingestion, extraction, retrieval, generation, and evaluation with no-op behavior when Langfuse is unavailable and strict allowlisted metadata that cannot leak secrets, page text, snippets, provider payloads, images, Docling JSON, or full content hashes.
**Demo:** After this: Langfuse tracing spans cover ingestion, extraction, retrieval, generation, and evaluation without leaking secrets, and tests or fixture traces prove evaluation can surface latency and cost summaries.

## Must-Haves

- Threat Surface (Q3): Trace updates are a data-exposure surface because document names, provider diagnostics, questions, page text, snippets, image bytes, Docling JSON, prompt payloads, API keys, and exception messages can accidentally cross into Langfuse. All new trace metadata must be allowlisted, compact, bounded, and free of raw content or secrets. Langfuse import/auth/backend failures must never change ingestion, extraction, retrieval, RAG, or evaluation behavior.
- Requirement Impact (Q4): Owns R008 and supports R007. Re-verify existing retrieval/RAG trace tests, extraction pipeline behavior, ingestion behavior, retrieval eval persistence, and optional latency/cost metric aggregation. Decision D018 governs the shared helper approach. Dashboard provider-free/no-secrets behavior must remain unchanged; no dashboard tracing work is in scope.
- Verification: Focused Windows-safe command must pass: venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py tests/test_extraction_pipeline.py tests/test_ingest.py. The tests must cover success metadata, Langfuse unavailable, Langfuse update failures, and forbidden-key/value absence for ingestion/storage, extraction, existing retrieval/RAG, and evaluation tracing.
- Negative Tests (Q7): Exercise missing Langfuse context, raising trace backend, extraction provider or document failures, empty retrieval eval state, and optional metrics absent. Assert trace metadata excludes question, prompt, answer_text, context, snippet, page_text, field_value, expected_value, verbatim_span, provider_payload, raw_response, api_key, secret, image_blob, docling_json, content_hash, file_path, and raw exception messages.

## Proof Level

- This slice proves: contract plus integration: unit and integration tests exercise real pipeline boundaries with fake Langfuse contexts and SQLite-backed fixtures; no live Langfuse runtime or human UAT required in this slice.

## Integration Closure

Upstream surfaces consumed: src/tracing.py, ingestion pipeline, extraction pipeline diagnostics, retrieval/RAG trace tests, retrieval eval runner, and S06 rag_eval_observations optional metrics. New wiring: shared safe trace update helper used by ingestion/storage, extraction, and evaluation boundaries; existing retrieval/generation coverage remains verified. Remaining milestone work: S08 records dashboard UAT evidence after R007 and R008 are complete.

## Verification

- Adds consistent bounded Langfuse observation metadata for ingestion, storage, extraction, and evaluation while preserving existing retrieval and generation trace coverage. Future agents can inspect Langfuse spans by boundary/status/run_id/doc_id/eval_type/retrieval_run_id/count fields, and can rely on tests proving no raw content or secrets are emitted.

## Tasks

- [x] **T01: Add shared safe trace helper** `est:1h`
  Expected executor skills: observability, tdd, verify-before-complete.
  - Files: `src/tracing.py`, `tests/test_tracing.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_tracing.py

- [x] **T02: Harden ingestion and storage trace updates** `est:1h`
  Expected executor skills: observability, tdd, verify-before-complete.
  - Files: `src/pipeline/ingest.py`, `src/pipeline/db_writer.py`, `tests/test_tracing.py`, `tests/test_ingest.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_ingest.py

- [x] **T03: Trace extraction pipeline diagnostics safely** `est:1h 15m`
  Expected executor skills: observability, tdd, verify-before-complete.
  - Files: `src/extraction/pipeline.py`, `tests/test_tracing.py`, `tests/test_extraction_pipeline.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_extraction_pipeline.py

- [x] **T04: Trace retrieval evaluation runs safely** `est:1h 15m`
  Expected executor skills: observability, tdd, verify-before-complete.
  - Files: `src/eval/retrieval_eval_runner.py`, `tests/test_tracing.py`, `tests/test_retrieval_eval_runner.py`, `tests/test_retrieval_eval_optional_metrics.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py

- [x] **T05: Run focused cross-pipeline tracing verification** `est:30m`
  Expected executor skills: verify-before-complete, observability.
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py tests/test_extraction_pipeline.py tests/test_ingest.py

## Files Likely Touched

- src/tracing.py
- tests/test_tracing.py
- src/pipeline/ingest.py
- src/pipeline/db_writer.py
- tests/test_ingest.py
- src/extraction/pipeline.py
- tests/test_extraction_pipeline.py
- src/eval/retrieval_eval_runner.py
- tests/test_retrieval_eval_runner.py
- tests/test_retrieval_eval_optional_metrics.py
