# S04: Streamlit Eval tab: run history, comparisons, empty states

**Goal:** Implement the Streamlit Eval tab that reads SQLite-backed evaluation run history (eval_runs/eval_metrics), renders safe empty states, and enables selecting and comparing two runs without triggering any evaluation computation from the UI.
**Demo:** Open Streamlit and see a populated Eval tab listing eval runs and metrics, with the ability to select and compare two runs and clear guidance for missing gold and evals.

## Must-Haves

- Eval tab renders with no eval runs (friendly empty state; no exceptions).
- Eval tab renders with runs present and shows metrics for a selected run.
- Eval tab supports selecting and comparing two runs and shows metric deltas.
- UI is read-only: it does not trigger evaluation computation or provider calls.

## Proof Level

- This slice proves: integration

## Integration Closure

Consumes SQLite-backed evaluation history contracts from S01–S03 (`eval_runs`/`eval_metrics` via `src.eval.repository`) and wires the new Eval tab into the Streamlit entrypoint (`src/app.py`).

## Verification

- Provides a UI inspection surface for evaluation pipeline health (run status/error_reason) and for tracking quality drift over time via persisted metrics.

## Tasks

- [x] **T01: Add dashboard eval adapter + tab renderer (run history, metric view, empty states)** `est:2h`
  Why: The milestone needs an evaluator-facing surface that can browse evaluation history and metrics without requiring any provider config or recomputation on Streamlit reruns.
  - Files: `src/dashboard/eval.py`, `src/dashboard/__init__.py`, `src/app.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_dashboard_eval_tab.py -q

- [x] **T02: Implement run comparison UI and comparison-focused tests** `est:2h`
  Why: The success criteria requires comparing at least two runs in the dashboard so a compliance officer can see whether changes improved extraction/retrieval performance.
  - Files: `src/dashboard/eval.py`, `tests/test_dashboard_eval_tab.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_dashboard_eval_tab.py -q

## Files Likely Touched

- src/dashboard/eval.py
- src/dashboard/__init__.py
- src/app.py
- tests/test_dashboard_eval_tab.py
