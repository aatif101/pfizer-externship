---
estimated_steps: 7
estimated_files: 4
skills_used: []
---

# T02: Harden ingestion and storage trace updates

Expected executor skills: observability, tdd, verify-before-complete.

Why: src/pipeline/ingest.py and src/pipeline/db_writer.py already have @observe spans but directly update Langfuse context, so a failed trace backend can crash ingestion and ad hoc metadata could drift into unsafe fields.

Do: Replace direct langfuse_context.update_current_trace calls in ingest_document and write_document_to_db with the shared helper from T01. Preserve existing @observe span names if possible. Allow only operational ingestion/storage keys: boundary, status, doc_id, filename, page_count, image_count, and error_class where applicable. Do not include file_path, resolved absolute path, page_text, image_blob, docling_json, Docling document JSON, raw exception messages, or content hashes. Add or update tests that monkeypatch the helper or fake context and exercise lightweight code paths without invoking real Docling conversion when possible; db_writer can be tested with simple SQLite fixtures. Ensure trace update failures do not change successful DB writes or ingestion return values.

Failure Modes (Q5): Langfuse unavailable or update failure must not alter ingestion/storage behavior. Invalid PDFs and oversized PDFs may still raise existing typed errors, but trace metadata must not include absolute paths or raw exception messages.

Load Profile (Q6): Ingestion can process many pages and image blobs; trace metadata must stay O(1) in size and never serialize page text, images, or Docling JSON.

Negative Tests (Q7): Fake context raising on update, inputs containing forbidden file_path/docling_json/page_text/image_blob keys, and storage writes with empty page text or missing image blobs.

Done when: ingestion and storage spans are no-op safe, metadata is allowlisted, and existing ingestion tests remain green.

## Inputs

- `src/tracing.py`
- `tests/test_tracing.py`
- `src/pipeline/ingest.py`
- `src/pipeline/db_writer.py`
- `tests/test_ingest.py`

## Expected Output

- `src/pipeline/ingest.py`
- `src/pipeline/db_writer.py`
- `tests/test_tracing.py`
- `tests/test_ingest.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_ingest.py

## Observability Impact

Makes existing ingestion and storage spans reliable operational signals instead of possible failure points, while documenting the redaction boundary in executable tests.
