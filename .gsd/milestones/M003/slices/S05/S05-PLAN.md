# S05: Dashboard polish and presentation-ready styling

**Goal:** Make the Streamlit dashboard presentation-ready by applying consistent headers, spacing, typography, and table formatting across Compliance, Chat, and Eval tabs, while preserving the provider-free/read-only guarantees and safe empty states established in prior slices.
**Demo:** Dashboard layout, typography, and table presentation feel demo-ready; Eval tab is readable and consistent with Compliance and Chat sections.

## Must-Haves

- Compliance, Chat, and Eval tabs share consistent header hierarchy (title + short caption), spacing, and section dividers.
- Tables are easier to scan: key columns are prioritized, numeric metrics are formatted, and status/risk fields have consistent labels.
- All existing dashboard tests still pass, and new/updated tests cover at least one visible polish change deterministically (no golden screenshots).
- No new runtime dependencies are introduced; UI remains credential-free and does not trigger evaluation work on rerun.

## Proof Level

- This slice proves: integration

## Integration Closure

- Uses existing dashboard entrypoint `src/app.py` and tab renderers in `src/dashboard/*`.
- Ensures Eval tab improvements remain read-only over `eval_runs` / `eval_metrics` and Compliance tab remains SQLite-only.
- Closes the UX gap between functional S04 Eval tab and demo-ready presentation without changing evaluation persistence contracts.

## Verification

- Improves evaluator-facing visibility by making run status/error_reason, metric groupings, and empty-state guidance more legible and consistent across tabs; does not change tracing or persistence.

## Tasks

- [x] **T01: Add shared dashboard UI helpers (headers, dividers, empty states, metric/table formatting)** `est:45m`
  Why: UI polish must be consistent across tabs without duplicating ad-hoc formatting logic in each renderer.
  - Files: `src/dashboard/ui.py`, `tests/test_dashboard_ui_helpers.py`, `src/dashboard/__init__.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_dashboard_ui_helpers.py -q

- [x] **T02: Polish Eval tab readability (layout, metric formatting, clearer compare UX) without changing data contracts** `est:60m`
  Why: Eval is the primary evaluator-facing surface for R007; it must be scannable in a demo and consistent with the other tabs.
  - Files: `src/dashboard/eval.py`, `tests/test_dashboard_eval_tab.py`, `src/dashboard/ui.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_dashboard_eval_tab.py -q

- [ ] **T03: Polish Compliance and Chat tabs for consistent presentation and actionable empty states** `est:60m`
  Why: The demo experience depends on all tabs feeling cohesive; empty states should guide the evaluator to the next action.
  - Files: `src/dashboard/compliance.py`, `src/dashboard/chat.py`, `src/dashboard/ui.py`, `tests/test_dashboard_compliance_tab.py`, `tests/test_dashboard_chat_tab.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_dashboard_compliance_tab.py tests/test_dashboard_chat_tab.py -q

- [ ] **T04: Run full dashboard test suite and ensure no regressions to provider-free/read-only guarantees** `est:30m`
  Why: Polish work can accidentally change behavior; this task closes the loop with a broader regression run.
  - Files: `src/dashboard/eval.py`, `src/dashboard/compliance.py`, `src/dashboard/chat.py`, `src/dashboard/ui.py`, `tests/test_dashboard_eval_tab.py`, `tests/test_dashboard_compliance_tab.py`, `tests/test_dashboard_chat_tab.py`
  - Verify: venv/Scripts/python.exe -m pytest -q

## Files Likely Touched

- src/dashboard/ui.py
- tests/test_dashboard_ui_helpers.py
- src/dashboard/__init__.py
- src/dashboard/eval.py
- tests/test_dashboard_eval_tab.py
- src/dashboard/compliance.py
- src/dashboard/chat.py
- tests/test_dashboard_compliance_tab.py
- tests/test_dashboard_chat_tab.py
