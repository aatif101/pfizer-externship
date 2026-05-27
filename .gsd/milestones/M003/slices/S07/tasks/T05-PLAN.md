---
estimated_steps: 7
estimated_files: 10
skills_used: []
---

# T05: Run focused cross-pipeline tracing verification

Expected executor skills: verify-before-complete, observability.

Why: R008 is only complete if the combined tracing boundaries work together and prior retrieval/generation behavior remains covered. This final task prevents a task-local pass from hiding cross-module regressions.

Do: Run the focused Windows-safe pytest command over tracing, ingestion, extraction, retrieval evaluation, and optional metrics tests. If tests fail, fix only issues in S07-touched files and rerun. Confirm existing retrieval/RAG trace tests in tests/test_tracing.py still pass, proving generation coverage did not regress even if retrieval/RAG local helpers were not migrated in this slice. Do not add dashboard tracing or provider calls.

Failure Modes (Q5): Test failures should identify whether breakage is in helper import compatibility, metadata filtering, no-op behavior, extraction semantics, or eval persistence. Do not accept skipped coverage for missing Langfuse keys; tests must use fakes and run offline.

Load Profile (Q6): Verification is local/offline and SQLite-backed; no network, API, or live Langfuse dependency should be required.

Negative Tests (Q7): The focused suite must include Langfuse absence, trace backend failure, forbidden metadata keys and values, empty eval prerequisites, and provider/extraction failure paths.

Done when: the focused command exits 0 and no code path added in S07 requires live Langfuse, provider credentials, or dashboard runtime.

## Inputs

- `src/tracing.py`
- `src/pipeline/ingest.py`
- `src/pipeline/db_writer.py`
- `src/extraction/pipeline.py`
- `src/eval/retrieval_eval_runner.py`
- `tests/test_tracing.py`
- `tests/test_retrieval_eval_runner.py`
- `tests/test_retrieval_eval_optional_metrics.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_ingest.py`

## Expected Output

- Update the implementation and proof artifacts needed for this task.

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py tests/test_extraction_pipeline.py tests/test_ingest.py

## Observability Impact

Provides final executable evidence that all R008 observation surfaces are safe and optional across pipeline boundaries.
