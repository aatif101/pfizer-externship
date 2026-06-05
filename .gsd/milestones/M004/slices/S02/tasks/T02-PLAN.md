---
estimated_steps: 14
estimated_files: 3
skills_used: []
---

# T02: Wire selector into Compliance tab

Expected executor skills: tdd, verify-before-complete.

Why: The user-facing Compliance tab must let evaluators choose latest-write compatibility, baseline, or candidate runs and must make the selected state impossible to confuse.

Do:
1. Extend fake Streamlit support in `tests/test_compliance_dashboard.py` and/or `tests/test_dashboard_compliance_tab.py` so tests can inspect selectbox labels/options, info messages, captions, dataframes, and source-detail behavior.
2. Update `render_compliance_tab()` in `src/dashboard/compliance.py` to load run selector options before rows, render a selector such as `Extraction run view`, and pass the selected option to the adapter from T01.
3. Render a prominent info/caption block for the selected state. Latest compatibility should be labeled as current latest-write compatibility state; run ids inferred as baseline/candidate should say Baseline run or Candidate run; unknown historical ids should say Historical run. Include bounded status/doc/field/timestamp/trace metadata when available.
4. Keep the existing summary metrics, records table, source detail, lazy `get_page_image()` behavior, and empty compliance state. For selected historical runs with no rows, show an empty state that names only the selected run id/view label and does not fall back to latest rows.
5. Ensure table rows still include Run ID and Trace ID and reflect the selected rows, not all history.
6. Avoid changing `src/app.py` unless import wiring requires it; the existing app entrypoint should continue to call `render_compliance_tab(get_settings().db_path)`.

Threat Surface (Q3): run id selection is untrusted UI input. It must be matched against prebuilt selector options, not interpolated directly into SQL; repository calls must continue to use parameterized queries. Data exposure is limited to bounded run metadata and existing compliance row display fields.

Requirement Impact (Q4): satisfies R012 and supports R015 by making baseline/candidate selection explicit; re-verifies S01 latest-write compatibility expectations from R011 by keeping latest as the default view.

Failure Modes (Q5): if run summaries exist but selected run rows are empty, show an actionable empty state instead of silently switching to latest. If Streamlit reruns after a run disappears, fall back to latest option safely.

Negative Tests (Q7): test latest default label, baseline label, candidate label, unknown historical label, missing run history fallback, and selected-run source-detail image lookup only for the selected row.

Done when: fake-render tests prove the selector appears, selected labels are clear, dataframes change with the chosen run, and legacy empty/latest behavior remains intact.

## Inputs

- `src/dashboard/compliance.py`
- `src/dashboard/ui.py`
- `src/dashboard/__init__.py`
- `src/app.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_dashboard_compliance_tab.py`

## Expected Output

- `src/dashboard/compliance.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_dashboard_compliance_tab.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py

## Observability Impact

Adds user-visible selected-run diagnostics in the Compliance tab and preserves lazy source image loading so dashboard troubleshooting can identify which run is being inspected without exposing confidential artifacts.
