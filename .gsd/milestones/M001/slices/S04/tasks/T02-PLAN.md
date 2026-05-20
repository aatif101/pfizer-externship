---
estimated_steps: 8
estimated_files: 3
skills_used: []
---

# T02: Render compliance records and source evidence in Streamlit

Expected executor skills/frontmatter: estimated_steps: 9; estimated_files: 3; skills_used: [verify-before-complete, make-interfaces-feel-better].

Why: The evaluator-facing Compliance tab must stop being a placeholder and show the persisted S03 records with risk, confidence, review, run metadata, and source evidence.

Do: Extend `src/dashboard/compliance.py` with `render_compliance_tab(db_path: str | None = None) -> None`. Render a friendly empty/setup message when `load_compliance_rows` returns no rows. When rows exist, render summary metrics for total documents, red/amber/green/unknown counts, and needs-review count. Render a `st.dataframe` table with visible columns for risk/status, vendor, doc type, date fields, age_days, confidence, review_state/needs_review, source page label, run_id, and trace_id. Add a simple detail selector (for example, by `doc_id`) or expanders that display risk reason, source page label, source_verbatim_span, and source_bbox only outside the main table. Use `get_page_image` lazily for the selected/detail row only and tolerate missing images.

Wire `src/app.py` so page config remains the first Streamlit call, then import `get_settings` and `render_compliance_tab`, and call `render_compliance_tab(get_settings().db_path)` inside the Compliance tab. Keep Chat/Eval placeholders unchanged and keep Langfuse status non-fatal.

Failure Modes (Q5): Missing image or malformed nullable source fields must render a message such as no source preview available rather than raising. Streamlit startup must not require `GEMINI_API_KEY`, Langfuse credentials, or a preexisting `compliance.db`.

Load Profile (Q6): Use one record load per render and lazy one-image lookup for selected details; do not load all page image blobs into the table.

Negative Tests (Q7): Extend `tests/test_compliance_dashboard.py` with render-level tests using Streamlit monkeypatches or `streamlit.testing.v1.AppTest` only if stable; assert empty-state rendering path and populated source-detail path do not crash.

Done when: Compliance tab is wired to real SQLite-backed rendering and app smoke tests still pass.

## Inputs

- `src/dashboard/compliance.py`
- `tests/test_compliance_dashboard.py`
- `src/app.py`
- `src/config.py`
- `src/db/queries.py`
- `tests/test_app.py`

## Expected Output

- `src/dashboard/compliance.py`
- `src/app.py`
- `tests/test_compliance_dashboard.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py tests/test_app.py -q

## Observability Impact

Adds UI-level operational visibility: summary counts, review-state counts, run_id/trace_id, risk reasons, source page labels, and source spans are visible for diagnosis while secrets and full raw document/page text remain hidden.
