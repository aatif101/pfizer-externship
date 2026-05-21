# M003 — Research

**Date:** 2026-05-21

## Summary

M003 (“Dashboard Evaluation and Polish”) is currently blocked on missing *evaluation computation + gold set schema + DB query adapters*, not on Streamlit UI work. The Streamlit app already exposes an **Eval** tab, but it is placeholder-only (`src/app.py`). The SQLite schema already includes a minimal `evaluations` table, but there are **no query helpers** for it and **no evaluation harness modules** implementing extraction F1, retrieval recall, RAGAS faithfulness, citation accuracy, latency, or cost metrics.

Recommendation: treat M003 as a **DB contract + pure-metrics-first** milestone. Define/extend the SQLite schema to include gold labels/queries, add DB adapter functions for eval runs/metrics, implement metric computation as pure functions with tests, and only then build the Streamlit Eval UI as a render-only surface (no heavy computation on rerun).

## Recommendation

1. **Establish the missing evaluation contract in SQLite**: extend `src/db/schema.py` with gold-set tables (extraction labels + retrieval/citation labels) and add idempotent migrations (ALTER TABLE / CREATE TABLE IF NOT EXISTS patterns like the existing extraction migration).
2. **Implement evaluation computation as pure functions** (unit-testable) and add a thin “persist results” adapter that writes into `evaluations`.
3. **Implement the Streamlit Eval tab** to *render* eval run history and metric summaries from SQLite, with explicit empty/missing prerequisite states (no gold labels, no eval runs yet, etc.), following patterns in existing dashboard tabs.

## Implementation Landscape

### Key Files

- `src/app.py` — Streamlit entry point; Eval tab currently shows placeholder `st.info(...)`. Will need to call a real `render_eval_tab(...)`.
- `src/db/schema.py` — already defines `evaluations`, `retrieval_index_runs`, `retrieval_index_pages`, and optional FTS5 table. Missing the gold-set schema for M003.
- `src/db/queries.py` — contains ingestion/document/page helpers and patterns for safe parameterized SQL. No evaluation CRUD helpers exist yet.
- `src/dashboard/compliance.py` — best prior art for:
  - SQLite-safe reads
  - friendly empty states
  - non-crashing UI patterns
- `src/dashboard/chat.py` — best prior art for:
  - bounded diagnostics
  - expected missing dependency handling without tracebacks

### What exists today (evidence)

- Eval tab placeholder:
  - `src/app.py` contains `with tab_eval: ... st.info("Phase 4 will surface ... metrics here.")`
- Evaluation storage table exists:
  - `src/db/schema.py` defines `CREATE TABLE IF NOT EXISTS evaluations (...)`
- Missing glue:
  - `src/db/queries.py` does **not** define any helpers for inserting/listing eval runs/metrics.
  - No `src/eval/*` (or similar) module exists for metric computation.

### Build Order

1) **DB schema + adapters** (unblocks everything)
- Add gold set schema (tables) + query helpers.
- Add evaluation run read/write helpers (`insert_eval_metric`, `list_eval_runs`, `list_eval_metrics_for_run`, etc.).

2) **Pure metric computation + tests**
- Extraction evaluation: per-field precision/recall/F1 with explicit normalization rules.
- Retrieval evaluation: recall@5/10 driven by `retrieval_index_*` rows + gold expected pages.
- Citation accuracy: start with a conservative definition (page-level match) to avoid brittle span detection.
- Latency/cost: optional; computed when trace metadata is available, otherwise UI displays “not available”.

3) **Streamlit Eval tab implementation**
- Render persisted run history.
- Comparison across ≥2 runs.
- Safe empty states and “what to do next” guidance.

### Verification Approach

- Unit tests:
  - `venv\Scripts\python.exe -m pytest -q`
- Add at least one integration-ish test that:
  - creates a temp SQLite DB
  - calls `init_db(db_path)`
  - inserts minimal gold labels + predicted rows
  - computes metrics
  - persists metrics to `evaluations`
  - asserts the DB adapter returns correctly grouped run/metric rows

## Constraints

- Streamlit reruns: avoid doing evaluation computation directly inside render functions (would duplicate work and reinsert metrics).
- SQLite schema evolution: `CREATE TABLE IF NOT EXISTS` does not alter existing tables; follow the existing migration approach in `src/db/schema.py` (PRAGMA table_info + ALTER TABLE where needed).
- Observability allowlisting: keep trace metadata bounded and avoid logging question text/snippets/provider payloads (project memory convention).

## Common Pitfalls

- **Computing evals in Streamlit render code** — Streamlit reruns on every interaction; must separate “run evaluation” from “render evaluation results”.
- **Brittle citation accuracy definition** — start with page-level match against gold expected citations; span-level checks can be a later enhancement.
- **Missing prerequisite UX** — treat “no gold set” / “no eval runs” / “no retrieval index” as expected states with deterministic `st.info/st.warning` guidance.

## Open Risks

- Gold set schema details are still unspecified in the milestone context; pick the smallest normalized schema that supports:
  - extraction field labels per doc
  - retrieval queries with expected page(s)
  - citation expectations
- Metric definition alignment: need explicit normalization for extraction values (date formats, whitespace, casing) to avoid misleading F1.
