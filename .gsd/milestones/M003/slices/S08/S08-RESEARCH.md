# S08 — Research: Record Eval tab UAT evidence

**Date:** 2026-05-27
**Depth:** Targeted research. The feature code already exists; S08 is evidence capture, runtime walkthrough, and artifact packaging.

## Summary

S08 should not add new dashboard computation. The Eval tab is already implemented as a read-only Streamlit renderer over persisted SQLite `eval_runs`/`eval_metrics`, and S06/S07 closed the backend metric/tracing work. The remaining work is to create repeatable UAT evidence proving three runtime states:

1. A populated Eval tab displays at least one persisted run and metrics.
2. The tab can compare two runs and show deltas.
3. A fresh or missing DB produces actionable empty-state messaging without crashing.

The main constraint is that evidence must be runtime/dashboard evidence, not only unit tests. Current `compliance.db` already contains 9 `eval_runs` and 112 `eval_metrics`, but only retrieval metric names (`retrieval.recall@5/10`, `retrieval.citation_accuracy@5/10`). If S08 wants to visibly reinforce R007’s optional metric coverage, seed a dedicated UAT DB with `rag.faithfulness.avg`, `rag.answer_relevancy.avg`, `rag.latency_ms.*`, `rag.cost_usd.*`, and `rag.tokens.*` metrics using repository helpers before opening Streamlit.

## Requirements Supported

- **R007** remains active and is the main requirement supported by S08. S08 should prove the dashboard renders repeatable persisted metric history, including retrieval/citation metrics and preferably optional RAG/operational metrics from S06.
- **R010 / redaction boundary** is a preservation constraint. UAT artifacts must not include raw prompts, answers, snippets, provider payloads, secrets, images of sensitive docs, Docling JSON, raw text, or full hashes. Screenshots should show metric tables and empty-state guidance only. If screenshots include seeded fake IDs/metric names, use synthetic values.
- **R008** is already validated by S07; S08 can mention it only as prerequisite context. Do not attempt live Langfuse UAT unless explicitly requested.

## Prior Context / Memories

Relevant memory findings:

- `MEM058` / `MEM061`: Eval tab is presentation-only and name-token based. It reads `eval_runs`/`eval_metrics` through repository helpers and must not import runners, providers, RAGAS, Langfuse, or compute metrics on rerun.
- `MEM022`: Dashboard rendering should treat missing DB/table state as a friendly empty UI rather than an exception.
- `MEM010`: SQLite migrations use `PRAGMA table_info` + nullable `ALTER TABLE`; not directly needed for S08 unless a script adds schema.

## Skill Discovery

Installed skills directly relevant:

- `write-docs` — useful for producing the final UAT evidence artifact for a fresh reader.
- `observability` — useful only as a checklist for health/failure/recovery wording in the evidence artifact.
- `verify-before-complete` — use before marking the slice complete; S08 is specifically evidence-gated.

External skill search:

- `npx skills find "Streamlit"` returned no skills.
- `npx skills find "SQLite"` returned several general SQLite skills. The most relevant if the user wants one installed later is:
  - `npx skills add martinholovsky/claude-skills-generator@sqlite-database-expert` (1.7K installs)
  - Not necessary for S08 because repository helpers are already established and schema work is done.

## Implementation Landscape

### `src/app.py`

Purpose: Streamlit app entry point. It creates three tabs and calls:

- `render_compliance_tab(get_settings().db_path)`
- `render_chat_tab(get_settings().db_path)`
- `render_eval_tab(get_settings().db_path)`

`DB_PATH` can be overridden via environment because `src/config.py` uses Pydantic settings field `db_path`. This is the cleanest way to run one populated UAT DB and one fresh/empty UAT DB without touching `.env`.

Current header comment still says the Eval tab is a placeholder. This is stale documentation only; not a runtime blocker. If the executor wants a tiny polish change, update the docstring to avoid confusion, but S08 can be completed with evidence only.

### `src/dashboard/eval.py`

Purpose: read-only Eval renderer and data adapter.

Key behavior already implemented:

- `load_eval_runs(db_path)` returns `[]` on missing DB/table OperationalError.
- `load_eval_metrics(db_path, run_id=...)` returns `[]` on missing metrics table.
- `render_eval_tab(...)` renders:
  - header/caption explaining read-only behavior,
  - empty state when no runs exist,
  - run history table,
  - primary run selectbox,
  - compatibility filter checkbox,
  - optional comparison run selectbox,
  - metrics table,
  - comparison table with deltas.
- Metric formatting already covers:
  - ratio metrics as percentages,
  - latency as `ms`,
  - cost as fixed USD,
  - token metrics with grouped integers.

Important seam: S08 should exercise this UI; do not move eval computation into the renderer.

### `src/eval/repository.py`

Purpose: SQLite repository for eval runs, eval metrics, gold labels, and bounded RAG/eval observations.

Useful helpers for UAT seeding:

- `create_eval_run(db_path, run_id, eval_type, pipeline_label, params)`
- `mark_eval_run_complete(db_path, run_id)`
- `upsert_eval_metric(db_path, run_id, metric_name, metric_value, scope_type=None, scope_id=None)`
- `insert_rag_eval_observation(...)` if the executor wants to prove observation aggregation indirectly, though direct metric seeding is simpler for dashboard UAT.

For a dashboard-only UAT DB, direct `create_eval_run` + `upsert_eval_metric` is enough because the Eval tab renders persisted rows only.

### `scripts/seed_and_verify.py`

Purpose: existing end-to-end demo seeding script. It initializes `compliance.db`, seeds documents/pages/compliance records/gold retrieval queries, builds a retrieval index, runs retrieval eval twice, and prints metric summaries.

Pros:

- Already runnable with `venv/Scripts/python.exe scripts/seed_and_verify.py`.
- Produces two comparable `retrieval_eval` runs.
- Prints a clear run/metric summary and suggests launching Streamlit.

Caveat:

- It seeds raw-looking page text and file names into `compliance.db`. Screenshots should focus on Eval tab metric tables, not source document content.
- It currently produces retrieval/citation metrics only, not optional `rag.*` metrics. For R007 visual proof, use a dedicated synthetic UAT DB or extend a slice-local seeding helper.

### Tests

Relevant tests already exist:

- `tests/test_dashboard_eval_tab.py` — covers empty state, populated run table, optional `rag.*` metric formatting, deltas, incompatible type filtering, and provider-free import guard.
- `tests/test_eval_repository.py` — covers eval repository contracts and observation storage boundaries.
- `tests/test_retrieval_eval_optional_metrics.py` — covers optional metric aggregation/persistence from bounded observations.
- `tests/test_app.py` — headless Streamlit startup smoke test.

These tests are supporting evidence but not sufficient alone for S08; the slice asks for recorded dashboard walkthrough evidence.

## Recommended UAT Data Strategy

Prefer a slice-local synthetic UAT DB so evidence is deterministic and sanitized:

- Path: `.gsd/milestones/M003/slices/S08/s08-uat-populated.db` (git-ignore decision left to executor; DB can be ephemeral if screenshots/markdown capture evidence).
- Initialize with `init_db`.
- Insert two complete `retrieval_eval` runs using repository helpers.
- Insert global metrics for both runs:
  - `retrieval.recall@5`, `retrieval.recall@10`
  - `retrieval.citation_accuracy@5`, `retrieval.citation_accuracy@10`
  - `rag.faithfulness.avg`
  - `rag.answer_relevancy.avg`
  - `rag.latency_ms.avg`, optionally `rag.latency_ms.p50`, `rag.latency_ms.p95`
  - `rag.cost_usd.total`, `rag.cost_usd.avg`
  - `rag.tokens.total`
- Use slightly different values between run A and run B so comparison deltas are visible.
- Optionally include one scoped query metric (`scope_type="query", scope_id="q_synthetic_001"`) to prove the expander path, but the S08 acceptance only requires global metrics and comparison.

For fresh DB evidence:

- Use a path that does not exist, e.g. `.gsd/milestones/M003/slices/S08/s08-fresh-empty.db`, or initialize an empty schema with no eval rows.
- Launch Streamlit with `DB_PATH` pointing there.
- Expected Eval tab text: `No evaluation runs yet. Run the evaluation CLI/tests to populate eval_runs and eval_metrics...` plus the DB path caption.

## Natural Seams / Suggested Task Split

1. **Prepare deterministic UAT seed data**
   - Add a slice-local helper script or one-off command in the UAT evidence artifact that creates a synthetic populated eval DB with two runs and R007-style metrics.
   - No app code should be required.
   - First proof: use repository helpers to list the two runs and metric names from the DB.

2. **Capture populated Eval tab walkthrough**
   - Start Streamlit with `DB_PATH` set to the populated UAT DB.
   - Open the app, switch to Eval, verify run history and metric table.
   - Select run A as primary and run B as comparison; verify deltas are shown.
   - Save screenshot(s) or browser debug bundle under `.gsd/milestones/M003/slices/S08/`.

3. **Capture fresh DB empty-state walkthrough**
   - Start Streamlit with `DB_PATH` set to a missing/empty DB.
   - Open Eval tab and verify the empty-state guidance renders without crash.
   - Save screenshot/debug bundle and note exact DB path used.

4. **Write UAT evidence artifact**
   - Recommended path: `.gsd/milestones/M003/slices/S08/S08-UAT-EVIDENCE.md` or a GSD `ASSESSMENT` artifact for S08.
   - Include commands run, DB paths, run IDs/metric names (synthetic only), screenshots/debug bundle paths, and pass/fail checklist.
   - Explicitly state no secrets/raw prompts/raw snippets/provider payloads are included.

## Runtime Commands / Verification

Use Windows-safe commands only. Do **not** use `/bin/bash` or `gsd_exec runtime=bash`.

### Seed existing demo data, if using current script

```text
venv/Scripts/python.exe scripts/seed_and_verify.py
```

### Start Streamlit with populated UAT DB

```text
set DB_PATH=.gsd\milestones\M003\slices\S08\s08-uat-populated.db && venv\Scripts\python.exe -m streamlit run src/app.py --server.headless true --server.port 8608
```

With `bg_shell`, use `type: "server"`, `ready_port: 8608`, and a clear label like `streamlit-s08-populated`.

### Start Streamlit with fresh DB

```text
set DB_PATH=.gsd\milestones\M003\slices\S08\s08-fresh-empty.db && venv\Scripts\python.exe -m streamlit run src/app.py --server.headless true --server.port 8609
```

### Regression tests to run before completion

Use `gsd_exec runtime=node` spawning Windows Python, for example:

```text
venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_app.py
```

S07 closeout already proved broader tracing behavior; S08 does not need to rerun the full 51-test tracing suite unless app code changes.

## Browser / Evidence Capture Notes

If browser automation tools are available to the executor:

- Navigate to `http://localhost:8608`.
- Use accessibility discovery to find and click the `Eval` tab.
- Assert visible text includes `Evaluation`, `Run history`, `Metrics`, and at least one metric such as `rag.faithfulness.avg` or `retrieval.recall@5`.
- Select comparison run B and assert a delta cell is visible (examples: `+2.5%`, `-234.6 ms`, or any seeded value).
- Capture screenshot/debug bundle.
- Repeat against `http://localhost:8609` and assert `No evaluation runs yet` is visible with no console errors/traceback.

If browser automation is not available, Streamlit’s Python testing utilities or the existing `FakeStreamlit` pattern can verify rendering, but that should be labeled as a fallback. S08 acceptance asks for a recorded dashboard walkthrough, so browser screenshots are the stronger evidence.

## Constraints and Pitfalls

- **Do not compute evals inside `render_eval_tab`**. Streamlit reruns would duplicate work and violate the established read-only boundary.
- **Do not add provider/RAGAS/Langfuse imports to dashboard code**. `tests/test_dashboard_eval_tab.py` has an import guard for this.
- **Do not screenshot sensitive source content**. The Compliance tab may show synthetic documents; keep screenshots on Eval tab or use synthetic UAT DB only.
- **Do not rely solely on current `compliance.db`** if optional R007 metric visibility is desired; current metric names are retrieval-only.
- **Fresh DB app startup exercises all tabs**, not just Eval. Compliance already handles missing tables. If Chat unexpectedly fails, record it as a blocker because Streamlit executes tab bodies during app run.
- **Existing `scripts/seed_and_verify.py` uses absolute `ROOT / "compliance.db"`**, so it cannot seed an alternate DB without modification.

## First Proof

The highest-value first proof is a tiny synthetic DB check before opening Streamlit:

1. `init_db(s08-uat-populated.db)`.
2. Create two complete `retrieval_eval` runs.
3. Upsert at least `retrieval.recall@5`, `retrieval.citation_accuracy@5`, `rag.faithfulness.avg`, `rag.latency_ms.avg`, `rag.cost_usd.total`, and `rag.tokens.total` for each run.
4. Assert `list_eval_runs` returns two rows and `list_eval_metrics` for each run returns the expected metric family names.

Once this passes, Streamlit UAT is low risk because `render_eval_tab` already has unit coverage for exactly these rows and formatting rules.

## Open Questions

- Should the final evidence artifact be stored as a slice-local markdown file (`S08-UAT-EVIDENCE.md`) or as a GSD `ASSESSMENT` artifact? Either is workable; prefer GSD `ASSESSMENT` if the planner wants it indexed in the GSD database.
- Should S08 update the stale `src/app.py` docstring that still calls Eval a placeholder? This is not required for UAT but would reduce future confusion.
- Should optional `rag.*` metrics be included in the recorded walkthrough? Recommended yes, because it visibly ties S08 back to R007 and S06.

## Sources

- `src/app.py`
- `src/config.py`
- `src/dashboard/eval.py`
- `src/dashboard/compliance.py`
- `src/eval/repository.py`
- `src/eval/retrieval_eval_runner.py`
- `scripts/seed_and_verify.py`
- `tests/test_dashboard_eval_tab.py`
- `tests/test_eval_repository.py`
- `tests/test_retrieval_eval_optional_metrics.py`
- `tests/test_app.py`
