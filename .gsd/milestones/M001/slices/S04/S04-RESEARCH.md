# S04 Research: Compliance dashboard records

## Summary

S04 is a targeted Streamlit/SQLite slice. The backend pieces from S02/S03 are already in place: `src.extraction.repository.list_compliance_records(db_path)` returns one dashboard-ready row per document from `compliance_records`, and `src.db.queries.get_page_image(db_path, doc_id, page_num)` can retrieve stored page thumbnails. `src/app.py` is still the Phase 1 shell with a placeholder Compliance tab, so the slice should focus on replacing that placeholder with a small, testable UI layer over the existing repository/query seams.

Active requirements supported by this slice:

- R002: surface exactly-six-field extraction outputs through document metadata columns and review/abstention visibility.
- R003: show conservative risk status, reason, `age_days`, run metadata, and source evidence from persisted `compliance_records`.
- R004: preserve source-page/span grounding in the UI before users trust provider facts.
- R008: keep app startup deterministic and safe without optional credentials; dashboard must not require Gemini/Langfuse.

## Recommendation

Create a small dashboard module rather than adding all logic inline in `src/app.py`:

- Add `src/dashboard/compliance.py` with pure-ish helpers:
  - `load_compliance_rows(db_path: str) -> list[dict]` wrapping `list_compliance_records` and handling missing DB/table cases with an empty result or typed UI state.
  - `format_compliance_rows(rows)` to add display labels such as 1-indexed source page (`source_page_display = source_page + 1`) while preserving raw values.
  - `render_compliance_tab(db_path: str | None = None) -> None` for Streamlit rendering.
  - Optional small helpers for risk labels/colors and source-evidence detail rendering.
- Update `src/app.py` to import `get_settings` and call `render_compliance_tab(get_settings().db_path)` inside the Compliance tab.
- Keep `src.extraction.repository` as the DB boundary for records; use `src.db.queries.get_page_image` only for optional page preview/detail.
- Do not require pandas directly. `st.dataframe` can render list/dict data, and avoiding a new dependency keeps S04 narrow.

## Implementation Landscape

Existing files and purposes:

- `src/app.py` — Streamlit entry point. Has sidebar Langfuse status and three tabs. Compliance tab currently only calls `st.header` and `st.info` placeholder. Page config is top-level and must remain the first Streamlit call.
- `src/config.py` — `Settings.db_path` defaults to `compliance.db` and can be overridden with `DB_PATH`; `get_settings()` is cached, so tests that monkeypatch env should call `get_settings.cache_clear()`.
- `src/extraction/repository.py` — has `_COMPLIANCE_COLUMNS` and `list_compliance_records(db_path)`. It returns deterministic rows ordered by expiry date, vendor, doc_id with columns: `doc_id`, `doc_type`, `vendor_name`, all four date fields, `aggregate_confidence`, `review_state`, `needs_review`, `trace_id`, `run_id`, `extracted_at`, `risk_level`, `risk_reason`, `compliance_status`, `age_days`, `source_page`, `source_bbox`, `source_verbatim_span`.
- `src/db/queries.py` — has `get_page_image(db_path, doc_id, page_num)` for page PNG blobs and `list_documents(db_path)` for ingestion records. Page numbers are 0-indexed in DB.
- `src/db/schema.py` — `compliance_records` already exists with indexes on risk/review/vendor/expiry/run/trace. No S04 schema change appears necessary.
- `tests/test_app.py` — current smoke test starts Streamlit headlessly for 5 seconds. It can remain, but S04 should add targeted tests for dashboard formatting/render helpers instead of relying only on process startup.
- `tests/test_extraction_persistence.py` and `tests/test_extraction_pipeline.py` — contain usable fixtures/patterns for creating a temp DB, inserting documents, upserting records, and asserting `list_compliance_records` shape.

Current constraints:

- App startup currently calls `verify_langfuse_connection()` once via session state. This remains non-fatal, but tests should set `LANGFUSE_ENABLED=false` or monkeypatch the dashboard module when using Streamlit AppTest.
- `compliance_records.source_page` is 0-indexed. UI must display human-facing 1-indexed page labels while not changing persistence semantics.
- Source spans may be null for fully abstained rows, but uncertain data must remain visible rather than hidden.
- Existing repository returns `needs_review` as SQLite int `0`/`1`; UI formatting should normalize for display without changing DB.
- Missing `compliance.db` is possible before extraction is run. A friendly empty state is better than a stack trace on initial app launch.

## Natural Seams / Suggested Tasks

1. **Data adapter and formatting tests**
   - New module: `src/dashboard/compliance.py`.
   - Functions: load rows, normalize display rows, map risk/review display values, compute page display label.
   - Tests: create temp DB with `init_db`, `insert_document`, `upsert_extraction_record` using existing test patterns; assert formatted rows include risk, confidence, review, age, source span, and `source_page_display == 1` when DB page is `0`.

2. **Streamlit render function**
   - Same module, `render_compliance_tab`.
   - Render an empty state if no rows exist.
   - Render summary metrics such as total docs, red/amber/green counts, and needs-review count.
   - Render a table with visible columns: risk/status, vendor, doc type, date fields, age_days, confidence, review_state/needs_review, source page, run_id/trace_id.
   - Render source evidence in a selected-row/detail area or expanders: source page label, source span, risk reason, and optional image via `get_page_image`.

3. **Wire app entrypoint**
   - `src/app.py` Compliance tab should call `render_compliance_tab(get_settings().db_path)` and keep Chat/Eval placeholders unchanged.
   - Avoid putting DB query logic in `app.py`; this makes AppTest and unit tests easier.

4. **Dashboard tests / app startup**
   - Add `tests/test_compliance_dashboard.py` for helper-level tests and optionally `streamlit.testing.v1.AppTest` smoke coverage.
   - Local introspection confirms Streamlit 1.56.0 and `streamlit.testing.v1.AppTest` are available in the venv. `AppTest.from_file('src/app.py').run()` is viable, but helper tests are likely less brittle.

## First Proof

The first proof should be a test that uses the real SQLite schema/repository and no Streamlit process:

1. Initialize a temp DB.
2. Insert one document and upsert a realistic extraction record with risk metadata.
3. Call the new dashboard loader/formatter.
4. Assert the row exposes: vendor, doc_type, all date fields, `risk_level`, `risk_reason`, `compliance_status`, `age_days`, confidence, review state, run_id/trace_id, source span, and 1-indexed source page display.

This de-risks the real S04 requirement before spending effort on visual layout.

## Verification Plan

Use the required Python 3.11 venv path.

Targeted commands:

```bash
venv/Scripts/python.exe -m pytest tests/test_compliance_dashboard.py -q
venv/Scripts/python.exe -m pytest tests/test_app.py -q
```

Regression command:

```bash
venv/Scripts/python.exe -m pytest -q
```

Optional manual/UAT check after data exists:

```bash
venv/Scripts/python.exe -m streamlit run src/app.py --server.headless true
```

Expected visual result: Compliance tab shows non-placeholder SQLite-backed rows, risk colors/states, confidence, review/abstention visibility, and source page/span evidence.

## Risks / Watch-outs

- `st.dataframe` row-click support can become a rabbit hole. Prefer a simple `selectbox` keyed by `doc_id` or expanders for source evidence unless row selection is already straightforward in Streamlit 1.56.
- Do not mutate DB page numbers for UI convenience; display `source_page + 1` only in formatted output.
- Avoid displaying raw `source_bbox` JSON in the main table. It can be hidden or placed in details if useful; source page/span are the acceptance-critical evidence.
- Missing database/table should not crash Streamlit startup. If `list_compliance_records` raises `sqlite3.OperationalError`, render a setup/empty message such as “No compliance records yet. Run ingestion and extraction first.”
- Do not call live Gemini or extraction provider code from the dashboard. S04 should be read-only over SQLite.
- Keep secrets out of UI/logs: run IDs and trace IDs are okay; provider keys and page text blobs are not.

## Skill Discovery

Installed skills relevant by category:

- `frontend-design` / `make-interfaces-feel-better` could inform polish if the executor is asked for visual refinement, but S04 is mainly a Streamlit data-surface slice.
- `observability` is relevant as a principle: app startup and dashboard empty/error states should expose deterministic status without optional credentials or secret/page-text leakage.

External skill search results, not installed:

- `silvainfm/claude-skills@streamlit` — 207 installs; likely directly relevant to Streamlit implementation. Install command if desired: `npx skills add silvainfm/claude-skills@streamlit`.
- `streamlit/streamlit@understanding-streamlit-architecture` — 65 installs; may be useful for rerun/session-state architecture. Install command: `npx skills add streamlit/streamlit@understanding-streamlit-architecture`.
- `streamlit/streamlit@fixing-streamlit-ci` — 86 installs; useful if AppTest or headless CI flakes. Install command: `npx skills add streamlit/streamlit@fixing-streamlit-ci`.

## Sources / Evidence

- Memory query: compliance dashboard records returned Phase 2 persistence/risk/schema patterns (`MEM005`, `MEM009`, `MEM010`, `MEM011`, `MEM014`).
- Local code read: `src/app.py`, `src/config.py`, `src/db/schema.py`, `src/db/queries.py`, `src/extraction/repository.py`, `src/extraction/models.py`, `src/extraction/pipeline.py`, `tests/test_app.py`, `tests/test_extraction_persistence.py`, `tests/test_extraction_pipeline.py`.
- Local venv introspection: Streamlit version is `1.56.0`; `streamlit.testing.v1` is available.
