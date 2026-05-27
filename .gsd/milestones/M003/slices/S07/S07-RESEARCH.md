# S07 — Research: Implement R008 Langfuse tracing

## Summary

S07 should consolidate and harden Langfuse tracing across ingestion, extraction, retrieval, generation, and evaluation. The repo already has partial Langfuse hooks for ingestion, DB writes, retrieval indexing, retrieval evidence, and RAG answer generation. The largest gaps are extraction pipeline tracing and evaluation tracing, plus consistent sanitization/no-op behavior. Existing retrieval/RAG code has good allowlisted metadata helpers; ingestion/DB writer tracing is less defensive and can still call `langfuse_context.update_current_trace(...)` without a `try/except` safety boundary.

Key risk: R008 is explicitly about useful audit traces **without secret leakage**. The safest implementation path is to create one small shared trace helper with strict allowlists and no-op fallback, then migrate each pipeline boundary to it rather than duplicating ad hoc Langfuse calls.

## Requirements and constraints

- Owns/supports **R008**: trace ingestion, extraction, retrieval, generation, and evaluation with Langfuse while avoiding secret leakage.
- Supports **R007** because evaluation should surface latency/cost summaries from safe trace/observation metadata where available.
- Langfuse is optional. Missing install, missing keys, failed auth, or backend errors must never crash ingestion/extraction/retrieval/RAG/eval.
- Project dependency pins `langfuse>=3.0,<4.0`; `src/tracing.py` and `tests/test_tracing.py` enforce v3.
- Dashboard must remain provider-free/no-secrets; no dashboard tracing requirement except optional connection status in sidebar.
- Trace metadata must be compact and allowlisted. Prior memory/conventions explicitly forbid question text, snippets, page text, provider payloads, secrets, image blobs, Docling JSON, and full content hashes.

## Relevant existing files

- `src/tracing.py` — central Langfuse module/connection check, but currently mainly verifies availability. It imports `observe/get_client` after a broad import attempt and has v3 pin comments.
- `src/pipeline/ingest.py` — `@observe(name="ingest_document")`; updates current trace with `doc_id` and `filename`. No try/except around update; includes filename (probably okay, but decide allowlist deliberately).
- `src/pipeline/db_writer.py` — `@observe(name="write_to_db")`; updates current trace with `doc_id`, `page_count`. No defensive try/except around update.
- `src/retrieval/indexer.py` — `@observe(name="retrieval_index_build")`; has `_safe_update_trace_metadata` allowlisting index status, run_id, counts, error_class.
- `src/retrieval/retriever.py` — retrieval metadata helper allowlists boundary, run_id, evidence_reason, top_score, citation_count, is_strong, error_class.
- `src/rag/service.py` — `@observe(name="rag_answer_question")`; helper allowlists answer status, reason code, run_id, provider_name, trace_id, top_score, citation_count, evidence_reason, error_class.
- `src/extraction/pipeline.py` — core extraction orchestration has no Langfuse decorators/metadata updates despite returning safe `ExtractionDiagnostics`.
- `src/eval/retrieval_eval_runner.py` — core evaluation runner has no Langfuse spans/metadata; optional metrics are placeholders.
- `tests/test_tracing.py` — strong prior art for monkeypatching fake Langfuse context and asserting forbidden keys are absent.

## Current tracing coverage by R008 phase

- Ingestion: partial. `ingest_document` is decorated and tags metadata; update failures may propagate.
- Extraction: missing at the core orchestration boundary (`extract_document`). Provider SDK responses may have trace IDs, but pipeline-level Langfuse span metadata is not updated.
- Retrieval: mostly covered for index build and evidence retrieval with bounded metadata and no-op tests.
- Generation: mostly covered in `answer_question` with bounded metadata and no-op tests.
- Evaluation: missing. `run_retrieval_eval` creates DB eval runs/metrics but does not create an evaluation span or safe metadata.
- Latency/cost fixture traces: missing. No durable local `trace_spans`/trace summary table exists, so eval cannot surface latency/cost except via future optional data.

## Recommendation

Implement a shared, testable tracing helper and apply it to missing/fragile boundaries.

1. Add a small central helper in `src/tracing.py`.
   - Example responsibilities: `trace_observe(name)` no-op decorator, `safe_update_trace(boundary, tags, metadata, allowed_keys)` function, optional `record_trace_summary(...)` if S07 also creates SQLite fixture summaries.
   - It should catch import/auth/context failures and return `False`/no-op, never raise.
   - It should redact by construction: filter to explicit allowed keys and optionally clamp string lengths.

2. Replace ad hoc Langfuse update calls in ingestion/DB writer with the helper.
   - Keep tags like `ingestion`, `storage`.
   - Allow only operational metadata: boundary, doc_id, filename (if considered non-sensitive for demo), page_count, image_count, status, error_class. Do not include file paths, page text, Docling JSON, image bytes, provider payloads.

3. Add extraction tracing around `extract_document`.
   - Decorate or wrap `extract_document` with `@observe(name="extract_document")` via no-op-safe helper.
   - On success, update metadata from `ExtractionDiagnostics`: boundary=`extraction`, run_id, doc_id, trace_id, provider_name, page_count, review_state, needs_review.
   - On known failures, update only boundary, run_id/doc_id if available, reason_code, error_class. Do not include exception message because provider errors may contain payloads/secrets.

4. Add evaluation tracing around `run_retrieval_eval`.
   - Decorate with `@observe(name="retrieval_evaluation")` or `@observe(name="eval_retrieval")`.
   - On start/success/error, update metadata: boundary=`evaluation`, eval_type, run_id, retrieval_run_id, query_count, k_values, metric_count, status, error_class.
   - If adding latency/cost fixture support, persist only numeric summaries in `eval_metrics` or bounded trace-summary rows; never raw prompt/context/answer text.

5. Decide whether to centralize existing retrieval/RAG helpers now.
   - Minimum S07 can leave retrieval/RAG local helpers if tests remain green.
   - Better long-term: use central helper to reduce duplication and make forbidden-key policy consistent.

## Natural implementation seams

### Seam A — Central no-op-safe trace helper

Files:
- `src/tracing.py`
- `tests/test_tracing.py`

Tasks:
- Add `safe_update_current_trace(tags, metadata, allowed_keys)` or equivalent.
- Ensure it handles Langfuse unavailable, context missing, auth/config absent, and backend update exceptions.
- Add redaction/allowlist tests using fake context.

First proof:
- Fake context receives only allowed keys; forbidden keys and forbidden values are absent from metadata representation.
- Failing fake context does not alter caller behavior.

### Seam B — Harden ingestion/storage tracing

Files:
- `src/pipeline/ingest.py`
- `src/pipeline/db_writer.py`
- `tests/test_tracing.py` or new `tests/test_ingest_tracing.py`

Tasks:
- Replace direct `langfuse_context.update_current_trace(...)` calls with central helper or wrap direct calls in strict try/except and allowlist.
- Ensure file paths, page text, image blobs, and Docling JSON cannot be sent.

First proof:
- Unit test monkeypatches fake context and verifies ingestion/storage metadata keys only. If full Docling ingest is too heavy, test helper-level or DB writer-level tracing with simple inputs.

### Seam C — Add extraction tracing

Files:
- `src/extraction/pipeline.py`
- `tests/test_tracing.py` or new `tests/test_extraction_tracing.py`

Tasks:
- Decorate/observe `extract_document` and update trace metadata on success/failure.
- Reuse `ExtractionDiagnostics`; it already contains safe fields.
- For exceptions, use `reason_code` and `error_class`, not raw messages.

First proof:
- Fixture DB + fake extraction provider produces trace metadata with `boundary=extraction`, `run_id`, `doc_id`, `provider_name`, `review_state`, `needs_review`, and no page text/provider payload.
- Failing fake context still returns the same extraction result.

### Seam D — Add evaluation tracing and optional trace-summary data

Files:
- `src/eval/retrieval_eval_runner.py`
- Possibly `src/eval/repository.py` and `src/db/schema.py` if recording local trace summaries for latency/cost proof.
- `tests/test_retrieval_eval_runner.py`, `tests/test_retrieval_eval_optional_metrics.py`, `tests/test_tracing.py`

Tasks:
- Add observe/update boundary around `run_retrieval_eval`.
- Include only counts and IDs: eval run_id, retrieval_run_id, query_count, k_values, status, metric_count, error_class.
- If adding SQLite trace-summary fixture table, keep it numeric/identifier-only and use it for R007 latency/cost tests.

First proof:
- Retrieval eval with fake context records evaluation metadata and still completes with Langfuse unavailable/failing.

## Suggested allowed metadata keys

Global/common:
- `boundary`, `status`, `error_class`, `reason_code`, `run_id`, `trace_id`

Ingestion/storage:
- `doc_id`, `filename`, `page_count`, `image_count`

Extraction:
- `provider_name`, `review_state`, `needs_review`, `page_count`

Retrieval/index:
- `index_status`, `source_document_count`, `source_page_count`, `indexed_page_count`, `evidence_reason`, `top_score`, `citation_count`, `is_strong`

Generation:
- `answer_status`, `provider_name`, `top_score`, `citation_count`, `evidence_reason`

Evaluation:
- `eval_type`, `retrieval_run_id`, `query_count`, `k_values`, `metric_count`

Forbidden regardless of phase:
- `question`, `prompt`, `answer_text`, `context`, `snippet`, `page_text`, `field_value`, `expected_value`, `verbatim_span`, `provider_payload`, `raw_response`, `api_key`, `secret`, `image_blob`, `docling_json`, `content_hash`, full file paths.

## Skill discovery

Installed relevant skill: `observability`. Its guidance is directly relevant: make unattended/background subsystems diagnosable with structured, bounded failure signals while avoiding noisy or unsafe logs. No separate Langfuse-specific installed skill is present; implementation can proceed with existing tests and pinned Langfuse v3 API.

## Verification

Use Windows-safe commands:

- Focused: `venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py tests/test_extraction_pipeline.py tests/test_ingest.py`
- Full: `venv/Scripts/python.exe -m pytest -q`

Expected new/updated tests:

- Extraction success trace metadata is allowlisted and bounded.
- Extraction failure trace metadata does not include exception message/payload.
- Evaluation trace metadata records run/status/counts only.
- Ingestion/DB writer Langfuse update failure does not crash pipeline behavior.
- Existing retrieval/RAG forbidden-key tests remain green.
- Missing Langfuse keys/imports still produce no-op behavior.

## Watch-outs

- There is inconsistency in Langfuse imports: `src/tracing.py` uses `from langfuse import observe, get_client`, while retrieval/RAG modules use `from langfuse.decorators import langfuse_context, observe`. Tests currently expect v3 imports. Do not migrate to Langfuse v4 paths.
- Do not log raw exception messages from provider boundaries; the existing RAG test intentionally checks that a secret-looking provider error string does not enter trace metadata.
- `filename` may be acceptable in demo traces, but `file_path` should not be traced because it can expose local user/project paths.
- If centralizing helpers, update tests carefully; monkeypatch patterns currently target module-local `_LANGFUSE_AVAILABLE` and `langfuse_context` in retrieval/RAG modules.
