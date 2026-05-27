# S06 — Research: Complete R007 metric coverage

## Summary

S06 should close the remaining R007 gaps by turning the current retrieval-eval placeholders into real, repeatable metrics while preserving the existing provider-free dashboard contract. The repo already has a solid base: `eval_runs`/`eval_metrics` persistence, extraction F1 helpers, retrieval recall/citation metrics, and an Eval tab that renders persisted rows only. The missing pieces are real faithfulness/relevancy metric persistence, robust latency/cost summaries, and tests proving optional services/data are absent-safe.

Key risk: `src/eval/retrieval_eval_runner.py` currently exposes `include_latency_cost` and `include_ragas` flags, but both are effectively placeholders. Latency/cost tries `SELECT AVG(duration_ms), P50(duration_ms), P95(duration_ms) FROM trace_spans` even though no `trace_spans` schema exists and SQLite does not provide `P50`/`P95` aggregate functions by default; this is swallowed as an optional no-op. RAGAS is not in `pyproject.toml`, and the hook only imports `ragas` then checks nonexistent `gold_rag_answers` / `gold_rag_contexts` tables.

## Requirements and constraints

- Owns/supports **R007**: evaluation harness must include extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost.
- Supports **R008** only indirectly: latency/cost may come from trace metadata, but S06 should not require Langfuse or secrets.
- Dashboard modules must remain credential-free/read-only. Do not compute evals in `src/dashboard/eval.py` or on Streamlit rerun.
- Persist only numeric metrics and bounded metadata. Do not store prompts, snippets, raw page text, provider payloads, image blobs, secrets, Docling JSON, or full hashes in eval metrics.
- Optional services must be deterministic no-ops when missing: no RAGAS install, no provider config, no trace data, no gold answers, or empty DB should not fail core extraction/retrieval evals.

## Relevant existing files

- `src/eval/extraction_metrics.py` — deterministic extraction precision/recall/F1 and normalization; likely already satisfies extraction-F1 part of R007.
- `src/eval/retrieval_metrics.py` — provider-free `compute_retrieval_recall_at_k` and page-level citation accuracy.
- `src/eval/retrieval_eval_runner.py` — persists retrieval recall/citation metrics; contains placeholder/no-op hooks for latency/cost and RAGAS.
- `src/eval/repository.py` — canonical eval DB adapter: `create_eval_run`, `mark_eval_run_complete/error`, `upsert_eval_metric`, `list_eval_runs`, `list_eval_metrics`, gold extraction/retrieval readers.
- `src/db/schema.py` — current schema has `eval_runs`, `eval_metrics`, `gold_extraction_labels`, `gold_retrieval_queries`, `gold_retrieval_targets`; no RAG gold-answer tables and no trace/span metric table.
- `src/rag/service.py` and `src/rag/models.py` — answer service returns bounded `AnswerResult` with answer text, citations, status diagnostics; it does not expose token/cost values.
- `src/dashboard/eval.py` — render-only Eval tab. It already recognizes ratio metric names like `faithfulness`, `answer_relevancy`, `recall`, `accuracy` for percentage formatting.
- Tests: `tests/test_retrieval_eval_runner.py`, `tests/test_retrieval_eval_optional_metrics.py`, `tests/test_extraction_eval_metrics.py`, `tests/test_eval_repository.py`, `tests/test_dashboard_eval_tab.py`.

## Current metric coverage

Covered now:

- Extraction field precision/recall/F1: implemented in `src/eval/extraction_metrics.py` and persisted by earlier slices.
- Retrieval recall@5/10: `run_retrieval_eval(..., k_values=(5,10))` persists `retrieval.recall@5` and `retrieval.recall@10` globally and per query.
- Citation accuracy: `retrieval.citation_accuracy@K` exists, using top-k retrieved pages as citations.

Not complete yet:

- Faithfulness / answer relevancy: no real computation path or schema for gold answers/contexts. `include_ragas=True` is a placeholder only.
- Latency: optional hook depends on a nonexistent `trace_spans` table and unsupported SQLite percentile functions.
- Cost: no table or DTO currently stores token/cost summaries. `AnswerProviderResult` has no token/cost fields.

## Recommendation

Implement S06 as an **offline-first RAG metric completion** slice with provider/RAGAS as optional enhancements:

1. Add a small provider-free observation input path for RAG/eval metrics.
   - Prefer a table such as `rag_eval_observations` or `eval_observations` keyed by `run_id`/`query_id` with bounded numeric/identifier fields only: latency_ms, input_tokens, output_tokens, total_tokens, cost_usd, status, cited_doc_id/page_num, optional precomputed faithfulness/relevancy.
   - Avoid storing raw question text beyond existing `gold_retrieval_queries.query_text`; avoid answer/context text in trace/metric tables unless a separate gold-answer schema is explicitly added and documented.

2. Replace `_maybe_persist_latency_cost_metrics` with deterministic SQLite-backed aggregation.
   - Do not use `P50()`/`P95()` SQL functions. Load numeric latency rows and compute p50/p95 in Python.
   - Persist canonical metric names such as `rag.latency_ms.p50`, `rag.latency_ms.p95`, `rag.cost_usd.total`, `rag.tokens.input`, `rag.tokens.output`, `rag.tokens.total` when source rows exist.
   - If no rows/table, skip without error and leave existing core retrieval metrics intact.

3. Add a real optional faithfulness/relevancy seam.
   - Short-term deterministic fallback: if observations include precomputed numeric `faithfulness` / `answer_relevancy`, aggregate and persist them. This lets fixture tests and future Langfuse/RAGAS imports feed the same contract without secrets.
   - Optional RAGAS path can be a separate function that accepts already-prepared examples and a configured judge; it should be off by default and absent-safe. Since `ragas` is not currently a dependency, do not make base tests require it.

4. Keep the dashboard unchanged except maybe metric-label readability if needed.
   - `src/dashboard/eval.py` already formats `faithfulness`, `answer_relevancy`, `accuracy`, `recall`, and latency/cost-ish values through metric names. Prefer persisting clean names rather than adding UI branching.

## Natural implementation seams

### Seam A — Schema/repository for bounded optional observations

Files:
- `src/db/schema.py`
- `src/eval/repository.py`
- `tests/test_eval_db_schema.py`
- `tests/test_eval_repository.py`

Tasks:
- Add idempotent table(s) for bounded RAG/eval observations or trace summaries.
- Add insert/list helpers with parameterized SQL and no provider imports.
- Include migration-safe `CREATE TABLE IF NOT EXISTS`; if altering existing tables, follow `_table_columns` pattern.

First proof:
- A temp DB can store two query observation rows and repository returns numeric latency/cost/faithfulness fields without raw text fields.

### Seam B — Aggregation functions for latency/cost and optional quality metrics

Files:
- New `src/eval/operational_metrics.py` or extend `src/eval/retrieval_metrics.py`
- `src/eval/retrieval_eval_runner.py`
- `tests/test_retrieval_eval_optional_metrics.py`

Tasks:
- Implement pure functions for average/p50/p95 and token/cost totals from numeric rows.
- Persist metrics only when input data exists.
- Ensure empty lists return no metrics rather than zero-valued misleading metrics, unless the metric definition explicitly says zero.

First proof:
- `include_latency_cost=True` on fixture rows persists p50/p95/cost totals; same flag on minimal DB still no-ops and core retrieval metrics remain.

### Seam C — Faithfulness/relevancy metric source

Files:
- `src/eval/retrieval_eval_runner.py` or new `src/eval/rag_eval_runner.py`
- Optional new `src/eval/ragas_metrics.py`
- Tests with fake/precomputed observations; optional RAGAS tests should be skipped when dependency/config absent.

Tasks:
- Implement aggregation of precomputed `rag.faithfulness` and `rag.answer_relevancy` observations into `eval_metrics`.
- If adding real RAGAS, isolate import inside a function and catch only missing dependency/configuration; do not swallow metric computation bugs broadly.

First proof:
- Fixture DB with two observations `{faithfulness: 1.0, 0.5}` persists `rag.faithfulness.avg = 0.75` (or similarly named metric) without importing providers or RAGAS.

## Suggested metric naming contract

Use names that the existing Eval tab formats naturally:

- `retrieval.recall@5`, `retrieval.recall@10` — already exists.
- `retrieval.citation_accuracy@5`, `retrieval.citation_accuracy@10` — already exists.
- `rag.faithfulness.avg` or `ragas.faithfulness.avg` — ratio/percent.
- `rag.answer_relevancy.avg` — ratio/percent.
- `rag.latency_ms.p50`, `rag.latency_ms.p95`, optionally `rag.latency_ms.avg` — numeric ms.
- `rag.cost_usd.total` / `rag.cost_usd.avg` — currency-ish numeric; dashboard may just show decimals unless enhanced later.
- `rag.tokens.input`, `rag.tokens.output`, `rag.tokens.total` — numeric totals.

Avoid storing raw answer/context/query payloads as metric values or params JSON.

## Skill discovery

Installed relevant skill: `observability`. Its core guidance aligns with this slice: keep failure-state persistence and diagnostics explicit, bounded, and useful for future agents. No installed RAGAS-specific skill is available. No new skill needs to be installed before implementation.

## Verification

Use Windows-safe verification:

- `venv/Scripts/python.exe -m pytest -q tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py tests/test_eval_repository.py tests/test_dashboard_eval_tab.py`
- Full confidence: `venv/Scripts/python.exe -m pytest -q`

Expected new tests:

- Optional metrics absent-safe on fresh/minimal DB.
- Latency p50/p95 computed in Python from fixture rows.
- Cost/token summaries persisted only when present.
- Faithfulness/relevancy precomputed observations aggregate and persist.
- No dashboard recomputation or provider imports introduced.

## Watch-outs

- Do not keep the current `P50(duration_ms), P95(duration_ms)` SQL approach; SQLite will not support that without custom aggregates.
- Do not add `ragas` to mandatory dependencies unless the project explicitly accepts provider/judge configuration for local dev. Optional import is safer.
- Do not compute RAGAS inside Streamlit. Eval tab must remain read-only.
- Be careful with `upsert_eval_metric`: global metrics use `scope_type=None, scope_id=None`; uniqueness relies on the expression index in `repository.py`.
