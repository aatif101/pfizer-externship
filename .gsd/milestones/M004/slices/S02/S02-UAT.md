# S02: Compliance dashboard run selector — UAT

**Milestone:** M004
**Written:** 2026-06-03T22:34:09.012Z

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: This slice is a dashboard adapter and Streamlit render-path wiring change; repository-backed pytest fixtures and fake Streamlit render tests prove the selectable run behavior without requiring a live browser. Final real dashboard UAT remains in M004/S05.

## Preconditions

- Python virtual environment dependencies are installed.
- S01 run-history repository surfaces are present: `list_extraction_run_summaries()` and `list_compliance_records_for_run()`.
- Test fixtures can create at least two extraction runs for the same document plus latest-write compatibility compliance rows.

## Smoke Test

Run `venv\Scripts\python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py` and confirm all tests pass. This verifies the selector adapter and Compliance tab render path together.

## Test Cases

### 1. Latest compatibility state remains the default

1. Seed compliance rows and historical run summaries.
2. Render the Compliance tab without a user-selected historical run.
3. **Expected:** The selector defaults to latest compatibility state, rows are loaded from latest-write compatibility, and the displayed view label is `Latest compatibility state`.

### 2. Baseline and candidate runs are selectable and labeled

1. Seed two extraction runs for the same document, one baseline-like and one candidate-like, with different compliance records.
2. Select each explicit historical run through its validated selector option.
3. **Expected:** The visible rows change to the selected run's records, and the UI labels the selected view as `Baseline run` or `Candidate run` based on bounded run metadata.

### 3. Historical selected run with no rows does not fall back to latest

1. Seed a known historical run summary that has no run-scoped compliance records.
2. Select that known run.
3. **Expected:** The Compliance tab shows an empty selected-run state for that run/view metadata and does not display latest-write rows.

### 4. Malformed or unknown selector values are safe

1. Provide an unknown or malformed selector option such as an unrecognized `run:<run_id>`.
2. Load rows through the adapter.
3. **Expected:** The adapter falls back to latest compatibility state rather than querying arbitrary run IDs or raising a traceback.

## Edge Cases

### Missing history tables or missing database

1. Point the dashboard helper at a database without S01 run-history tables, or at an absent database path.
2. Render the Compliance tab.
3. **Expected:** Run summaries resolve to an empty deterministic list and the existing empty/latest behavior remains stable without tracebacks.

### Source details remain scoped to selected rows

1. Select a historical run with a narrow row set.
2. Expand or render source details.
3. **Expected:** Source-detail image loading is attempted only for rows in the selected view, not for other historical/latest rows.

## Failure Signals

- The run selector is missing when historical runs exist.
- Baseline, candidate, historical, or latest labels are absent or misleading.
- Selecting a known historical run still displays latest-write rows.
- Unknown selector values raise exceptions or query arbitrary run IDs.
- Missing database/history tables produce tracebacks instead of deterministic empty UI.
- Tests in `tests/test_compliance_dashboard.py` or `tests/test_dashboard_compliance_tab.py` fail.

## Not Proven By This UAT

- It does not prove a real browser session against the final 5-document local database; that remains M004/S05.
- It does not prove Gemini usage/cost observation capture; that remains M004/S03.
- It does not prove visual fallback extraction quality; that remains M004/S04 and S05.

## Notes for Tester

Selector labels and diagnostics are intentionally bounded. They may include run id, inferred run kind, status, document count, field count, trace id, and timestamps, but they must not include raw prompts, page text, provider payloads, images, PDFs, secrets, or confidential local artifact paths.
