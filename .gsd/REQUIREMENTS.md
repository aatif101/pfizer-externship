# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R002 — Extract structured SDF metadata including document type, vendor, manufacturing date, effective date, revision date, and expiry date with source spans and source page references.
- Class: core-capability
- Status: active
- Description: Extract structured SDF metadata including document type, vendor, manufacturing date, effective date, revision date, and expiry date with source spans and source page references.
- Why it matters: Compliance officers need reliable structured fields to assess supplier document freshness and risk.
- Source: migration from GSD 1.0 EXTRACT-01
- Primary owning slice: M001
- Validation: Validated when extracted fields persist to SQLite for sample PDFs and include page-level/source-span evidence.
- Notes: Next primary implementation target after migration cleanup.

### R003 — Compute compliance risk levels from document age using green, amber, and red thresholds and store the result with extracted fields.
- Class: core-capability
- Status: active
- Description: Compute compliance risk levels from document age using green, amber, and red thresholds and store the result with extracted fields.
- Why it matters: The primary demo value is immediate identification of expired or at-risk supplier documentation.
- Source: migration from GSD 1.0 EXTRACT-02
- Primary owning slice: M001
- Validation: Validated when tests cover threshold boundaries and dashboard/query rows show expected risk levels.
- Notes: Thresholds retained from GSD 1.0: green under 2 years, amber 2 to 3 years, red over 3 years.

### R004 — Display extracted compliance records in Streamlit with sortable fields, risk coloring, confidence, and source page links.
- Class: primary-user-loop
- Status: active
- Description: Display extracted compliance records in Streamlit with sortable fields, risk coloring, confidence, and source page links.
- Why it matters: The dashboard is the evaluator-facing surface for the compliance workflow.
- Source: migration from GSD 1.0 DASH-01 and DASH-02
- Primary owning slice: M001
- Supporting slices: M003
- Validation: Validated when Streamlit renders ingested/extracted records from SQLite with correct risk colors and source links.
- Notes: Compliance tab currently exists as a skeleton and should be extended in M001/M003.

### R005 — Provide grounded natural-language Q&A over the document corpus with page-level citations and abstention on insufficient evidence.
- Class: core-capability
- Status: active
- Description: Provide grounded natural-language Q&A over the document corpus with page-level citations and abstention on insufficient evidence.
- Why it matters: The chatbot is the second primary user loop and must remain grounded for pharma compliance credibility.
- Source: migration from GSD 1.0 RETRIEVE and RAG requirements
- Primary owning slice: M002
- Validation: Validated when sample questions return cited answers and low-confidence queries abstain rather than hallucinate.
- Notes: Initial implementation should use hybrid text retrieval before later visual retrieval upgrades.

### R006 — Add visual page retrieval with ColQwen-style embeddings and Qdrant multivector reranking for layout-aware document search.
- Class: differentiator
- Status: active
- Description: Add visual page retrieval with ColQwen-style embeddings and Qdrant multivector reranking for layout-aware document search.
- Why it matters: Visual retrieval is the differentiated technical feature for scanned, stamped, and table-heavy pharmaceutical documents.
- Source: migration from GSD 1.0 VISUAL-01 and VISUAL-02
- Primary owning slice: M002
- Validation: Validated when visual retrieval improves or complements recall on scanned/table-heavy pages in the gold set.
- Notes: Deferred until baseline extraction/dashboard and text retrieval are stable; revisit exact model/checkpoint during implementation.

### R007 — Maintain an evaluation harness with extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost metrics.
- Class: quality-attribute
- Status: active
- Description: Maintain an evaluation harness with extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost metrics.
- Why it matters: The demo needs evidence, not just claims, especially for compliance-oriented AI.
- Source: migration from GSD 1.0 EVAL and BENCH requirements
- Primary owning slice: M003
- Validation: Validated when eval commands produce repeatable metric reports over a documented gold set.
- Notes: Gold set and benchmark reporting belong after baseline user loops are functioning.

### R008 — Trace ingestion, extraction, retrieval, generation, and evaluation operations with Langfuse while avoiding secret leakage.
- Class: operability
- Status: active
- Description: Trace ingestion, extraction, retrieval, generation, and evaluation operations with Langfuse while avoiding secret leakage.
- Why it matters: Observability is necessary for debugging and for auditability in a pharmaceutical document workflow.
- Source: migration from GSD 1.0 OBS-01 and readiness cleanup
- Primary owning slice: M001
- Supporting slices: M002,M003
- Validation: Validated when traces include useful phase/doc/page metadata and tests confirm missing Langfuse credentials do not crash the app.
- Notes: Langfuse v3 is currently pinned and working in Python 3.11; reassess v3 vs v4 before deep LangGraph integration.

### R009 — Use Python 3.11 project virtual environment for development and verification; do not rely on global Python 3.14.
- Class: constraint
- Status: active
- Description: Use Python 3.11 project virtual environment for development and verification; do not rely on global Python 3.14.
- Why it matters: The project dependency set is verified in Python 3.11 and fails under the current global Python 3.14 environment.
- Source: readiness cleanup 2026-05-19
- Primary owning slice: M001
- Validation: Validated when editable install and pytest pass through ./venv/Scripts/python.exe.
- Notes: Global Python 3.14 currently has incompatible Pydantic/pydantic-settings packages. Supported commands should use ./venv/Scripts/python.exe on Windows.

### R010 — Do not commit local provider tokens, API keys, or machine-specific model settings; keep local settings files ignored.
- Class: compliance/security
- Status: active
- Description: Do not commit local provider tokens, API keys, or machine-specific model settings; keep local settings files ignored.
- Why it matters: The repo previously contained token-like material; preventing recurrence is a non-negotiable security hygiene requirement.
- Source: readiness cleanup 2026-05-19
- Primary owning slice: M001
- Validation: Validated when git status shows settings.local.json untracked/ignored and secret pattern scan finds no known token prefixes in the local file.
- Notes: settings.local.json was untracked and added to .gitignore during migration cleanup. Any previously exposed provider key must remain revoked/rotated.

## Validated

### R001 — Ingest pharmaceutical PDF folders into a persistent document store using Docling with page text and 150 DPI page thumbnails.
- Class: core-capability
- Status: validated
- Description: Ingest pharmaceutical PDF folders into a persistent document store using Docling with page text and 150 DPI page thumbnails.
- Why it matters: This is the foundation for extraction, source-page links, retrieval, and visual RAG over supplier documentation.
- Source: migration from GSD 1.0 INGEST-01 and INGEST-02
- Primary owning slice: M001
- Validation: Phase 1 implementation exists and Python 3.11 venv pytest suite passed with 15 tests before migration cleanup.
- Notes: Implemented with Docling conversion, pypdfium2 rasterization, SQLite document/page tables, and Typer CLI.

## Deferred

## Out of Scope

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | validated | M001 | none | Phase 1 implementation exists and Python 3.11 venv pytest suite passed with 15 tests before migration cleanup. |
| R002 | core-capability | active | M001 | none | Validated when extracted fields persist to SQLite for sample PDFs and include page-level/source-span evidence. |
| R003 | core-capability | active | M001 | none | Validated when tests cover threshold boundaries and dashboard/query rows show expected risk levels. |
| R004 | primary-user-loop | active | M001 | M003 | Validated when Streamlit renders ingested/extracted records from SQLite with correct risk colors and source links. |
| R005 | core-capability | active | M002 | none | Validated when sample questions return cited answers and low-confidence queries abstain rather than hallucinate. |
| R006 | differentiator | active | M002 | none | Validated when visual retrieval improves or complements recall on scanned/table-heavy pages in the gold set. |
| R007 | quality-attribute | active | M003 | none | Validated when eval commands produce repeatable metric reports over a documented gold set. |
| R008 | operability | active | M001 | M002,M003 | Validated when traces include useful phase/doc/page metadata and tests confirm missing Langfuse credentials do not crash the app. |
| R009 | constraint | active | M001 | none | Validated when editable install and pytest pass through ./venv/Scripts/python.exe. |
| R010 | compliance/security | active | M001 | none | Validated when git status shows settings.local.json untracked/ignored and secret pattern scan finds no known token prefixes in the local file. |

## Coverage Summary

- Active requirements: 9
- Mapped to slices: 9
- Validated: 1 (R001)
- Unmapped active requirements: 0
