# S04: Compliance dashboard records

**Goal:** Replace the Compliance tab placeholder with a credential-free, SQLite-backed Streamlit dashboard that surfaces persisted extraction/compliance rows with risk status, confidence, review state, run metadata, and source evidence.
**Demo:** The Compliance tab shows document metadata, age, risk color, confidence, and source page links from SQLite.

## Must-Haves

- Owned/supporting requirements: R002, R003, R004, R008. Done when `src/app.py` wires the Compliance tab to a dashboard module over `list_compliance_records`, tests prove real SQLite records are formatted with all six-field-derived metadata and 1-indexed source-page display, Streamlit renders an empty state without a database/table, source evidence is visible without exposing secrets or raw full-page text, and app startup remains non-fatal without Gemini/Langfuse credentials.
- Threat Surface (Q3): The dashboard reads local SQLite rows containing extracted supplier metadata and source spans. Abuse/data-exposure risk is accidental display of secrets or oversized document text; keep UI read-only, only show persisted compliance fields/source spans, never provider keys or page blobs in the main table, and avoid live provider calls.
- Requirement Impact (Q4): Re-verify R002/R003 persistence display contracts, R004 Streamlit dashboard surface, and R008 offline-safe startup. No existing decision is revisited; D010 risk policy remains consumed as persisted data.
- Failure Modes (Q5): Missing DB, missing `compliance_records`, malformed nullable row values, or absent page images must produce friendly empty/detail states rather than stack traces. Langfuse/Gemini credentials are optional and must not be required.
- Load Profile (Q6): Expected demo corpus is small; per render is one compliance-record query plus optional one page-image lookup for selected detail. At 10x corpus size, `st.dataframe` rendering and image loading are first bottlenecks; keep page previews optional/lazy and avoid loading all images.
- Negative Tests (Q7): Cover empty DB/missing table, null source evidence, 0-indexed page off-by-one display, and needs_review int-to-boolean formatting.

## Proof Level

- This slice proves: Integration proof: pytest exercises real SQLite schema/repository-to-dashboard adapter and Streamlit smoke startup. Human/UAT is optional after extraction data exists; no live LLM/provider runtime is required.

## Integration Closure

Consumes S03 `src.extraction.repository.list_compliance_records(db_path)`, `src.db.queries.get_page_image(db_path, doc_id, page_num)`, and `src.config.get_settings().db_path`. Introduces `src.dashboard.compliance.render_compliance_tab` and wires it into `src/app.py`. After this slice, M001 has an end-to-end offline path from extraction persistence to visible compliance dashboard rows; later milestones can improve visual polish/source-page navigation.

## Verification

- Runtime diagnostics become visible in the UI through deterministic empty states, summary metrics by risk/review state, run_id/trace_id columns, risk reasons, and source page/span details. Failure display must be sanitized: no API keys, raw provider responses, full page text blobs, or stack traces in Streamlit.

## Tasks

- [x] **T01: Add compliance dashboard data adapter and tests** `est:1h30m`
  Expected executor skills/frontmatter: estimated_steps: 8; estimated_files: 3; skills_used: [tdd, verify-before-complete].
  - Files: `src/dashboard/__init__.py`, `src/dashboard/compliance.py`, `tests/test_compliance_dashboard.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py -q

- [x] **T02: Render compliance records and source evidence in Streamlit** `est:2h`
  Expected executor skills/frontmatter: estimated_steps: 9; estimated_files: 3; skills_used: [verify-before-complete, make-interfaces-feel-better].
  - Files: `src/dashboard/compliance.py`, `src/app.py`, `tests/test_compliance_dashboard.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py tests/test_app.py -q

- [x] **T03: Run slice regression and tighten dashboard edge cases** `est:45m`
  Expected executor skills/frontmatter: estimated_steps: 5; estimated_files: 2; skills_used: [verify-before-complete].
  - Files: `src/dashboard/compliance.py`, `src/app.py`, `tests/test_compliance_dashboard.py`
  - Verify: venv/Scripts/python.exe -m pytest -q

## Files Likely Touched

- src/dashboard/__init__.py
- src/dashboard/compliance.py
- tests/test_compliance_dashboard.py
- src/app.py
