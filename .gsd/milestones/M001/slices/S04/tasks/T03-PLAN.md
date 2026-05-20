---
estimated_steps: 6
estimated_files: 3
skills_used: []
---

# T03: Run slice regression and tighten dashboard edge cases

Expected executor skills/frontmatter: estimated_steps: 5; estimated_files: 2; skills_used: [verify-before-complete].

Why: S04 is the final M001 slice and must prove the new dashboard surface did not regress extraction persistence, app startup, or offline credential behavior.

Do: Run the targeted checks first, then the full project regression with the required Python 3.11 virtualenv. If tests reveal dashboard-specific edge cases, make narrow fixes in `src/dashboard/compliance.py` and/or `tests/test_compliance_dashboard.py`; if app startup fails due to import order, fix `src/app.py` while preserving `st.set_page_config` as the first Streamlit call. Do not broaden scope into extraction providers, schema changes, or visual redesign.

Failure Modes (Q5): Regression failures should be localized to dashboard formatting/rendering, app import order, or preexisting tests. Do not mask provider or credential errors by calling live providers.

Negative Tests (Q7): Confirm the test suite includes no-doc/no-table dashboard behavior and null-evidence handling before claiming completion.

Done when: targeted dashboard/app tests and full regression pass through `venv/Scripts/python.exe`.

## Inputs

- `src/dashboard/compliance.py`
- `src/app.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_app.py`

## Expected Output

- `src/dashboard/compliance.py`
- `src/app.py`
- `tests/test_compliance_dashboard.py`

## Verification

venv/Scripts/python.exe -m pytest -q

## Observability Impact

Ensures final dashboard behavior is verified with executable evidence and any edge-case failures remain visible through tests rather than manual inspection only.
