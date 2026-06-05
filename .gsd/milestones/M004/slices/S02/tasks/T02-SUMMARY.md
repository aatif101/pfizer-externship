---
id: T02
parent: S02
milestone: M004
key_files:
  - src/dashboard/compliance.py
  - tests/test_compliance_dashboard.py
  - tests/test_dashboard_compliance_tab.py
key_decisions:
  - The Compliance tab selector label is now `Extraction run view`, and the selected option object (not raw UI input) is used for row loading and diagnostics.
  - Selected historical run empty states intentionally do not fall back to latest-write rows; they name only the selected bounded run/view metadata.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:31:31.428Z
blocker_discovered: false
---

# T02: Wired the Compliance tab to a validated extraction-run selector with explicit latest, baseline, candidate, and historical view diagnostics.

**Wired the Compliance tab to a validated extraction-run selector with explicit latest, baseline, candidate, and historical view diagnostics.**

## What Happened

Updated `render_compliance_tab()` so it loads run selector options before compliance rows, renders the selector as `Extraction run view`, and passes the validated selected option ID into the T01 adapter. The selected view now renders a prominent info message plus bounded caption diagnostics: latest-write compatibility state for the default view, and run kind, run ID, status, document count, field count, trace ID, started timestamp, and completed timestamp for persisted runs. Historical selected-run views no longer reuse latest-state copy; their current-state message explicitly says only that run’s rows are shown, and empty selected-run views name the selected run/view without falling back to latest rows. Existing summary metrics, table columns including Run ID and Trace ID, source detail rendering, and lazy `get_page_image()` behavior were preserved. Expanded fake Streamlit support to capture headers, captions, selectbox labels/options/formatted labels, dataframes, source-detail messages, and deterministic selector choices; added render tests for default latest copy, baseline row filtering, candidate labels, unknown historical empty state, missing run history fallback, and selected-row-only source image lookup.

## Verification

Ran the task verification target with the Windows-safe GSD node wrapper: `venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py`. All 14 tests passed, covering selector display, selected-state diagnostics, row filtering, empty states, source-detail behavior, and legacy latest/empty behavior.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py` | 0 | ✅ pass | 6589ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/dashboard/compliance.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_dashboard_compliance_tab.py`
