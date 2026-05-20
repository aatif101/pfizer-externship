---
id: S02
parent: M001
milestone: M001
provides:
  - Typed extraction models for S03 real extraction pipeline integration.
  - SQLite schema and repository helpers for S03 to persist extracted metadata.
  - Dashboard-ready compliance listing shape for S04 Streamlit rendering.
requires:
  - slice: S01
    provides: Python 3.11 virtual environment path and clean migrated repository state.
  - slice: Phase 1 ingestion foundation
    provides: Existing `documents` and `pages` table conventions, including document IDs and page references.
affects:
  - S03
  - S04
key_files:
  - src/extraction/__init__.py
  - src/extraction/models.py
  - src/extraction/repository.py
  - src/db/schema.py
  - tests/test_extraction_models.py
  - tests/test_extraction_schema.py
  - tests/test_extraction_persistence.py
  - tests/test_db.py
key_decisions:
  - Model required SDF fields as a closed enum and require extraction records to include exactly the six Phase 2 fields.
  - Require non-abstained fields to include source evidence while permitting abstained fields to omit spans when an explicit abstention reason is present.
  - Use migration-safe nullable SQLite columns and a separate document-level `compliance_records` table to prepare dashboard consumption.
  - Use SQLite foreign-key enforcement at the repository boundary for missing documents.
  - Use deterministic compliance listing order by non-null expiry date, expiry date ascending, vendor name, then doc_id.
  - Use expiry-date evidence as document-level source context when available, otherwise fall back to the first non-abstained field.
patterns_established:
  - Strict Pydantic validation is the boundary before extraction records are persisted.
  - Extraction persistence uses idempotent upserts for both field-level rows and document-level compliance summaries.
  - SQLite writes use parameterized queries, including for untrusted vendor/source strings.
  - Dashboard-facing data should be exposed through repository list helpers rather than raw SQL in UI code.
observability_surfaces:
  - Extraction and compliance persistence carry `trace_id`/run metadata fields for future Langfuse/runtime correlation.
  - Field-level rows preserve confidence, review state, needs-review, abstention reason, source page, bbox JSON, and verbatim evidence for audit/debugging.
drill_down_paths:
  - .gsd/milestones/M001/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S02/tasks/T02-SUMMARY.md
  - .gsd/milestones/M001/slices/S02/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-05-19T22:49:44.422Z
blocker_discovered: false
---

# S02: Extraction contract and persistence

**Established a strict typed SDF extraction contract plus SQLite persistence and dashboard-ready compliance records for deterministic sample extraction records.**

## What Happened

S02 delivered the Phase 2 extraction foundation on top of the Phase 1 document/page store. T01 introduced `src/extraction/models.py` with strict Pydantic v2 models for the six required SDF fields, source evidence, confidence, review state, needs-review state, and abstention handling. T02 evolved the SQLite schema with extraction review metadata, nullable compliance/dashboard placeholders, `compliance_records`, and indexes for document/review/risk access paths while preserving migration compatibility. T03 added repository helpers that idempotently persist and retrieve validated `SDFExtractionRecord` instances, write exactly six field-level extraction rows per document record, maintain one document-level compliance record, preserve SQL metacharacters safely through parameterized queries, and provide deterministic compliance listing for the later Streamlit dashboard slice. Closeout verification found that the originally planned `./venv/Scripts/python.exe` command form is not accepted by this Windows shell, so the same project venv was verified with `venv/Scripts/python.exe`.

## Verification

Closeout verification was run through `gsd_exec` using the project Python 3.11 virtual environment. `venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_schema.py tests/test_extraction_persistence.py -q` passed as part of the combined closeout command, covering 21 targeted extraction contract/schema/persistence tests. `venv/Scripts/python.exe -m pytest -q` passed with 36 tests and 19 third-party deprecation warnings in 94.23s. No Langfuse credentials or external API/network calls were required. Persistence tests cover malformed model rejection before persistence, SQLite FK rejection for nonexistent documents, idempotent upserts, SQL metacharacter round-trips, abstention storage, review flags, aggregate compliance fields, and deterministic dashboard listing.

## Requirements Advanced

- R002 — Typed models and repository tests now represent/persist the six required SDF fields with source spans, source page evidence, confidence, review state, and abstentions for deterministic sample records.
- R003 — Compliance record schema includes nullable risk/review fields and document-level summaries needed for later threshold computation.
- R004 — Repository exposes dashboard-ready compliance rows with deterministic ordering, confidence/source metadata, and document-level field summaries.
- R008 — Extraction persistence carries trace/run metadata and remains non-fatal without Langfuse credentials.

## Requirements Validated

None.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

The planned verification command used `./venv/Scripts/python.exe`, but the Windows shell in this environment rejects the leading `./`. Verification used the same project virtual environment via `venv/Scripts/python.exe`, which passed. No source-code scope deviation.

## Known Limitations

S02 stores contract and persistence foundations only. It does not run real PDF/VLM extraction, compute final compliance risk thresholds, render Streamlit dashboard rows, or emit extraction runtime traces.

## Follow-ups

S03 should wire real extractor calls into `SDFExtractionRecord` and repository helpers, compute/abstain source-grounded metadata from PDFs, and populate compliance/risk values. S04 should render `compliance_records` in Streamlit with risk coloring, confidence, and source-page links.

## Files Created/Modified

- `src/extraction/__init__.py` — Exports extraction model/repository surface for Phase 2 use.
- `src/extraction/models.py` — Defines strict Pydantic v2 SDF extraction field, evidence, confidence, review, and abstention models.
- `src/extraction/repository.py` — Adds idempotent SQLite persistence, retrieval, and compliance listing helpers.
- `src/db/schema.py` — Adds extraction review columns, compliance_records schema, and indexes.
- `tests/test_extraction_models.py` — Covers extraction contract validation and negative cases.
- `tests/test_extraction_schema.py` — Covers schema evolution for extraction/compliance tables.
- `tests/test_extraction_persistence.py` — Covers repository persistence, idempotency, FK failures, abstentions, SQL metacharacters, and compliance listing.
- `tests/test_db.py` — Updates database schema regression coverage.
