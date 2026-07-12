---
phase: "01-foundation-ingestion"
status: passed
verified: 2026-07-12
requirements:
  - INGEST-01
  - INGEST-02
---

# Phase 1 Verification

## Requirement evidence

| Requirement | Evidence | Result |
|---|---|---|
| INGEST-01 | Real Docling conversion in `tests/test_s05_end_to_end_proof.py`; content-identity, migration, CLI skip/force, atomic rollback, and direct-call tests in `tests/test_ingest.py` and `tests/test_db.py` | Passed |
| INGEST-02 | Real 150-DPI rasterization plus exact one-image-per-page persistence in `tests/test_rasterizer.py`, `tests/test_ingest.py`, and the S05 end-to-end proof | Passed |

## Invariants proven

- Identical content is detected across paths without loading the VLM.
- Pending, errored, empty, partial, or non-contiguous snapshots are never skipped.
- Legacy path IDs migrate without primary-key rewrites.
- New and replacement writes roll back atomically, including derived OCR rows.
- Sparse page provenance never borrows text from an adjacent page.
- Changed bytes cannot commit under a stale content identity.
- Born-digital date/name text is preserved exactly; scanned pages retain VLM text.
- No raw content, absolute path, serialized document, image bytes, content hash,
  or raw exception string enters ingestion/storage traces or CLI/log failures.
- The process-scoped Docling converter is constructed once and uses the supported
  named Granite preset seam.

## Commands

```text
venv\Scripts\python.exe -m pytest tests\test_converter.py tests\test_ingest.py tests\test_s05_end_to_end_proof.py -q --tb=short
34 passed

venv\Scripts\python.exe -m pytest tests\test_db.py tests\test_rasterizer.py tests\test_extraction_pipeline.py -q --tb=short
25 passed

venv\Scripts\python.exe -m pytest tests -q --tb=short
423 passed, 8 skipped
```

Verdict: Phase 1 satisfies INGEST-01 and INGEST-02 and is ready for Phase 2.
