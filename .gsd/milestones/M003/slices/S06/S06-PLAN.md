# S06: Complete R007 metric coverage

**Goal:** Complete R007 metric coverage by adding provider-free, bounded RAG/evaluation observation storage plus deterministic aggregation for faithfulness/relevancy, citation, latency, and cost metrics, while keeping the dashboard read-only and absent-safe.
**Demo:** After this: Evaluation run history includes repeatable faithfulness or relevancy, citation, latency, and cost metrics where prerequisites are configured, with deterministic fallback behavior and tests when optional services are absent.

## Must-Haves

- SQLite schema and repository expose a bounded observation source for optional RAG/eval quality and operational metrics without storing prompts, snippets, raw page text, provider payloads, image blobs, secrets, Docling JSON, or full hashes.
- Retrieval/RAG eval runs persist existing retrieval recall and citation metrics plus faithfulness/relevancy, latency, token, and cost summaries when bounded observation rows exist.
- Missing optional services or data remains a deterministic no-op: no RAGAS install, no provider config, no trace/observation data, no gold answers, no retrieval index, or empty DB does not fail core extraction/retrieval eval paths.
- Eval tab continues to read only persisted SQLite rows and formats the new metric names clearly enough to compare runs; it must not compute evals, import providers, or require credentials on Streamlit rerun.
- Verification passes with Windows-safe pytest commands, including optional-metric negative tests.

## Proof Level

- This slice proves: Contract and integration proof. Real runtime provider calls are not required; fixture SQLite data must exercise schema, repository, aggregation, runner persistence, dashboard rendering, and no-prerequisite fallback behavior.

## Integration Closure

Consumes existing M003 eval_run/eval_metric contracts, gold retrieval fixtures, retrieval eval runner, and dashboard render-only Eval tab. Introduces only bounded observation storage and pure metric aggregation; S07 remains responsible for Langfuse tracing instrumentation, while S08 remains responsible for recorded UAT evidence.

## Verification

- Adds evaluator-facing persisted numeric metrics and bounded metadata that future agents can inspect via eval_runs, eval_metrics, and observation repository helpers. Failure visibility remains sanitized through eval_run error_reason; redaction boundary forbids raw prompts, answers, snippets, provider payloads, secrets, images, and Docling JSON in eval metrics or observation rows.

## Tasks

- [x] **T01: Add bounded RAG evaluation observation storage** `est:1.5h`
  ---
  estimated_steps: 7
  estimated_files: 4
  skills_used:
    - tdd
    - observability
  ---
  - Files: `src/db/schema.py`, `src/eval/repository.py`, `tests/test_eval_db_schema.py`, `tests/test_eval_repository.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_eval_db_schema.py tests/test_eval_repository.py

- [x] **T02: Implement pure optional metric aggregation** `est:1h`
  ---
  estimated_steps: 6
  estimated_files: 2
  skills_used:
    - tdd
    - observability
  ---
  - Files: `src/eval/operational_metrics.py`, `tests/test_retrieval_eval_optional_metrics.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_retrieval_eval_optional_metrics.py

- [x] **T03: Wire optional RAG metrics into retrieval eval runs** `est:2h`
  ---
  estimated_steps: 8
  estimated_files: 3
  skills_used:
    - tdd
    - observability
  ---
  - Files: `src/eval/retrieval_eval_runner.py`, `tests/test_retrieval_eval_optional_metrics.py`, `tests/test_retrieval_eval_runner.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py

- [x] **T04: Keep Eval tab readable and credential-free for new metrics** `est:1h`
  ---
  estimated_steps: 5
  estimated_files: 2
  skills_used:
    - tdd
    - observability
  ---
  - Files: `src/dashboard/eval.py`, `tests/test_dashboard_eval_tab.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py

- [x] **T05: Run integrated R007 regression proof** `est:30m`
  ---
  estimated_steps: 4
  estimated_files: 0
  skills_used:
    - verify-before-complete
  ---
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_eval_db_schema.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py tests/test_extraction_eval_metrics.py tests/test_dashboard_eval_tab.py

## Files Likely Touched

- src/db/schema.py
- src/eval/repository.py
- tests/test_eval_db_schema.py
- tests/test_eval_repository.py
- src/eval/operational_metrics.py
- tests/test_retrieval_eval_optional_metrics.py
- src/eval/retrieval_eval_runner.py
- tests/test_retrieval_eval_runner.py
- src/dashboard/eval.py
- tests/test_dashboard_eval_tab.py
