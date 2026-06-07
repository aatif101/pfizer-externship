---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T03: Browser UAT of Compliance and Eval dashboard tabs

Why: R015 requires verified dashboard evidence that the run selector and metric comparison views surface the visual-fallback candidate correctly. No code changes are needed - this task verifies existing behavior on real data from compliance.db written by T02. Do: (1) Start Streamlit via bg_shell: command venv\Scripts\python.exe -m streamlit run src/app.py, type:server, ready_port:8501. (2) Use browser_navigate to http://localhost:8501 and wait for page load. (3) Compliance tab UAT: navigate to the Compliance tab, locate the 'Extraction run view' selector, confirm vf-candidate-20260607 appears as an option with a label containing 'Candidate run' or 'Historical run'. Select it; confirm compliance rows load or empty state renders without error. (4) Eval tab UAT: navigate to the Eval tab, confirm the run selector shows an extraction_eval run referencing vf-candidate-20260607. Select it as Primary run, select a baseline eval run as Compare; confirm metric delta rows appear for extraction.macro.f1, extraction.macro.precision, extraction.macro.recall. (5) Use browser_assert to confirm selector elements are visible and at least one metric row appears. Capture a screenshot as evidence. Done when: browser_assert confirms both tab selectors rendered and at least one eval metric delta row is visible in the Eval tab comparison view.

## Inputs

- `src/app.py`
- `src/dashboard/compliance.py`
- `src/dashboard/eval.py`

## Expected Output

- Update the implementation and proof artifacts needed for this task.

## Verification

venv\Scripts\python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py tests/test_app.py
