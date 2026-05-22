---
estimated_steps: 9
estimated_files: 3
skills_used: []
---

# T02: Polish Eval tab readability (layout, metric formatting, clearer compare UX) without changing data contracts

Why: Eval is the primary evaluator-facing surface for R007; it must be scannable in a demo and consistent with the other tabs.

Do:
- Use shared UI helpers for the tab intro caption and section headings.
- Improve run history table readability (stable column labels/order) and add lightweight formatting for timestamps/None values.
- Improve metric display formatting: round floats, display percents for metrics that are known ratios (e.g., f1/precision/recall), and render delta columns with sign (+/-) formatting.
- Keep the tab strictly read-only and provider-free; no evaluation computation or DB writes.
- Update/extend existing tests to assert the new formatted values/columns deterministically using FakeStreamlit.

Done when:
- `tests/test_dashboard_eval_tab.py` passes and asserts at least one new formatted output field (e.g., percent formatting or delta sign).

## Inputs

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`
- `src/dashboard/ui.py`

## Expected Output

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_dashboard_eval_tab.py -q
