---
estimated_steps: 11
estimated_files: 3
skills_used: []
---

# T03: Run dashboard regression closeout

Expected executor skills: verify-before-complete.

Why: The selector changes the dashboard's main compliance render path, so closeout should re-run the focused dashboard regression set plus run-history repository tests to prove S01 compatibility remains intact.

Do:
1. Run the focused compliance dashboard tests from T01/T02.
2. Run UI helper and app/dashboard smoke tests that cover imports and neighboring dashboard tabs.
3. Run S01 repository tests that cover run-scoped compliance/history behavior and latest compatibility.
4. If a regression appears, fix only selector-related regressions in files touched by this slice; do not expand scope into S03 usage, S04 visual fallback, or S05 real evaluation.
5. Capture final verification evidence using Windows-native commands. If using GSD evidence, use `gsd_exec` runtime=node spawning `venv\\Scripts\\python.exe`; do not use bash.

Requirement Impact (Q4): re-verifies R012 and protects R011 compatibility while maintaining R016/R017 constraints.

Failure Modes (Q5): app smoke may fail if top-level imports accidentally introduce provider credentials or tracing side effects; dashboard tests should localize such failures to the compliance adapter/render seam.

Done when: all listed tests pass with fresh evidence and no bash-based verification was invoked.

## Inputs

- `src/dashboard/compliance.py`
- `src/dashboard/ui.py`
- `src/app.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_dashboard_compliance_tab.py`
- `tests/test_dashboard_ui_helpers.py`
- `tests/test_app.py`
- `tests/test_extraction_persistence.py`
- `tests/test_extraction_run_history_schema.py`

## Expected Output

- `src/dashboard/compliance.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_dashboard_compliance_tab.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py tests/test_dashboard_ui_helpers.py tests/test_app.py tests/test_extraction_persistence.py tests/test_extraction_run_history_schema.py

## Observability Impact

Provides fresh closeout evidence that the dashboard selector works and that latest-write compatibility plus run-history diagnostics remain inspectable.
