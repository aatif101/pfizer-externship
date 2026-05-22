---
estimated_steps: 8
estimated_files: 3
skills_used: []
---

# T01: Add shared dashboard UI helpers (headers, dividers, empty states, metric/table formatting)

Why: UI polish must be consistent across tabs without duplicating ad-hoc formatting logic in each renderer.

Do:
- Create a small, dependency-free UI helper module (Streamlit-only) for shared patterns: tab header (title + short caption), section separators, consistent empty-state callouts, and small formatting helpers (percent, float, datetime-ish strings).
- Keep helpers presentation-only: no SQLite access, no provider/tracing imports.
- Add minimal unit tests for formatting helpers (pure functions only) to keep polish deterministic.

Done when:
- Helper module exists and is imported by at least one tab renderer.
- Formatting helper tests pass.

## Inputs

- `src/dashboard/compliance.py`
- `src/dashboard/eval.py`
- `src/dashboard/chat.py`
- `tests/test_dashboard_eval_tab.py`

## Expected Output

- `src/dashboard/ui.py`
- `tests/test_dashboard_ui_helpers.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_dashboard_ui_helpers.py -q
