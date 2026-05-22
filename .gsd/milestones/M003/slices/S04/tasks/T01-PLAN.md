---
estimated_steps: 19
estimated_files: 3
skills_used: []
---

# T01: Add dashboard eval adapter + tab renderer (run history, metric view, empty states)

Why: The milestone needs an evaluator-facing surface that can browse evaluation history and metrics without requiring any provider config or recomputation on Streamlit reruns.

Do:
- Create a new module `src/dashboard/eval.py` that follows the existing dashboard patterns (credential-free, read-only). It should:
  - Load evaluation runs from SQLite via `src.eval.repository.list_eval_runs`.
  - Provide helper(s) to load metrics for a selected run via `src.eval.repository.list_eval_metrics`.
  - Render clear empty states:
    - If DB path is missing/unopenable or schema tables are missing: show an st.warning/st.info explaining how to create runs (CLI / tests) and do not crash.
    - If eval_runs is empty: show an st.info “No evaluation runs yet” with guidance.
  - Render a run table (or dataframe) showing: run_id, eval_type, status, created_at, completed_at, pipeline_label.
  - Provide selection UI (e.g., selectbox) for a primary run and display its metrics grouped into:
    - Global metrics (scope_type/scope_id null)
    - Per-scope metrics (e.g., per query) in a compact expandable table.
  - Keep the module provider-free: do not import LLM SDKs, Langfuse, retrieval, or evaluation runners.
  - Avoid heavy recomputation: only query SQLite; do not create eval runs.
- Update `src/dashboard/__init__.py` to export `render_eval_tab`.
- Update `src/app.py` tab wiring so the Eval tab calls `render_eval_tab(get_settings().db_path)` instead of the placeholder st.info.

Done when:
- `streamlit run src/app.py` can render the Eval tab against an empty DB without crashing and shows deterministic empty-state messaging.
- With a DB containing at least one eval_run/eval_metrics, the tab shows a run list and metrics for the selected run.

## Inputs

- `src/app.py`
- `src/dashboard/__init__.py`
- `src/dashboard/compliance.py`
- `src/eval/repository.py`
- `src/db/schema.py`

## Expected Output

- `src/dashboard/eval.py`
- `src/dashboard/__init__.py`
- `src/app.py`
- `tests/test_dashboard_eval_tab.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_dashboard_eval_tab.py -q

## Observability Impact

Adds a new evaluator-facing UI surface for inspecting eval run status + errors via eval_runs.error_reason and for verifying persisted metrics without rerunning evaluation.
