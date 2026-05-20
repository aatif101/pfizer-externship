---
estimated_steps: 20
estimated_files: 1
skills_used: []
---

# T01: Add realistic offline end to end proof test

---
estimated_steps: 8
estimated_files: 1
skills_used:
  - tdd
  - verify-before-complete
---

Why: The validation blocker is lack of durable proof that a realistic PDF can traverse ingestion, extraction, compliance persistence, and dashboard formatting together. Existing tests prove those seams separately, and `tests/fixtures/sample.pdf` is unsuitable because it persists empty page text.

Do:
1. Add `tests/test_s05_end_to_end_proof.py` with a deterministic raw-PDF generator or in-test fixture that requires no new dependencies and writes a one-page SDF-style PDF under pytest's temporary directory.
2. Include these exact visible spans in the PDF: `Supplier Declaration Form`, `Vendor Name: Acme Pharma Ltd.`, `Manufacturing Date: 2024-01-05`, `Effective Date: 2024-02-01`, `Revision Date: 2024-03-15`, and `Expiry Date: 2027-01-31`.
3. Initialize a temporary SQLite DB through the existing schema helper, run `ingest_document()`, and assert one page, one image, non-empty persisted page text, and presence of all required spans.
4. Implement a fake `SDFExtractionProvider` in the test that cites the actual ingested `doc_id`, page 0, and exact spans; do not call Gemini or require credentials.
5. Run `extract_document(db_path, doc_id, provider, today=date(2026, 1, 6), run_id=...)` and verify six field rows, one compliance row, risk `amber`, `age_days == 732`, source page 0, `source_verbatim_span == "2027-01-31"`, and populated run/trace metadata.
6. Verify `format_compliance_rows()` exposes evaluator-facing values including vendor `Acme Pharma Ltd.`, `source_page_label == "Page 1"`, expiry source span, and `aggregate_confidence_display == "90%"`.
7. Keep assertions and failures sanitized: no full page text dumps, no provider raw JSON dumps, no secrets.

Failure Modes: Docling may emit warnings or be slow; the test should tolerate warnings but fail on empty page text, missing images, malformed provider output, bad source grounding, or missing SQLite rows. If the generated PDF stops parsing in Docling, the test should fail with a clear assertion that the grounded spans were not persisted.

Load Profile: Single temporary one-page PDF, one SQLite database, and one fake extraction run; performance is intentionally small but exercises the real heavy Docling path. At 10x load, Docling runtime would dominate, but S05 proof is not a bulk-ingestion benchmark.

Negative Tests: The proof implicitly guards the known bad fixture class by asserting non-empty page text and exact span grounding. Existing extraction tests continue covering missing page text, invalid spans, malformed provider payloads, and abstentions.

Done when: The new S05 test is committed in the test tree and passes by itself with the project Python 3.11 venv command.

## Inputs

- `src/pipeline/ingest.py`
- `src/extraction/pipeline.py`
- `src/extraction/providers.py`
- `src/extraction/repository.py`
- `src/dashboard/compliance.py`
- `src/db/schema.py`
- `src/db/queries.py`
- `tests/test_ingest.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_compliance_dashboard.py`

## Expected Output

- `tests/test_s05_end_to_end_proof.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py -q

## Observability Impact

Creates a repeatable proof surface for future agents: pytest failures localize whether ingestion text, provider grounding, repository persistence, risk computation, or dashboard formatting broke. The test verifies persisted run_id/trace_id metadata without requiring Langfuse.
