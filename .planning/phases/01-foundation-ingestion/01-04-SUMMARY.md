---
phase: "01-foundation-ingestion"
plan: "04"
slug: ingestion-integrity-hardening
status: complete
completed: 2026-07-12
requirements:
  - INGEST-01
  - INGEST-02
---

# Phase 1 Plan 04 — Ingestion Integrity Hardening Summary

## Outcome

Ingestion is content-addressed, transaction-safe, literal-text preserving, and
privacy-bounded. Identical PDF bytes are skipped across renames and moves, while
direct API calls still perform explicit re-ingestion. A committed document now
represents one exact, complete page snapshot or no change at all.

## What changed

- Added an idempotent nullable `documents.content_sha256` migration and unique
  partial index. New documents use the full SHA-256 digest; existing 16-character
  path IDs remain stable and are backfilled only after a successful re-ingest.
- Added content-first lookup with status, declared page count, stored page count,
  and first/last page checks. A row is skippable only when pages are exactly the
  contiguous zero-based set declared by the document.
- Bound preflight identity to the bytes actually converted and rasterized. A
  caller-supplied stale identity or a PDF changed during processing is rejected
  before any document/page commit.
- Replaced multi-connection writes with one explicit SQLite transaction. Header,
  pages, PNGs, content identity, derived-OCR invalidation, and final status commit
  together; injected failures preserve the prior document/page/OCR snapshot.
- Removed adjacent-page fallback from sparse Docling provenance and enforced one
  PNG per declared page.
- Switched converter construction to the supported literal
  `VlmConvertOptions.from_preset("granite_docling")` path with a narrow older-2.x
  fallback and retained one process-cached converter.
- Preserved exact born-digital text through pypdfium2's embedded text layer while
  retaining Granite-Docling for document layout/JSON and image-only scanned-page
  transcription. This closed a real regression where the modern VLM engine
  omitted four dates from the end-to-end fixture.
- Reduced ingestion, storage, converter, rasterizer, and CLI output to basenames,
  counts, statuses, and exception classes. Full content-derived IDs are excluded
  from ingestion/storage trace allowlists.

## Verification evidence

- Focused real-Docling gate:
  `venv\Scripts\python.exe -m pytest tests\test_converter.py tests\test_ingest.py tests\test_s05_end_to_end_proof.py -q --tb=short`
  — **34 passed** in 87.13s.
- Focused schema/rasterizer/extraction compatibility gate:
  `venv\Scripts\python.exe -m pytest tests\test_db.py tests\test_rasterizer.py tests\test_extraction_pipeline.py -q --tb=short`
  — **25 passed** in 23.98s.
- Full offline Windows regression:
  `venv\Scripts\python.exe -m pytest tests -q --tb=short`
  — **423 passed, 8 skipped** in 117.20s.
- `git diff --check` — passed.

The eight skips are pre-existing explicit GPU/optional-integration skips. The 14
warnings are upstream Torch JIT deprecations and do not affect behavior.

## Deviations resolved during review

The first implementation passed mocked contracts but the supported Docling preset
lost literal dates on a real PDF fixture. Rather than reverting to a deprecated
model-spec API, ingestion now combines supported Granite layout/scanned-page
parsing with exact embedded text for born-digital pages. Independent review also
found and closed a hash time-of-check/time-of-use gap and failure-time leakage in
privacy-test assertions.

## Remaining scope

Phase 1 is complete. Model extraction quality, durable extraction-run lifecycle,
critic confidence, HITL, agentic RAG, and statistically defensible benchmarks are
owned by Phases 2 through 7.
