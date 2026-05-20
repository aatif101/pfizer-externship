---
id: S04
parent: M001
milestone: M001
provides:
  - Offline Streamlit compliance tab backed by persisted extraction rows.
  - Validated dashboard contract for R004 and downstream UI/evaluation polish.
  - Reusable compliance dashboard module for future milestones.
requires:
  - slice: S03
    provides: Persisted extraction/compliance records via `list_compliance_records` and page image lookup support via `get_page_image`.
affects:
  - M001
  - M003
key_files:
  - src/dashboard/__init__.py
  - src/dashboard/compliance.py
  - src/app.py
  - tests/test_compliance_dashboard.py
  - tests/test_app.py
key_decisions:
  - Keep Compliance dashboard data access credential-free and provider-free by wrapping only SQLite repository/query functions.
  - Use additive display-label fields for Streamlit compatibility while preserving raw compliance row keys.
  - Treat missing DB/table states as empty dashboard states rather than exceptions.
  - Load source page images lazily only for selected detail records.
patterns_established:
  - SQLite-backed dashboard adapter normalizes compliance rows before rendering.
  - Friendly empty states for absent persistence layers.
  - Sanitized, lazy source evidence display for compliance UI.
observability_surfaces:
  - Dashboard summary metrics by risk/review state.
  - Run_id and trace_id columns in compliance records.
  - Risk reasons and source page/span details in record detail views.
  - Sanitized empty/error UI states instead of stack traces.
drill_down_paths:
  - .gsd/milestones/M001/slices/S04/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S04/tasks/T02-SUMMARY.md
  - .gsd/milestones/M001/slices/S04/tasks/T03-SUMMARY.md
  - .gsd/exec/1c1054ab-1c3a-4ff9-a247-d39977fbbb57.stdout
duration: ""
verification_result: passed
completed_at: 2026-05-20T18:04:36.633Z
blocker_discovered: false
---

# S04: Compliance dashboard records

**Replaced the Compliance tab placeholder with an offline, SQLite-backed Streamlit dashboard that renders persisted extraction/compliance records, risk status, confidence, review metadata, and sanitized source evidence.**

## What Happened

S04 closes the Phase 2 compliance display loop by adding `src.dashboard.compliance` and wiring `src/app.py` to render real compliance records from SQLite through `list_compliance_records`. The dashboard adapter formats persisted metadata for Streamlit while preserving raw row values, converts source pages to user-facing 1-indexed display, normalizes nullable fields, formats review/confidence/risk/run metadata, and handles missing databases or missing `compliance_records` tables as deterministic empty states. The Streamlit renderer shows summary metrics, risk/review status, a readable records table, and lazy source evidence detail with page/span information plus optional page-image preview via `get_page_image`; it intentionally makes no Gemini, Langfuse, or other provider calls. Edge-case tests cover empty and malformed persistence states, null source evidence, page-index conversion, needs_review int-to-boolean formatting, lazy missing-image tolerance, and Streamlit app smoke startup without credentials. Requirement records R002, R003, and R004 were updated to validated based on the M001 schema/extraction/dashboard chain.

## Verification

Closeout verification ran through the required verification surface with `venv/Scripts/python.exe -m pytest -q` via `gsd_exec` run `1c1054ab-1c3a-4ff9-a247-d39977fbbb57`. Result: exit code 0, `71 passed, 19 warnings in 111.50s`. Prior task-level verification also passed: T01 ran `venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py -q` with 5 tests; T02 ran `venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py tests/test_app.py -q` with 7 tests; T03 ran the full regression. Verification covers real SQLite adapter behavior, dashboard render contracts, app startup without provider credentials, friendly empty states, source page display, and lazy source evidence handling.

## Requirements Advanced

- R008 — App/dashboard startup remains non-fatal without Langfuse/Gemini credentials and the UI avoids secret/raw provider exposure; broader tracing coverage remains for later milestones.

## Requirements Validated

- R002 — M001 S02-S04 schema/extraction/dashboard chain persists and displays structured SDF metadata with source evidence from SQLite.
- R003 — M001 S02-S04 implement/test risk computation, persist computed risk, and render risk levels/reasons from SQLite dashboard rows.
- R004 — S04 tests and full regression prove Streamlit Compliance tab renders SQLite records with metadata, risk display, confidence, review state, and source page/span evidence.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

T02 used a fake Streamlit object for render-level tests instead of `streamlit.testing.v1.AppTest` to keep tests stable and focused on the dashboard render contract. No source-level deviations from the slice goal.

## Known Limitations

The dashboard is a baseline offline display surface, not a polished production compliance console. Page previews are optional/lazy, sorting/filtering remains Streamlit-basic, and live Langfuse trace ingestion is not proven by this slice.

## Follow-ups

Later milestones can improve dashboard visual polish, richer filtering/sorting, source-page navigation, and production-scale performance. R008 still has broader cross-operation tracing coverage beyond this dashboard startup behavior.

## Files Created/Modified

- `src/dashboard/__init__.py` — Introduced dashboard package exports for compliance rendering.
- `src/dashboard/compliance.py` — Added compliance dashboard adapter, formatting helpers, empty-state handling, metrics, table rendering, and lazy source evidence/detail display.
- `src/app.py` — Wired the Compliance tab to the dashboard renderer using configured SQLite database path.
- `tests/test_compliance_dashboard.py` — Added SQLite-backed adapter and render contract tests for populated, empty, nullable, and source-evidence edge cases.
- `tests/test_app.py` — Added/updated Streamlit app smoke coverage for compliance tab startup.
