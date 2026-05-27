---
estimated_steps: 7
estimated_files: 4
skills_used: []
---

# T04: Trace retrieval evaluation runs safely

Expected executor skills: observability, tdd, verify-before-complete.

Why: Evaluation is a required R008 phase and R007 benefits when evaluation runs expose latency/cost summaries from safe observation metadata, but run_retrieval_eval currently persists metrics without a trace boundary.

Do: Add a Langfuse v3-compatible observe span around run_retrieval_eval and use the shared helper for start/success/empty/error metadata. Allowed keys should include boundary=evaluation, status, eval_type, run_id, retrieval_run_id, query_count, k_values, metric_count, include_latency_cost, include_ragas if represented compactly, and error_class. Do not trace query_text, expected target content, retrieved snippets, page text, generated answers, provider payloads, prompts, raw exception messages, secrets, or full hashes. When optional latency/cost/RAGAS aggregate metrics are requested, continue using S06 rag_eval_observations and eval_metrics only; do not call providers or Langfuse APIs to fetch raw trace bodies. Update tests to verify complete runs, empty-state runs, optional latency/cost aggregation, Langfuse absence, raising trace backend, and sanitized error metadata.

Failure Modes (Q5): Missing retrieval index or gold set remains a complete empty run. Missing rag_eval_observations table or no optional rows remains a graceful skip. Retrieval/eval computation errors still mark eval_run error and re-raise, but trace metadata must avoid raw error text.

Load Profile (Q6): Evaluation can run many gold queries; trace metadata should include counts only and not scale with query text, target lists, retrieved hits, snippets, or metric row details.

Negative Tests (Q7): No retrieval index, no gold queries, malformed optional numeric observations if existing tests cover it, failing Langfuse context, and error with secret-looking exception message that must not appear in trace metadata.

Done when: retrieval evaluation produces safe trace metadata in success, empty, optional-metric, and error paths while preserving existing SQLite run and metric contracts.

## Inputs

- `src/tracing.py`
- `tests/test_tracing.py`
- `src/eval/retrieval_eval_runner.py`
- `tests/test_retrieval_eval_runner.py`
- `tests/test_retrieval_eval_optional_metrics.py`

## Expected Output

- `src/eval/retrieval_eval_runner.py`
- `tests/test_tracing.py`
- `tests/test_retrieval_eval_runner.py`
- `tests/test_retrieval_eval_optional_metrics.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py

## Observability Impact

Completes R008 phase coverage for evaluation and preserves R007 optional latency/cost visibility through safe persisted aggregate metrics.
