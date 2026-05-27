# S06: Complete R007 metric coverage — UAT

**Milestone:** M003
**Written:** 2026-05-27T20:49:23.451Z

## UAT Type

Contract and integration UAT with fixture-backed SQLite data; no live provider, RAGAS, Langfuse, or Streamlit credential setup required.

## Preconditions

- Use the project Python 3.11 virtual environment via `venv/Scripts/python.exe`.
- SQLite schema initialization is available from `src/db/schema.py`.
- Retrieval eval fixtures/gold data from the test suite are available.
- Optional services may be absent; this is expected and must not block core evaluation.

## Steps

1. Initialize or open a test SQLite database with the M003 evaluation schema.
2. Insert retrieval/gold query fixture data and run retrieval evaluation without optional RAG observation rows.
3. Confirm the run persists core retrieval recall and citation metrics, and optional RAG quality/latency/token/cost metrics are omitted rather than written as zeroes.
4. Insert bounded `rag_eval_observations` rows for the source retrieval/index run with numeric faithfulness, answer relevancy, latency, token, cost, and citation fields.
5. Run retrieval evaluation with optional metric collection enabled.
6. Confirm the resulting eval run persists existing recall/citation metrics plus global `rag.*` metrics for faithfulness or relevancy, latency, token, and cost summaries.
7. Open or render the Eval tab against persisted eval_runs/eval_metrics.
8. Confirm the dashboard displays percentages for quality metrics, milliseconds for latency metrics, fixed USD precision for cost metrics, integer formatting for token metrics, and comparison deltas where two compatible runs are selected.
9. Repeat with an empty or missing observation table and with no provider/RAGAS/Langfuse configuration.

## Expected Outcomes

- Core extraction/retrieval evaluation paths do not require optional services.
- Optional quality and operational metrics are repeatable from bounded SQLite observations when present.
- Empty, missing, or all-null optional metric families produce no metric instead of misleading zeroes.
- Malformed numeric observation data fails visibly through sanitized eval run failure state rather than leaking payloads.
- Eval tab remains read-only and credential-free; it does not import evaluators, providers, RAGAS, Langfuse, or execute metric computation during Streamlit reruns.
- Forbidden data classes are not stored in observation schema or eval metrics: raw prompts, answers, snippets, provider payloads, secrets, image blobs, Docling JSON, raw page text, or full hashes.

## Edge Cases

- Empty DB: Eval tab shows safe empty guidance and does not crash.
- Missing optional observation table: retrieval evaluation proceeds and omits optional `rag.*` metrics.
- Null optional values: no misleading zero metrics are emitted; dashboard renders blanks for persisted nulls.
- Unrelated observation source run IDs: ignored for the current eval run.
- Malformed non-null numeric values: recorded as a sanitized eval failure rather than a silent no-op.

## Evidence

- `venv/Scripts/python.exe -m pytest -q tests/test_eval_db_schema.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py tests/test_extraction_eval_metrics.py tests/test_dashboard_eval_tab.py` passed with 37 tests.
