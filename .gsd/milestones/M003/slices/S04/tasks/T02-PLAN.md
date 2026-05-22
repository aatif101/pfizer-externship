---
estimated_steps: 14
estimated_files: 2
skills_used: []
---

# T02: Implement run comparison UI and comparison-focused tests

Why: The success criteria requires comparing at least two runs in the dashboard so a compliance officer can see whether changes improved extraction/retrieval performance.

Do:
- Extend `render_eval_tab` in `src/dashboard/eval.py` to support comparing two runs:
  - Add a secondary run selector (optional) filtered to compatible types by default (same eval_type), with an override to compare any.
  - Compute a comparison table keyed by (metric_name, scope_type, scope_id) showing value A, value B, and delta (B - A) where both values exist.
  - Provide UI controls to toggle showing only changed metrics and to include/exclude per-scope metrics (to keep UI readable on large per-query metric sets).
  - Ensure robust handling when one run has no metrics or missing keys: show blanks, not crashes.
- Expand `tests/test_dashboard_eval_tab.py` (or add `tests/test_dashboard_eval_tab_compare.py`) to cover:
  - Empty DB → no crash.
  - One run present → metric view renders.
  - Two runs present → comparison table includes expected metric rows and deltas.
  - Mixed eval_type runs: default filter behavior works.

Done when:
- Comparison UI renders and the tests assert deterministic comparison output using Streamlit’s AppTest harness.

## Inputs

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`
- `src/eval/repository.py`

## Expected Output

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_dashboard_eval_tab.py -q

## Observability Impact

Makes evaluation regressions visible by highlighting metric deltas between two persisted runs without requiring external tracing tools.
