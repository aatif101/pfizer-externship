# S02: Compliance dashboard run selector

**Goal:** Wire the Compliance dashboard to S01 run-scoped extraction history so a viewer can choose latest-write compatibility state or a specific historical extraction run, with clear baseline/candidate/latest labeling and bounded diagnostics.
**Demo:** The Compliance tab can select a specific extraction run and clearly labels whether the user is viewing baseline, candidate, or latest compatibility state.

## Must-Haves

- `src.dashboard.compliance` exposes credential-free, provider-free adapter helpers that load run summaries, build safe selector labels, classify baseline/candidate/historical/latest display state, and load compliance rows either from latest-write compatibility or from `list_compliance_records_for_run()`.
- The Streamlit Compliance tab renders a run selector when historical runs exist, defaults to latest compatibility state, and clearly labels the selected view as Latest compatibility state, Baseline run, Candidate run, or Historical run.
- Existing empty-state behavior remains deterministic for missing databases or missing history tables.
- Source-detail image loading remains lazy and only uses the selected rows.
- Tests cover two persisted runs for the same document and prove selecting a historical run changes visible rows without relying on latest-write fallback.
- Verification uses Windows-native Python invocations only; no `/bin/bash` and no `gsd_exec` runtime=bash.

## Proof Level

- This slice proves: Integration proof: repository-backed pytest coverage plus Streamlit fake-render tests exercise the real dashboard adapter and render path. Real browser/UAT is not required in this slice; final real dashboard UAT remains in S05.

## Integration Closure

Upstream surfaces consumed: `src.extraction.repository.list_extraction_run_summaries()`, `src.extraction.repository.list_compliance_records_for_run()`, existing latest-write `list_compliance_records()`, and Streamlit rendering in `src.dashboard.compliance`. New wiring introduced: Compliance tab selector and labels choose between latest compatibility rows and explicit run-scoped rows. Remaining milestone work: usage/cost observations in S03, visual fallback in S04, and real five-document comparison/UAT in S05.

## Verification

- Runtime signals are dashboard-visible bounded run summaries: run id, inferred run kind, status, document count, field count, trace id, started/completed timestamps, and selected view label. Inspection surfaces are the Compliance tab selector/info messages and repository-backed adapter tests. Failure visibility: missing DB/table states become deterministic empty lists and empty-state UI instead of tracebacks. Redaction constraints: selector labels and diagnostics must not include raw prompts, page text, provider payloads, images, PDFs, secrets, or local confidential artifact paths.

## Tasks

- [x] **T01: Add run selector adapter contract** `est:1h`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/dashboard/compliance.py`, `tests/test_compliance_dashboard.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py

- [x] **T02: Wire selector into Compliance tab** `est:1h 30m`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/dashboard/compliance.py`, `tests/test_compliance_dashboard.py`, `tests/test_dashboard_compliance_tab.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py

- [x] **T03: Run dashboard regression closeout** `est:30m`
  Expected executor skills: verify-before-complete.
  - Files: `src/dashboard/compliance.py`, `tests/test_compliance_dashboard.py`, `tests/test_dashboard_compliance_tab.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py tests/test_dashboard_ui_helpers.py tests/test_app.py tests/test_extraction_persistence.py tests/test_extraction_run_history_schema.py

## Files Likely Touched

- src/dashboard/compliance.py
- tests/test_compliance_dashboard.py
- tests/test_dashboard_compliance_tab.py
