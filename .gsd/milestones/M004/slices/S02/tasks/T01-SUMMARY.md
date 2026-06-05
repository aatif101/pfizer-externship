---
id: T01
parent: S02
milestone: M004
key_files:
  - src/dashboard/compliance.py
  - tests/test_compliance_dashboard.py
key_decisions:
  - Selector option IDs use `latest` and `run:<run_id>`, but `run:<run_id>` is only honored when the run appears in repository-provided summaries; malformed or unknown IDs fall back to latest compatibility state.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:28:03.630Z
blocker_discovered: false
---

# T01: Added a bounded Compliance dashboard run-selector adapter for latest, baseline, candidate, and historical extraction views.

**Added a bounded Compliance dashboard run-selector adapter for latest, baseline, candidate, and historical extraction views.**

## What Happened

Implemented the run selector seam in `src/dashboard/compliance.py` by importing the repository run-history contract, adding a frozen `RunSelectorOption` display contract, and exposing helpers to load run summaries, build bounded selector options, and load compliance rows for latest compatibility or a validated explicit run. The adapter always includes latest compatibility state, classifies run IDs containing `baseline` or `candidate`, treats all other known runs as historical, and falls back to latest state for malformed or unknown selector option IDs so selector values cannot become arbitrary run-id queries. The Streamlit render path now uses the same adapter contract and displays a bounded selected-view message while preserving the existing latest-write compliance row behavior and lazy source-image loading.

## Verification

Ran the requested dashboard adapter test suite with the Windows-safe GSD verification path. The test suite covers latest compatibility reads, baseline/candidate explicit run reads for the same document, missing run-history table fallback, unknown selector fallback to latest rows, explicit known run with no compliance rows returning empty instead of latest, existing formatting behavior, and render-path empty/populated behavior.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_compliance_dashboard.py` | 0 | ✅ pass (10 passed) | 6700ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/dashboard/compliance.py`
- `tests/test_compliance_dashboard.py`
