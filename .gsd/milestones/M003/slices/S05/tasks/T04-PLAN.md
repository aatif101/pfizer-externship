---
estimated_steps: 6
estimated_files: 7
skills_used: []
---

# T04: Run full dashboard test suite and ensure no regressions to provider-free/read-only guarantees

Why: Polish work can accidentally change behavior; this task closes the loop with a broader regression run.

Do:
- Run the full test suite (or at minimum all dashboard tests) under the project Python 3.11 venv.
- If any failures indicate accidental behavior changes (e.g., new Streamlit calls not covered by fakes, changed strings, ordering), adjust implementation/tests to keep behavior deterministic and within the read-only/provider-free boundaries.

Done when:
- Dashboard-related tests pass as a group and the suite is green.

## Inputs

- `src/dashboard/eval.py`
- `src/dashboard/compliance.py`
- `src/dashboard/chat.py`
- `src/dashboard/ui.py`
- `tests/test_dashboard_eval_tab.py`

## Expected Output

- `src/dashboard/eval.py`
- `src/dashboard/compliance.py`
- `src/dashboard/chat.py`
- `src/dashboard/ui.py`
- `tests/test_dashboard_eval_tab.py`
- `tests/test_dashboard_compliance_tab.py`
- `tests/test_dashboard_chat_tab.py`

## Verification

venv/Scripts/python.exe -m pytest -q
