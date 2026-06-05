---
estimated_steps: 14
estimated_files: 2
skills_used: []
---

# T01: Add run selector adapter contract

Expected executor skills: tdd, verify-before-complete.

Why: S02 needs a small credential-free adapter seam before touching Streamlit rendering so run selection behavior is testable without a browser and without provider/runtime dependencies.

Do:
1. In `tests/test_compliance_dashboard.py`, add tests that create two extraction runs for the same document using existing fixtures/helpers, then assert adapter helpers can load bounded run summaries and load compliance rows for latest compatibility versus each explicit run independently.
2. Add negative tests for missing `extraction_runs`/history tables returning a latest-only selector state rather than raising `sqlite3.OperationalError`.
3. In `src/dashboard/compliance.py`, import `ExtractionRunSummary`, `list_extraction_run_summaries`, and `list_compliance_records_for_run` from `src.extraction.repository`.
4. Add a small internal data contract such as a frozen dataclass or plain dict for selector options containing a stable option id, display label, view kind, run id, status, document count, field count, trace id, and timestamps. Keep values bounded and display-only.
5. Implement helper functions such as `load_extraction_run_summaries(db_path)`, `build_run_selector_options(summaries)`, `load_compliance_rows_for_selection(db_path, selected_option_id)`, and run-kind/label helpers. Always include a latest compatibility option; classify explicit runs as baseline when the run id contains `baseline`, candidate when it contains `candidate`, and otherwise historical run.
6. Preserve current `load_compliance_rows(db_path)` behavior for latest-write compatibility and missing DB/table empty states.
7. Do not store or expose raw prompts, page text, provider payloads, images, PDFs, secrets, or local artifact paths in labels or diagnostics.

Failure Modes (Q5): repository schema may be absent during a fresh dashboard open; convert missing run-history/compliance tables to empty selector rows and latest empty state. Malformed/unknown selected option ids must fall back to latest compatibility state rather than querying arbitrary run ids.

Load Profile (Q6): each dashboard rerun should perform one bounded run-summary query plus one compliance-row query for the selected state. At 10x more runs, labels remain metadata-only and no page images or extraction field text are loaded for the selector.

Negative Tests (Q7): cover missing history tables, unknown selector ids, explicit run id with no rows, and two run ids for the same document producing distinct selected-row values.

Done when: adapter tests prove run summaries and selected rows are deterministic, run-specific reads do not fall back to latest-write state, and latest compatibility behavior remains unchanged.

## Inputs

- `src/dashboard/compliance.py`
- `src/extraction/repository.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_extraction_persistence.py`

## Expected Output

- `src/dashboard/compliance.py`
- `tests/test_compliance_dashboard.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_compliance_dashboard.py

## Observability Impact

Adds bounded run-summary selector state as an inspection surface and keeps missing-table states visible as deterministic empty/latest-only UI state rather than unhandled exceptions.
