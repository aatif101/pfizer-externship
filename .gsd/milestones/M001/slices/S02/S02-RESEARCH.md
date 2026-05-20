# S02 — Research

**Date:** 2026-05-19

## Summary

S02 should establish the extraction contract before any VLM calls are wired. The codebase already has the Phase 1 persistence foundation: `documents`, `pages`, `extractions`, and `evaluations` tables in `src/db/schema.py`; page rows use 0-indexed `page_num`; all SQL helpers in `src/db/queries.py` use parameterized placeholders; ingestion is traced with Langfuse decorators but remains non-fatal when credentials are absent. The existing `extractions` table is close to the field-level contract required by R002 because it stores `doc_id`, `field_name`, `field_value`, `confidence`, `source_page`, `source_bbox`, `verbatim_span`, `trace_id`, and `needs_review`.

The missing pieces are typed domain models, stricter field names, explicit review/abstention states, normalized date handling, and dashboard-friendly document-level persistence. A per-field table alone can represent evidence, but S03/S04 will need a single row per document for doc type, vendor, dates, aggregate confidence, review state, and later compliance risk display. S02 should therefore add Pydantic models plus persistence helpers that can upsert both field-level evidence rows and a document-level extraction/compliance summary row from deterministic sample records. Do not call Gemini/Claude in this slice; prove the contract with hand-authored records so S03 can focus on extraction pipeline wiring.

This slice primarily owns R002 and prepares R003/R004. It also supports R008 because extraction persistence should carry `trace_id`/metadata and should not require Langfuse credentials to function.

## Recommendation

Create a small `src/extraction/` package with Pydantic v2 models and a SQLite repository layer backed by schema evolution in `src/db/schema.py` / `src/db/queries.py`. Recommended contract:

- `SDFFieldName`: enum for `doc_type`, `vendor_name`, `manufacturing_date`, `effective_date`, `revision_date`, `expiry_date`.
- `ReviewState`: enum such as `pending`, `needs_review`, `reviewed`, `abstained`.
- `SourceEvidence`: `page_num` using existing DB convention (0-indexed), optional `bbox` stored as JSON, required/optional `verbatim_span` depending on abstention.
- `ExtractedField`: field name, raw value, optional normalized value/date, confidence `0..1`, evidence, review state, optional abstention reason.
- `SDFExtractionRecord`: one document's six required fields, aggregate confidence, record-level review state, trace/run metadata.

Keep the existing `extractions` table for field-level evidence, but extend it with `review_state`, `abstention_reason`, `normalized_value`, and optionally `updated_at` via migration-safe `ALTER TABLE` checks. Add a document-level table such as `compliance_records` or `document_extractions` with one row per `doc_id` containing `doc_type`, `vendor_name`, the date fields, `aggregate_confidence`, `review_state`, and placeholders for S03/S04 risk fields (`risk_level`, `risk_reason`, `age_days` can be nullable until risk is implemented). This avoids making the Streamlit dashboard pivot field rows on every render and aligns with the legacy architecture note that expected a `compliance_documents`-style table.

## Implementation Landscape

### Key Files

- `src/db/schema.py` — Current SQLite DDL. Already creates `documents`, `pages`, `extractions`, `evaluations`; should gain migration-safe additions for explicit review state/abstention and a dashboard-friendly document-level extraction table. Current `CREATE TABLE IF NOT EXISTS` will not alter existing DBs, so add a lightweight `_ensure_column`/migration step inside `init_db()` if new columns are added to existing tables.
- `src/db/queries.py` — Current query layer uses parameterized SQL and should remain the persistence boundary. Add `upsert_extraction_field(...)`, `upsert_extraction_record(...)`, `get_extraction_record(doc_id)`, and `list_compliance_records(...)` helpers here or in a thin `src/extraction/repository.py` that delegates to `_connect()`.
- `src/pipeline/ingest.py` — Establishes `doc_id` as a hash of resolved path and writes 0-indexed page rows. Extraction persistence must reuse these `doc_id` values and source pages must match `pages.page_num`.
- `src/pipeline/db_writer.py` — Pattern for small orchestration functions decorated with `@observe` and non-secret Langfuse metadata. Use the same pattern later for extraction writes, but keep S02 tests independent of credentials.
- `src/config.py` — Good place for `extraction_confidence_threshold: float = 0.75` if S02 computes `needs_review`; current settings already include DB path and Langfuse toggles.
- `src/tracing.py` — Version/credential constraints for Langfuse v3. Extraction code should not import v4 APIs and should not fail when keys are absent.
- `tests/test_db.py` — Existing schema/FK/SQL injection tests. Extend or add new tests for extraction table columns, FK behavior from extraction rows to documents, and parameterized handling of malicious field values.
- `tests/test_ingest.py` and `tests/fixtures/sample.pdf` — Existing sample PDF only contains `Sample SDF Test Page`; do not depend on it for real extraction values. Use hand-authored sample `SDFExtractionRecord` objects for S02.
- `src/app.py` — Compliance tab is still a placeholder. S02 should not build the UI, but persistence shape should make S04's table query straightforward.

### Natural Seams

1. **Typed contract only** — Add `src/extraction/models.py` and model tests. This is independent of SQLite and should catch invalid field names, confidence outside `0..1`, invalid review states, invalid/negative source pages, malformed bbox JSON/list shapes, and fields that have neither value nor abstention reason.
2. **Schema evolution** — Add/alter SQLite DDL and tests that `init_db()` works on a fresh DB and on an existing Phase 1-shaped DB. This is the main fragility point because `CREATE TABLE IF NOT EXISTS` alone will not modify current local DBs.
3. **Persistence helpers** — Add upsert/list/get functions for field rows and document-level records. Prove idempotent upsert semantics with a hand-authored sample record.
4. **Trace/review metadata** — Ensure `trace_id`, `review_state`, `needs_review`, and `abstention_reason` round-trip without requiring Langfuse connection.

### Build Order

1. **First proof: Pydantic model validation.** This defines the contract the S03 extractor must produce and avoids coupling to VLM quirks. Include sample records with all required fields and one abstained field.
2. **Schema/migration proof.** Add nullable columns/document table and verify both fresh and pre-existing DB initialization. This unblocks persistence without risking migration surprises later.
3. **Query helper proof.** Upsert a sample record for an existing document, fetch it back, and verify field-level evidence, aggregate confidence, review state, and nullable abstentions.
4. **Full regression.** Run the full Python 3.11 pytest suite to prove Phase 1 ingestion/tracing still works.

### Verification Approach

Use the project venv from D001/R009 only:

```bash
./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_persistence.py -q
./venv/Scripts/python.exe -m pytest -q
```

Suggested assertions:

- Model accepts the six required SDF fields and rejects unknown fields.
- Confidence must be between 0 and 1.
- `page_num` is non-negative and aligns with DB 0-indexed pages.
- An abstained field can have `field_value=None` only when `review_state='abstained'` and `abstention_reason` is set.
- Insert/upsert requires an existing `documents.doc_id` and fails FK checks for nonexistent docs.
- Upserting the same field twice updates instead of duplicating due to `UNIQUE (doc_id, field_name)`.
- Values containing SQL metacharacters round-trip safely.
- Missing Langfuse credentials do not affect persistence tests.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Runtime extraction contract and JSON/schema validation | Pydantic v2 already in `pyproject.toml` | Gives validators, enums, JSON schema, and structured-output compatibility for Gemini/Claude in S03 without custom validation code. |
| Date parsing/normalization | `python-dateutil` already in dependencies | Useful when S03 normalizes vendor-specific dates; S02 can store normalized ISO strings and validate obvious date shapes without inventing parsers. |
| SQLite FK and parameterization | Existing `_connect()` and query style in `src/db/schema.py` / `src/db/queries.py` | Keeps R010/security hygiene and current test patterns intact. |

## Constraints

- Use `./venv/Scripts/python.exe` for verification; global Python 3.14 is not supported for this project.
- Keep Langfuse v3 import paths only; do not introduce v4 callback/import APIs.
- Source pages should use existing DB convention: `pages.page_num` is 0-indexed. UI can display `page_num + 1` later.
- The fixture PDF does not contain real SDF metadata, so S02 should use deterministic sample records instead of pretending to extract from `tests/fixtures/sample.pdf`.
- Existing DB initialization is not a real migration system. Any new column added to an existing table needs explicit `PRAGMA table_info`/`ALTER TABLE` handling or a new table name.
- Do not log verbatim page text or secret-bearing settings; continue the Phase 1 pattern of logging only filenames/counts/status.

## Common Pitfalls

- **Relying on `CREATE TABLE IF NOT EXISTS` to evolve the schema** — it will not add new columns to existing databases. Add migration checks or use new tables.
- **Ambiguous page numbering** — Docling provenance is 1-indexed in `ingest._extract_page_texts()`, but persisted pages are 0-indexed. Store extraction `source_page` as 0-indexed and document the UI display conversion.
- **Boolean-only review state** — `needs_review` is not enough to represent pending, human-reviewed, or abstained fields. Add an enum/string state while keeping the boolean as a dashboard/filter convenience.
- **Per-field-only persistence** — field rows are good for evidence/audit, but S04 needs a row-oriented dashboard query. Add a document-level summary table or view now.
- **Self-reported LLM confidence** — S02 should model confidence as numeric evidence supplied by later pipeline stages, not ask the LLM to claim confidence in prose.

## Open Risks

- The best final table name is not established. Existing code already has `extractions`; legacy research used `extracted_fields` and `compliance_documents`. Pick names that minimize churn, and document the choice in tests/docstrings.
- Bounding-box shape from Docling/VLM extraction is not yet proven for these PDFs. Make bbox optional JSON now and require page-level evidence as the baseline.
- Date-field age/risk computation belongs in S03/S04, but table columns for `risk_level`/`age_days` should be nullable now to avoid another dashboard-facing migration immediately after S02.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Observability / tracing | Installed `observability` skill available in system prompt | Relevant for keeping extraction persistence trace metadata non-fatal and agent-debuggable; not invoked because S02 is research-only. |
| Pydantic | `bobmatnyc/claude-mpm-skills@pydantic` (`npx skills add bobmatnyc/claude-mpm-skills@pydantic`) | Available; promising for S03 structured-output work, not necessary to install for this small contract slice. |
| SQLite | `martinholovsky/claude-skills-generator@sqlite database expert` (`npx skills add martinholovsky/claude-skills-generator@sqlite-database-expert`) | Available; potentially useful if schema migration logic grows beyond lightweight `ALTER TABLE` checks. |

## Sources

- Existing code inventory and schema inspection: `src/db/schema.py`, `src/db/queries.py`, `src/pipeline/ingest.py`, `src/pipeline/db_writer.py`, `src/config.py`, `src/tracing.py`, and current tests.
- Legacy architecture notes: `.planning/research/ARCHITECTURE.md` expects field extraction with per-field confidence/evidence, document age risk rules, and a compliance document row for dashboard consumption.
- Legacy requirement notes: `.planning/REQUIREMENTS.md` defines the six required fields and page/span evidence expectations that became R002/R003/R004.
