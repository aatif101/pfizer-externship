---
id: S02
parent: M004
milestone: M004
provides:
  - Compliance dashboard run selector and selected-view labels for latest, baseline, candidate, and historical extraction states.
  - Repository-backed adapter path from S01 run summaries and run-scoped compliance records into the Compliance tab.
  - Regression coverage proving historical run selection changes visible rows without relying on latest-write fallback.
requires:
  - slice: S01
    provides: Run-scoped extraction and compliance history query functions plus stable run summary metadata.
affects:
  - S05
key_files:
  - src/dashboard/compliance.py
  - tests/test_compliance_dashboard.py
  - tests/test_dashboard_compliance_tab.py
  - tests/test_dashboard_ui_helpers.py
  - tests/test_app.py
  - tests/test_extraction_persistence.py
  - tests/test_extraction_run_history_schema.py
key_decisions:
  - Selector option IDs use `latest` and `run:<run_id>`, but explicit run IDs are honored only when they appear in repository-provided summaries.
  - Malformed or unknown selector values fall back to latest compatibility state.
  - Selected historical runs with no compliance records intentionally render empty selected-run state instead of falling back to latest-write rows.
  - The Streamlit selector label is `Extraction run view`, and the selected option object drives loading and diagnostics rather than raw UI input.
patterns_established:
  - Dashboard run selection is mediated by bounded adapter objects rather than direct Streamlit values.
  - Latest compatibility and explicit run-scoped reads are separate dashboard states to avoid latest-write ambiguity.
  - Empty states for selected historical runs are deterministic and do not mask missing run-scoped data.
observability_surfaces:
  - Compliance tab selector/info messages show bounded run summaries and selected view labels.
  - Adapter tests exercise deterministic failure visibility for missing database/history tables, unknown selectors, and selected empty runs.
drill_down_paths:
  - .gsd/milestones/M004/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S02/tasks/T02-SUMMARY.md
  - .gsd/milestones/M004/slices/S02/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-06-03T22:34:09.010Z
blocker_discovered: false
---

# S02: Compliance dashboard run selector

**The Compliance dashboard now selects latest compatibility state or explicit extraction runs and labels baseline, candidate, historical, and latest views without ambiguous latest-write fallback.**

## What Happened

S02 wired the Compliance dashboard to the S01 run-scoped extraction history surfaces. The slice first added credential-free, provider-free adapter helpers in `src.dashboard.compliance` that load extraction run summaries, build bounded selector labels, classify the selected view, and load compliance rows either from latest-write compatibility or from an explicit run-scoped query. It then rendered those helpers in the Streamlit Compliance tab through an `Extraction run view` selector that defaults to latest compatibility state when history exists and clearly announces whether the user is viewing Latest compatibility state, Baseline run, Candidate run, or Historical run. The implementation deliberately validates selector input before row loading: malformed or unknown `run:<run_id>` values fall back to latest compatibility state, while a known historical run with no compliance rows stays empty instead of silently falling back to latest rows. Source-detail image loading remains lazy because details are rendered only from the selected compliance rows. The final closeout re-ran the dashboard selector, UI-helper, app, S01 persistence, and run-history schema regression coverage together.

## Verification

Closeout verification used the required Windows-safe GSD path: `gsd_exec` with `runtime=node` spawning `venv\Scripts\python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py tests/test_dashboard_ui_helpers.py tests/test_app.py tests/test_extraction_persistence.py tests/test_extraction_run_history_schema.py`. The command exited 0 and pytest reported 54 passed in 16.34s. Task-level evidence also showed the focused adapter/render suites passing: T01 covered latest reads, explicit baseline/candidate run reads for the same document, missing-history fallback, unknown selector fallback, known empty run behavior, formatting, and empty/populated render paths; T02 covered selector display, selected-state diagnostics, row filtering, empty states, source-detail behavior, and legacy latest/empty behavior.

## Requirements Advanced

- R012 — Implemented the Compliance dashboard selector and labels for latest compatibility, baseline, candidate, and historical extraction run views.
- R017 — Closeout verification used Windows-native `gsd_exec` runtime=node spawning `venv\Scripts\python.exe`; no `/bin/bash` or `runtime=bash` was used.

## Requirements Validated

- R012 — Closeout verification passed with 54 tests covering dashboard adapter and render-path run selection, labels, selected row filtering, empty states, and S01 run-history persistence compatibility.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

- None — no requirements were invalidated or re-scoped.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

Real browser verification against the local 5-document compliance database is intentionally deferred to M004/S05. This slice does not add usage/cost observations or visual fallback behavior.

## Follow-ups

M004/S03 should attach bounded Gemini usage and estimated-cost observations to run identity. M004/S04 should use run identity when applying targeted visual fallback. M004/S05 should perform the final real 5-document dashboard comparison/UAT using the selector delivered here.

## Files Created/Modified

- `src/dashboard/compliance.py` — Added and rendered run selector adapter behavior for latest compatibility and explicit historical extraction runs with bounded labels/diagnostics.
- `tests/test_compliance_dashboard.py` — Added repository-backed adapter tests for latest, baseline, candidate, historical, unknown, empty, and missing-history states.
- `tests/test_dashboard_compliance_tab.py` — Added fake Streamlit render tests for selector display, selected-state diagnostics, row filtering, empty states, and source-detail behavior.
