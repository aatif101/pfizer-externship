---
id: T02
parent: S04
milestone: M001
key_files:
  - src/dashboard/compliance.py
  - src/dashboard/__init__.py
  - src/app.py
  - tests/test_compliance_dashboard.py
key_decisions:
  - Kept the Compliance renderer credential-free and provider-free, with one compliance row load per render and lazy page-image lookup for selected source evidence only.
  - Used display-label keys directly in the dataframe rows instead of relying on Streamlit `column_config` label behavior for better version compatibility.
duration: ""
verification_result: passed
completed_at: 2026-05-20T17:56:30.930Z
blocker_discovered: false
---

# T02: Wired the Compliance tab to render persisted SQLite compliance records with summary metrics, table fields, and lazy source evidence previews.

**Wired the Compliance tab to render persisted SQLite compliance records with summary metrics, table fields, and lazy source evidence previews.**

## What Happened

Extended `src/dashboard/compliance.py` with `render_compliance_tab(db_path: str | None = None)`, preserving the existing row-loading and formatting adapter while adding a Streamlit render path. The renderer now shows a deterministic empty/setup state for missing or empty SQLite data, summary metrics for total documents and risk/review counts, a display-safe compliance table with risk/status/vendor/date/confidence/review/source/run/trace columns, and a selected-document source evidence detail section. Source page images are fetched lazily through `get_page_image` only for the selected row, and nullable/missing/malformed source image fields fall back to a sanitized 'No source preview available' message instead of raising. Updated `src/app.py` so `st.set_page_config` remains the first Streamlit call, then the Compliance tab calls `render_compliance_tab(get_settings().db_path)` while Chat and Eval placeholders remain unchanged. Added render-level tests using a fake Streamlit surface to verify empty-state rendering, populated source-detail rendering, and lazy/missing-image behavior without requiring credentials or a preexisting `compliance.db`.

## Verification

Ran the task verification command `venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py tests/test_app.py -q`. It passed with 7 tests, covering SQLite load/format behavior, null source evidence formatting, render empty state, populated source-detail path, lazy missing-image tolerance, and Streamlit app smoke startup.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py tests/test_app.py -q` | 0 | ✅ pass (7 passed) | 8080ms |

## Deviations

Used a fake Streamlit object for render-level tests instead of `streamlit.testing.v1.AppTest` to keep the tests stable and focused on the dashboard render contract.

## Known Issues

None.

## Files Created/Modified

- `src/dashboard/compliance.py`
- `src/dashboard/__init__.py`
- `src/app.py`
- `tests/test_compliance_dashboard.py`
