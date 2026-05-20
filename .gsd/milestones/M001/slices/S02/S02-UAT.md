# S02: Extraction contract and persistence — UAT

**Milestone:** M001
**Written:** 2026-05-19T22:49:44.423Z

## UAT: S02 Extraction Contract and Persistence

**UAT Type:** Automated developer UAT using temporary SQLite databases and deterministic sample extraction records.

### Preconditions

1. Work from the project root on the Python 3.11 virtual environment.
2. No Gemini, Claude, or Langfuse credentials are required.
3. A temporary SQLite database can be initialized with the project schema.

### Steps

1. Create or initialize a test SQLite database with the existing Phase 1 `documents` and `pages` tables plus the S02 extraction/compliance schema.
2. Insert one document and at least one page row using the established Phase 1 document/page conventions.
3. Construct a valid `SDFExtractionRecord` containing exactly these six required fields: document type, vendor, manufacturing date, effective date, revision date, and expiry date.
4. Include field-level source evidence with source page references, source spans, confidence scores, normalized values, review state, and needs-review flags.
5. Include at least one abstained field with an explicit abstention reason.
6. Persist the record through the extraction repository.
7. Fetch the record back and compare field values, normalized values, evidence, confidence, review state, trace/run metadata, and abstention details.
8. Persist the same record again with changed values and verify the repository updates idempotently rather than duplicating rows.
9. List dashboard-ready compliance records and verify the row includes document-level field summaries, risk/review placeholders, confidence/source metadata, and deterministic ordering.
10. Attempt negative cases: unknown field names, invalid confidence, negative page numbers, malformed bounding boxes, missing non-abstained values, missing abstention reasons, nonexistent `doc_id`, and SQL-like vendor/source strings.

### Expected Outcomes

- The valid sample record is accepted by Pydantic validation.
- Invalid records fail before persistence.
- Exactly six field-level extraction rows are stored for the sample record.
- One document-level `compliance_records` row is upserted for the document.
- Fetching the record reconstructs the typed model with evidence, confidence, review, and abstention details intact.
- Repeated persistence is idempotent and updates existing rows.
- Missing parent documents fail via SQLite foreign-key enforcement.
- SQL metacharacter strings round-trip as data and do not alter query behavior.
- Compliance listing returns dashboard-ready rows for S04.

### Edge Cases Covered

- Unknown fields are rejected.
- Confidence outside `[0, 1]` is rejected.
- Negative source page numbers are rejected.
- Invalid bounding boxes are rejected.
- Non-abstained fields without values/source spans are rejected.
- Abstentions without reasons are rejected.
- Missing `doc_id` parents fail FK checks.
- Malicious-looking vendor/source text persists safely as literal text.

### Not Proven By This UAT

- Real VLM/Gemini/Claude extraction from PDFs is not proven; that is S03.
- Compliance risk threshold calculation is only prepared by nullable columns/placeholders; threshold behavior belongs to S03/S04.
- Streamlit rendering, risk coloring, and source-page links are not proven; that is S04.
- Langfuse tracing integration for extraction runtime is not exercised beyond confirming credentials are not required for this persistence slice.
