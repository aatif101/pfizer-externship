# M001: Phase 2 Extraction and Compliance

**Gathered:** 2026-05-19
**Status:** Ready for planning

## Project Description

The Pfizer SDF Intelligence System is an end-to-end AI-powered pharmaceutical document intelligence and compliance demo. It ingests folders of supplier documentation PDFs, including certificates of analysis, vendor certificates, and compliance forms that may be scanned or stamped, and turns them into auditable compliance records. M001 is the Phase 2 milestone that moves the existing Phase 1 ingestion foundation from stored documents/pages into structured extraction, conservative compliance risk calculation, and an evaluator-facing Streamlit Compliance tab.

## Why This Milestone

Phase 1 proved that the system can ingest PDFs into SQLite with Docling-derived text and page thumbnails. That is not yet useful to a compliance officer until the system can extract the SDF fields that matter, decide which documents are stale or risky, and present those results in the dashboard. M001 exists to deliver that first real compliance loop: a folder of supplier PDFs becomes structured, source-backed metadata and green/amber/red risk rows the user can inspect.

This needs to happen now because later retrieval/RAG work depends on trusted document metadata, source page references, and a working compliance record layer. Without M001, the chatbot and evaluation milestones would be built on unvalidated document facts.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run ingestion and extraction on at least one realistic SDF-style PDF and have the system persist document type, vendor name, manufacturing date, effective date, revision date, expiry date, confidence/review state, source page, and verbatim source span for extracted fields.
- Open the Streamlit Compliance tab and see SQLite-backed compliance rows with extracted metadata, conservative green/amber/red risk, confidence/review flags, and source-page/source-span evidence rather than a placeholder.

### Entry point / environment

- Entry point: Python CLI/workflow for ingestion plus Phase 2 extraction, and `streamlit run src/app.py` for the Compliance tab.
- Environment: local development on the Python 3.11 project virtual environment.
- Live dependencies involved: SQLite database; Gemini API for live extraction; Langfuse tracing when credentials are present; no auth or production service dependency.

## Completion Class

- Contract complete means: Pydantic models and SQLite schema/repository tests prove the six required SDF fields, source evidence, confidence, review/abstention state, and dashboard-ready compliance record shape.
- Integration complete means: a realistic SDF-style PDF can flow through ingestion, Gemini-primary extraction, persistence, risk calculation, and Streamlit display with page-plus-span evidence or explicit abstentions.
- Operational complete means: missing VLM/Langfuse credentials, malformed extraction output, missing fields, ambiguous dates, low confidence, and SQLite FK/validation failures are handled explicitly without crashing unrelated app surfaces.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A realistic SDF-style PDF can be ingested, extracted, risk-scored, persisted, and displayed in the Compliance tab as a document-level row with field-level evidence.
- Low-confidence or missing fields are not silently hidden or treated as valid; they are persisted with `needs_review`/`abstained` state and shown to the user as uncertain.
- The milestone cannot be considered truly done if it only uses synthetic Pydantic records; automated tests may mock Gemini for stability, but there must be at least one realistic PDF end-to-end proof of the full workflow.

## Architectural Decisions

### Gemini-Primary Extraction

**Decision:** Use Gemini as the primary VLM extraction provider for M001.

**Rationale:** Gemini 2.5 Flash is the stack recommendation for bulk extraction because it is vision-capable, supports structured outputs, and is materially cheaper than Claude for folder-scale document processing. Claude can remain a later critic or fallback path, but M001 should not expand scope into a dual-provider orchestration problem unless execution discovers a hard blocker.

**Alternatives Considered:**
- Provider-neutral Gemini/Claude adapter now — useful later, but adds scope before the baseline compliance loop is proven.
- No live VLM in M001 — lower flake risk, but would fail to prove the core Phase 2 extraction promise.

### Page and Span Evidence Standard

**Decision:** Require source page and verbatim span for every non-abstained extracted field; bounding boxes remain optional in M001.

**Rationale:** Page-plus-span evidence gives compliance reviewers an auditable reason to trust a field without blocking Phase 2 on unproven bounding-box extraction across scanned and stamped PDFs. Bounding boxes can be added when visual retrieval/citation surfaces mature.

**Alternatives Considered:**
- Page-only evidence — easier for scanned documents but too weak for a compliance trust story.
- Page, span, and bounding box required — strongest audit trail, but high implementation risk because bbox shape is not yet proven for these documents.

### Conservative Compliance Date Basis

**Decision:** Use the most conservative date interpretation for risk: expired documents are red; otherwise compute age from the oldest relevant lifecycle date, and flag missing or ambiguous dates for review.

**Rationale:** Pharmaceutical compliance should avoid under-flagging stale supplier documentation. When manufacturing, effective, revision, and expiry dates disagree, the safest demo behavior is to surface risk or uncertainty rather than silently mark a document green.

**Alternatives Considered:**
- Revision/effective-date freshness only — matches document-version freshness, but may under-flag older manufacturing or stale supplier materials.
- Expiry-first only — intuitive for certificates, but may miss stale SDF revisions that are not explicitly expired.

### Flag-and-Show Review Policy

**Decision:** Persist and display low-confidence or missing fields with clear `needs_review` or `abstained` state instead of hiding them or failing the whole document.

**Rationale:** Compliance officers need to see which documents require attention. Hiding uncertain rows makes the dashboard look cleaner but reduces trust, while failing whole documents makes realistic scanned/stamped PDFs brittle for demo use.

**Alternatives Considered:**
- Hide uncertain fields until reviewer approval — safer visually, but obscures why a document is incomplete.
- Fail the entire document on any missing field — strict, but poor user experience and unrealistic for noisy PDF extraction.

---

> See `.gsd/DECISIONS.md` for the full append-only register of all project decisions.

## Error Handling Strategy

M001 should treat extraction as a validation-and-review pipeline rather than an all-or-nothing parser.

- Malformed Gemini responses must fail Pydantic validation before persistence and produce an explicit extraction error/review state.
- Fields without trustworthy value plus source page and verbatim span must be stored as abstained or needs-review, not shown as valid facts.
- Low confidence should not remove a document from the dashboard; it should set `needs_review` and make uncertainty visible.
- Date parsing failures or conflicting dates should produce review state and conservative risk messaging rather than defaulting to green.
- SQLite writes must remain parameterized, idempotent where appropriate, and FK-protected against nonexistent documents/pages.
- Missing Gemini credentials should block live extraction with a clear user-facing message but should not break model tests, persistence tests, ingestion, or Streamlit startup.
- Missing Langfuse credentials must remain non-fatal; traces should enrich debugging when configured but never become a runtime dependency.
- Do not log full page text, provider tokens, or secret-bearing settings. Persist verbatim spans only as explicit field evidence.

## Risks and Unknowns

- Gemini output reliability on real SDF-style PDFs — this determines how much retry/repair logic S03 needs.
- Realistic sample PDF availability — final acceptance needs at least one realistic SDF-style PDF, not only synthetic records.
- Date semantics across document types — manufacturing, effective, revision, and expiry dates may mean different things by form; conservative rules reduce but do not eliminate ambiguity.
- Source span extraction from scanned/stamped PDFs — page-level evidence should be reliable, but verbatim spans may be noisy when OCR/layout conversion is imperfect.
- Existing database evolution — Phase 1 databases may need migration-safe column/table creation because `CREATE TABLE IF NOT EXISTS` will not alter existing tables.
- Dashboard source links — S04 must decide the exact UX for page links/previews using existing page blobs or derived page references.

## Existing Codebase / Prior Art

- `src/pipeline/ingest.py` — Existing Typer ingestion flow; writes documents and 0-indexed pages after Docling conversion and rasterization.
- `src/pipeline/converter.py` — Existing Docling conversion wrapper; S01 noted Docling VLM API deprecation should be revisited before heavy extraction work.
- `src/pipeline/rasterizer.py` — Existing pypdfium2 150 DPI page rasterization for page thumbnails/source-page preview surfaces.
- `src/db/schema.py` — Current SQLite DDL for `documents`, `pages`, `extractions`, and `evaluations`; needs migration-safe evolution for review state and compliance records.
- `src/db/queries.py` — Existing parameterized query helpers; should remain the persistence boundary or be wrapped by a small extraction repository.
- `src/app.py` — Streamlit shell with a placeholder Compliance tab that M001 must replace with SQLite-backed records.
- `src/tracing.py` — Langfuse v3 tracing helper that is intentionally non-fatal when credentials are absent.
- `.gsd/milestones/M001/slices/S02/S02-RESEARCH.md` — Prior research recommends `src/extraction/` Pydantic models, field-level evidence rows, and a document-level `compliance_records` table.
- `.gsd/milestones/M001/slices/S01/S01-SUMMARY.md` — Confirms Python 3.11 venv, local-secret hygiene, current GSD artifacts, and passing test baseline.

## Relevant Requirements

- R001 — Provides the validated ingestion foundation that M001 consumes.
- R002 — M001 directly implements structured SDF metadata extraction with source spans and source page references.
- R003 — M001 computes green/amber/red compliance risk from conservative document age/date interpretation and stores the result.
- R004 — M001 surfaces extracted compliance records in Streamlit with risk coloring, confidence/review state, and source links/evidence.
- R008 — M001 should trace extraction/persistence stages when Langfuse is configured while remaining safe without credentials.
- R009 — All development and verification commands must use the Python 3.11 project virtual environment.
- R010 — Provider tokens and local settings must stay out of Git and logs.

## Scope

### In Scope

- Pydantic extraction contract for required SDF fields, source evidence, confidence, review state, abstention, and normalized values.
- SQLite schema/repository evolution for field-level evidence and dashboard-ready document-level compliance records.
- Gemini-primary baseline extraction pipeline that produces validated records from realistic SDF-style PDFs.
- Conservative compliance risk calculation with green/amber/red thresholds and explicit uncertain/review states.
- Streamlit Compliance tab backed by SQLite records, including risk display, confidence/review indicators, and source page/span visibility.
- Tests for model validation, schema migration, repository round-trips, risk boundaries, SQL metacharacter safety, and dashboard data access/rendering behavior.
- One realistic end-to-end proof through ingestion, extraction, risk scoring, persistence, and dashboard display.

### Out of Scope / Non-Goals

- Hybrid retrieval, RAG chatbot, and natural-language Q&A; those belong to M002.
- ColQwen visual retrieval and Qdrant multivector indexing; those belong to later retrieval work.
- RAGAS/eval benchmark reporting beyond tests needed to prove extraction/risk/dashboard behavior; broader evaluation belongs to M003.
- Authentication, multi-user access control, and production deployment.
- Fine-tuning models or self-hosting an LLM/VLM.
- Making bounding-box evidence mandatory in M001.
- Building a full human-in-the-loop review queue; M001 only needs clear review/abstention state and dashboard visibility.

## Technical Constraints

- Use `./venv/Scripts/python.exe` for installs, tests, and verification; global Python 3.14 is unsupported for this project.
- Keep local provider tokens and settings ignored/untracked; never log secrets.
- Use Pydantic v2 models for extraction validation and structured-output compatibility.
- Use SQLite as the local persistence layer and preserve parameterized SQL patterns.
- Persist page references using the existing database convention: `pages.page_num` is 0-indexed; UI may display 1-indexed page numbers.
- Keep Langfuse v3 behavior non-fatal when credentials are missing.
- Avoid relying on `CREATE TABLE IF NOT EXISTS` alone for schema evolution of existing Phase 1 databases.
- Automated tests should not require live Gemini credentials; live extraction can be proved via a controlled smoke/demo path.

## Integration Points

- Docling conversion — supplies page text/layout content that Gemini extraction and source-span validation can use.
- pypdfium2/page blobs — support page thumbnail/source preview surfaces for the Compliance tab.
- SQLite — stores documents, pages, field-level extractions, document-level compliance records, and later evaluation rows.
- Gemini API — primary live VLM extraction provider for Phase 2.
- Langfuse — optional tracing/observability for extraction and persistence operations.
- Streamlit — user-facing Compliance tab for displaying extracted records and compliance risk.
- Typer/Python CLI — local workflow entry point for folder ingestion and extraction commands.

## Testing Requirements

Use the Python 3.11 project virtual environment for all verification.

Required test coverage:

- Unit tests for extraction models: required field enum, confidence range, non-negative page numbers, source evidence requirements, abstention rules, normalized value/date behavior, and rejection of unknown fields.
- SQLite/schema tests: fresh DB creation, Phase 1-shaped DB migration, FK behavior, new review/abstention columns, `compliance_records` table, indexes/unique constraints, and parameterized handling of SQL-like vendor/span values.
- Repository tests: idempotent upsert of sample extraction records, field-level evidence round-trip, document-level compliance row round-trip, trace/review metadata persistence, and nonexistent `doc_id` failure.
- Risk tests: green under 2 years, amber at 2-3 years, red over 3 years, expired documents red, missing/ambiguous dates needs-review, and conservative oldest-date selection.
- Pipeline tests: mocked Gemini response is validated, malformed response becomes explicit failure/review state, missing credentials produce a clear non-crashing error path, and no secret/page-text leakage in logs.
- Streamlit/dashboard tests: Compliance tab imports/starts headlessly, dashboard query renders records from SQLite, risk colors/states are represented, and uncertain fields are visible rather than hidden.
- Integrated proof: one realistic SDF-style PDF runs through ingestion, extraction, risk calculation, persistence, and dashboard display. Live VLM calls may be excluded from routine CI but must be verified for milestone completion.

Suggested commands include:

```bash
./venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_schema.py tests/test_extraction_persistence.py -q
./venv/Scripts/python.exe -m pytest -q
```

Additional slice-specific tests should be added for extraction pipeline, risk calculation, and Streamlit dashboard rendering as those slices are planned/executed.

## Acceptance Criteria

### S02: Extraction contract and persistence

- Typed extraction models represent doc type, vendor name, manufacturing date, effective date, revision date, expiry date, confidence, review state, abstention, source page, and verbatim source span.
- The existing `extractions` field-level table is extended migration-safely for normalized values, review state, abstention reason, and trace metadata.
- A dashboard-ready document-level compliance record table exists and can be populated from a sample extraction record.
- Sample records round-trip through SQLite idempotently and safely, including values with SQL metacharacters.

### S03: Baseline extraction pipeline

- A Gemini-primary extraction path can transform realistic SDF-style PDF/page content into the typed extraction contract.
- The pipeline stores source-backed fields or explicit abstentions; it does not invent values when evidence is missing.
- Malformed VLM output, missing credentials, and low-confidence fields produce explicit non-crashing failure/review states.
- Compliance risk is computed with the conservative date policy and persisted with the record.

### S04: Compliance dashboard records

- The Streamlit Compliance tab displays real SQLite compliance records instead of placeholder text.
- Rows include document metadata, dates, risk level/color, confidence/review state, and source page/span evidence.
- Low-confidence or missing fields are visible as needs-review/abstained rather than hidden.
- A realistic PDF end-to-end scenario can be demonstrated from ingestion/extraction through dashboard display.

## Open Questions

- Which exact realistic SDF-style PDF(s) will serve as the final integrated proof fixture — current thinking is to choose at least one representative multi-page supplier/compliance document during execution.
- Whether the first live extraction implementation should read page text only, page images only, or both — current thinking is Gemini-primary with enough page context to preserve source-span evidence, while keeping automated tests provider-mocked.
- How source page links should be rendered in Streamlit — current thinking is to start with page number/source span visibility and use existing page blobs for previews if practical.
- What confidence threshold should mark `needs_review` — current thinking is to introduce a configurable default, likely around the S02 research suggestion of 0.75, and test boundary behavior.
