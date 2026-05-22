---
estimated_steps: 8
estimated_files: 5
skills_used: []
---

# T03: Polish Compliance and Chat tabs for consistent presentation and actionable empty states

Why: The demo experience depends on all tabs feeling cohesive; empty states should guide the evaluator to the next action.

Do:
- Apply shared UI helpers to Compliance and Chat tabs: consistent headers/captions, section separation, and consistent phrasing for empty states.
- Compliance: ensure the summary metrics + table + source evidence sections have consistent spacing and headings; keep data adapter credential-free and preserve lazy page-image loading.
- Chat: ensure the chat intro/help text is concise and consistent; keep provider seams and existing safe error handling unchanged.
- Update/extend existing dashboard tests (or add a small new test) to confirm the new empty-state text and/or header structure is stable.

Done when:
- Compliance and Chat renderers use the shared helper(s) and all relevant dashboard tests pass.

## Inputs

- `src/dashboard/compliance.py`
- `src/dashboard/chat.py`
- `src/dashboard/ui.py`
- `tests/test_dashboard_eval_tab.py`

## Expected Output

- `src/dashboard/compliance.py`
- `src/dashboard/chat.py`
- `tests/test_dashboard_compliance_tab.py`
- `tests/test_dashboard_chat_tab.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_dashboard_compliance_tab.py tests/test_dashboard_chat_tab.py -q
