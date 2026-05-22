# S03: Retrieval and RAG evaluation metrics (recall, RAGAS, citation accuracy, latency and cost)

**Goal:** Compute and persist retrieval and RAG evaluation metrics (recall@5/10, citation accuracy, and optional latency/cost + optional RAGAS), backed by the existing SQLite gold query set and eval_runs/eval_metrics tables, with deterministic offline tests and graceful empty-state behavior.
**Demo:** Compute retrieval recall at 5 and 10 and basic citation accuracy against a gold query set; when optional trace metadata exists, attach latency and cost summaries; persist a retrieval or RAG eval run to SQLite.

## Must-Haves

- New provider-free metric module(s) compute retrieval recall@k and citation accuracy from gold_retrieval_* tables and a retrieval index run.
- `src/eval/repository.py` supports reading whatever additional data is needed for these metrics (e.g., latest retrieval index run, retrieval index pages).
- Callable entrypoint can create an eval_run, compute metrics, and upsert eval_metrics without duplicating rows.
- Optional metrics are safe:
- If RAG outputs / provider configs are missing, RAGAS metrics are skipped without crashing.
- If latency/cost trace fields are absent, those metrics are skipped without crashing.
- Pytest proves: empty gold set -> no crash + no/zero metrics; non-empty gold -> deterministic recall/citation results; metric upsert is idempotent.

## Proof Level

- This slice proves: contract + integration (SQLite-backed) with deterministic pytest coverage; no live LLM or Langfuse required.

## Integration Closure

Consumes: `src/db/schema.py` eval + gold tables, `src/eval/repository.py` run/metric upsert helpers, and the existing retrieval index tables. Produces: retrieval/RAG metric computation functions + repository read helpers, plus contract tests that will be consumed by S04 Streamlit Eval tab rendering.

## Verification

- Adds evaluation metrics rows (eval_metrics) for retrieval/RAG runs with clear metric_name + scope fields (query_id, doc_id) to support audit and downstream UI; ensures optional metric paths are explicitly non-fatal.

## Tasks

- [x] **T01: Add provider-free retrieval eval metrics (recall@k and page-level citation accuracy) with gold query/target support** `est:1.5-2h`
  Why: S03 needs deterministic, provider-free retrieval metrics to satisfy R007 and to power the Streamlit Eval tab run history.
  - Files: `src/eval/retrieval_metrics.py`, `tests/test_retrieval_eval_metrics.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_metrics.py -q

- [x] **T02: Extend eval repository with retrieval gold + index helpers and implement an eval runner to persist S03 metrics into eval_runs/eval_metrics** `est:2.5-3.5h`
  Why: Metrics must be computed against the real SQLite contract (gold_retrieval_* + retrieval_index_* tables) and persisted as eval_runs/eval_metrics so S04 can render run history and comparisons.
  - Files: `src/eval/repository.py`, `src/eval/retrieval_eval_runner.py`, `tests/test_retrieval_eval_runner.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_runner.py -q

- [x] **T03: Optional hooks for latency/cost and RAGAS metric placeholders that degrade gracefully (no secrets, no crashes)** `est:1.5-2h`
  Why: R007 requires latency/cost and faithfulness/relevancy metrics, but they must be optional and must not require live providers in deterministic test runs.
  - Files: `src/eval/retrieval_eval_runner.py`, `tests/test_retrieval_eval_optional_metrics.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_optional_metrics.py -q

## Files Likely Touched

- src/eval/retrieval_metrics.py
- tests/test_retrieval_eval_metrics.py
- src/eval/repository.py
- src/eval/retrieval_eval_runner.py
- tests/test_retrieval_eval_runner.py
- tests/test_retrieval_eval_optional_metrics.py
