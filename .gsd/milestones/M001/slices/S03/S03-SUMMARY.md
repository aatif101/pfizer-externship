---
id: S03
parent: M001
milestone: M001
provides:
  - Baseline SDF extraction pipeline persisting six-field extraction records and compliance rows.
  - Offline-safe fake and Gemini provider seams with typed sanitized failures.
  - Extraction CLI entrypoints for one-document and batch extraction.
requires:
  - slice: S02
    provides: Ingested documents/pages and extraction model/repository contract.
affects:
  - S04 can render compliance dashboard rows populated by the extraction pipeline.
key_files:
  - src/extraction/models.py
  - src/extraction/repository.py
  - src/extraction/risk.py
  - src/db/queries.py
  - src/extraction/providers.py
  - src/extraction/pipeline.py
  - src/extraction/gemini.py
  - src/extraction/cli.py
  - src/config.py
  - tests/test_extraction_risk.py
  - tests/test_extraction_persistence.py
  - tests/test_extraction_pipeline.py
  - tests/test_extraction_provider_gemini.py
  - tests/test_extraction_cli.py
key_decisions:
  - Use calendar-year anniversary cutoffs for 2-year and 3-year SDF risk thresholds while persisting actual elapsed age_days.
  - Validate and ground untrusted provider facts in the pipeline behind a dependency-free provider protocol.
  - Lazy Gemini provider construction keeps default imports and tests credential-free while live mode fails with typed configuration errors.
  - Default CLI provider construction is lazy Gemini with a monkeypatchable provider seam for offline CLI tests.
patterns_established:
  - Provider DTOs are untrusted and validated for field names, pages, source spans, confidence, and abstentions before persistence.
  - Malformed provider output becomes deterministic six-field abstentions rather than raw-response leakage or crashes.
  - Operator diagnostics include identifiers and typed reason classes, not secrets or document content.
observability_surfaces:
  - Extraction diagnostics expose run_id, trace_id, provider_name, document_id, page_count, review states, and abstention reasons.
  - CLI output reports per-document success/failure counts and sanitized provider/config errors.
  - SQLite extraction_fields and compliance_records persist dashboard-ready extraction and risk metadata.
drill_down_paths:
  - .gsd/milestones/M001/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S03/tasks/T02-SUMMARY.md
  - .gsd/milestones/M001/slices/S03/tasks/T03-SUMMARY.md
  - .gsd/milestones/M001/slices/S03/tasks/T04-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-05-20T17:40:56.149Z
blocker_discovered: false
---

# S03: Baseline extraction pipeline

**Delivered the offline-verifiable baseline SDF extraction pipeline with risk persistence, provider seams, deterministic failure handling, and CLI entrypoints.**

## What Happened

S03 connects ingested document pages to strict six-field SDF extraction records and dashboard-ready compliance rows. T01 added conservative risk metadata and SQLite round-trip coverage. T02 introduced the provider protocol, fake-provider integration path, page loading, source-span grounding, abstentions, run/trace metadata, and persistence. T03 added a lazy Gemini provider with non-required configuration, bounded retries, typed sanitized provider/config failures, malformed-output abstentions, low-confidence review handling, and mocked offline tests. T04 wired Typer extract and extract-all commands through the real pipeline with safe diagnostics and deterministic failure behavior.

## Verification

Full project regression passed after task-summary recovery: `venv/Scripts/python.exe -m pytest -q` returned 65 passed with 19 existing third-party deprecation warnings. Targeted checks also covered app import, pipeline behavior, Gemini provider failure paths, and CLI persistence paths. Extraction runs expose run IDs, optional trace IDs, document IDs, page counts, provider/error classes, review/abstention states, and persisted compliance rows without surfacing API keys, full page text, raw provider responses, or image blobs.

## Requirements Advanced

- R002 — Strict six-field extraction records are produced with evidence, confidence, review state, and abstention handling.
- R003 — Compliance rows are populated with conservative risk status, reason, age_days, run metadata, and source evidence.
- R004 — Source-page/span grounding is enforced before provider facts are trusted.
- R008 — Provider/CLI failure modes are typed, deterministic, observable, and safe without optional credentials.

## Requirements Validated

- R002 — Provider/pipeline tests assert exactly six fields and malformed-output abstentions.
- R003 — Persistence and CLI tests assert compliance_records rows are written from pipeline execution.
- R004 — Span mismatch tests abstain ungrounded provider facts.
- R008 — Missing credential, retryable provider failure, unknown doc, no-doc, and provider failure tests assert safe deterministic behavior.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

Full regression passed offline without Gemini or Langfuse credentials. Live Gemini extraction remains opt-in and requires GEMINI_API_KEY. Batch extraction is sequential, so Gemini quota/cost is the first scaling breakpoint.

## Deviations

Added `venv.bat` during T04 to make the automated Windows verification gate execute the required forward-slash venv/Scripts/python.exe path through cmd.exe.

## Known Limitations

Full regression emits existing third-party deprecation warnings from installed dependencies. Streamlit compliance rendering and source-page UI links remain deferred to S04.

## Follow-ups

Proceed to S04 to render persisted compliance rows in the dashboard and source-page UI.

## Files Created/Modified

- `src/extraction/models.py` — S03 extraction pipeline implementation or verification support.
- `src/extraction/repository.py` — S03 extraction pipeline implementation or verification support.
- `src/extraction/risk.py` — S03 extraction pipeline implementation or verification support.
- `src/db/queries.py` — S03 extraction pipeline implementation or verification support.
- `src/extraction/providers.py` — S03 extraction pipeline implementation or verification support.
- `src/extraction/pipeline.py` — S03 extraction pipeline implementation or verification support.
- `src/extraction/gemini.py` — S03 extraction pipeline implementation or verification support.
- `src/extraction/cli.py` — S03 extraction pipeline implementation or verification support.
- `src/config.py` — S03 extraction pipeline implementation or verification support.
- `tests/test_extraction_risk.py` — S03 extraction pipeline implementation or verification support.
- `tests/test_extraction_persistence.py` — S03 extraction pipeline implementation or verification support.
- `tests/test_extraction_pipeline.py` — S03 extraction pipeline implementation or verification support.
- `tests/test_extraction_provider_gemini.py` — S03 extraction pipeline implementation or verification support.
- `tests/test_extraction_cli.py` — S03 extraction pipeline implementation or verification support.
- `venv.bat` — S03 extraction pipeline implementation or verification support.
