# S07: Implement R008 Langfuse tracing — UAT

**Milestone:** M003
**Written:** 2026-05-27T21:21:32.229Z

# S07 UAT: Langfuse tracing safety contract

**UAT Type:** Automated contract and integration UAT; no live Langfuse, provider credentials, dashboard runtime, or human walkthrough required for this slice.

## Preconditions

- Use the project Python 3.11 virtual environment via `venv/Scripts/python.exe`.
- Do not configure live Langfuse credentials; tests use fake and missing contexts to prove no-op behavior.
- SQLite-backed fixtures and offline provider fakes are available from the test suite.

## Steps

1. Run the focused tracing suite:
   `venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py tests/test_extraction_pipeline.py tests/test_ingest.py`
2. Inspect trace metadata tests for allowed operational keys at ingestion/storage, extraction, and evaluation boundaries.
3. Confirm missing Langfuse context and raising fake trace backends do not fail ingestion, extraction, retrieval evaluation, or optional metrics flows.
4. Confirm forbidden sensitive terms are absent from serialized trace metadata assertions.
5. Confirm retrieval evaluation optional metrics continue to surface aggregate latency/cost/RAGAS-style metrics from persisted observation rows.

## Expected Outcomes

- Pytest exits 0 with the focused cross-pipeline suite passing.
- Trace metadata contains useful compact fields such as boundary, status, run_id, doc_id, eval_type, retrieval_run_id, count fields, provider_name, review_state, needs_review, error_class, and typed reason_code where safe.
- Trace metadata excludes raw document/question/provider content, file paths, image blobs, Docling JSON, raw responses, full content hashes, API keys/secrets, and raw exception messages.
- Langfuse import/auth/backend failures are operationally invisible to core behavior: pipelines continue to return or raise exactly as before.

## Edge Cases Covered

- Langfuse context missing or unavailable.
- Trace backend update raises.
- Empty or unsafe trace payload after filtering.
- Invalid PDF/ingestion failure.
- Missing extraction document, no pages, no page text, malformed provider payload, provider exception with secret-looking message.
- Empty retrieval eval state with no index or no gold queries.
- Optional metrics absent or malformed observation rows.

## Operational Readiness (Q8)

- **Health signal:** Passing focused tests plus Langfuse spans, when configured, should show boundary/status/run or doc identifiers and count/metric summaries for ingestion, storage, extraction, retrieval/generation coverage, and evaluation.
- **Failure signal:** Pipeline behavior does not depend on Langfuse; trace failures are swallowed by the helper and represented only by a false helper return in tests. Application-level failures still surface through existing typed exceptions, result statuses, and persisted eval records.
- **Recovery procedure:** If tracing metadata is missing, verify Langfuse configuration separately, then run `tests/test_tracing.py` to distinguish helper/filtering regressions from backend availability. If a new field is needed, add it to the relevant boundary allowlist with a no-raw-content test before emitting it.
- **Monitoring gaps:** This slice does not add dashboard-side tracing, live Langfuse UAT screenshots, or alerting on trace delivery failures. S08 remains responsible for Eval tab runtime/UAT evidence, not for changing the R008 tracing contract.
