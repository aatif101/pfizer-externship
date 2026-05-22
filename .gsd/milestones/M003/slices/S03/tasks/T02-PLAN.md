---
estimated_steps: 16
estimated_files: 3
skills_used: []
---

# T02: Extend eval repository with retrieval gold + index helpers and implement an eval runner to persist S03 metrics into eval_runs/eval_metrics

Why: Metrics must be computed against the real SQLite contract (gold_retrieval_* + retrieval_index_* tables) and persisted as eval_runs/eval_metrics so S04 can render run history and comparisons.

Do:
- Extend `src/eval/repository.py` with read helpers needed for retrieval evaluation, such as:
  - `get_latest_retrieval_index_run(db_path)` (or list + choose best status) to locate the active run_id.
  - `list_retrieval_index_pages(db_path, run_id)` if needed for query-time retrieval.
- Implement a new provider-free runner module `src/eval/retrieval_eval_runner.py` that:
  - Creates an eval_run row with type like `retrieval_eval` and params including k values and retrieval_run_id.
  - Loads gold queries + targets using existing repository helpers.
  - For each gold query, executes retrieval using existing retrieval code (e.g. `src/retrieval/retriever.py` and `src/retrieval/repository.py`) to produce a ranked list of hits.
  - Computes recall@5 and recall@10, plus citation accuracy (using the same retrieved top-k as citations for now).
  - Upserts summary metrics and per-query metrics into `eval_metrics` using stable metric names (e.g. `retrieval.recall@5`, scope_type=`query`, scope_id=`<query_id>`).
  - Marks eval_run complete, or error with sanitized error_reason.

Done-when:
- A callable function like `run_retrieval_eval(db_path, k_values=[5,10])` exists and persists an eval_run + metrics.
- Repository functions return safe empty results when prerequisites are missing.
- Tests create a temp SQLite DB, insert minimal documents/pages + retrieval index rows + gold queries/targets, run the runner, and assert persisted metrics match expected values and that rerunning is idempotent (no duplicate metric rows).

## Inputs

- `src/eval/repository.py`
- `src/db/schema.py`
- `src/retrieval/indexer.py`
- `src/retrieval/repository.py`
- `src/retrieval/retriever.py`

## Expected Output

- `src/eval/retrieval_eval_runner.py`
- `tests/test_retrieval_eval_runner.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_runner.py -q

## Observability Impact

Adds persisted eval_runs/eval_metrics rows for retrieval eval, enabling downstream UI inspection and failure diagnosis via DB state.
