---
estimated_steps: 15
estimated_files: 3
skills_used: []
---

# T03: Wire optional RAG metrics into retrieval eval runs

---
estimated_steps: 8
estimated_files: 3
skills_used:
  - tdd
  - observability
---

Why: R007 is not complete until eval run history can persist faithfulness/relevancy, citation, latency, and cost metrics when prerequisites exist. The runner is the integration point that converts fixture/observation data into `eval_metrics` rows while keeping core retrieval recall/citation evaluation intact.

Do: Replace the placeholder optional hooks in `src/eval/retrieval_eval_runner.py` with repository-backed observation loading plus the pure aggregation from `src/eval/operational_metrics.py`. Keep `include_latency_cost=True` and `include_ragas=True` absent-safe; `include_ragas` should aggregate precomputed faithfulness/relevancy observations and may optionally attempt an isolated RAGAS import only if prepared examples/configuration are explicitly present, but base behavior must not require the dependency. Persist canonical metrics such as `rag.latency_ms.avg`, `rag.latency_ms.p50`, `rag.latency_ms.p95`, `rag.cost_usd.total`, `rag.cost_usd.avg`, `rag.tokens.input`, `rag.tokens.output`, `rag.tokens.total`, `rag.faithfulness.avg`, and `rag.answer_relevancy.avg` when source values exist. Existing `retrieval.recall@K` and `retrieval.citation_accuracy@K` behavior must remain unchanged, including per-query scoped metrics.

Done when: fixture tests prove optional observation rows create global optional metrics, missing rows/tables/config are no-ops, sanitized runner errors still mark failed eval runs, and core retrieval eval tests still pass.

Threat Surface (Q3): Optional observation data may come from traces or provider-adjacent evaluation; only numeric aggregates are persisted into `eval_metrics`, and broad exception swallowing must not hide real computation bugs except explicitly optional missing-dependency/table cases.
Requirement Impact (Q4): Owns R007 and supports R008 only indirectly via trace-like numeric metadata; re-test retrieval eval runner, optional metrics, and repository behavior.
Failure Modes (Q5): No retrieval index or no gold queries completes without metrics; no observation rows skips optional metrics; missing RAGAS/provider config skips optional RAGAS path; malformed observation data should produce a sanitized eval_run error rather than leaking payloads.
Load Profile (Q6): Retrieval eval still performs one retrieval per gold query; optional aggregation adds one bounded observation query and O(n) numeric aggregation.
Negative Tests (Q7): Fresh DB/minimal DB, empty gold queries, no observations, no RAGAS installed, null optional fields, and invalid numeric observation values if validation permits constructing them.

## Inputs

- `src/eval/retrieval_eval_runner.py`
- `src/eval/retrieval_metrics.py`
- `src/eval/repository.py`
- `src/eval/operational_metrics.py`
- `tests/test_retrieval_eval_optional_metrics.py`
- `tests/test_retrieval_eval_runner.py`

## Expected Output

- `src/eval/retrieval_eval_runner.py`
- `tests/test_retrieval_eval_optional_metrics.py`
- `tests/test_retrieval_eval_runner.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py

## Observability Impact

Turns optional evaluation observations into visible eval_metrics rows and keeps missing optional sources distinguishable from true runner errors via existing sanitized eval_run status/error fields.
