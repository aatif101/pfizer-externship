# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R007 — Maintain an evaluation harness with extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost metrics.
- Class: quality-attribute
- Status: active
- Description: Maintain an evaluation harness with extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost metrics.
- Why it matters: The demo needs evidence, not just claims, especially for compliance-oriented AI.
- Source: migration from GSD 1.0 EVAL and BENCH requirements
- Primary owning slice: M003
- Validation: Validated when M003 eval commands produce repeatable metric reports over a documented gold set, including extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost.
- Notes: M002 advanced R007 only by proving deterministic retrieval/citation regression scaffolding for the text-RAG loop. Full gold-set metric reporting remains active scope for M003 and must not be dropped.

### R008 — Trace ingestion, extraction, retrieval, generation, and evaluation operations with Langfuse while avoiding secret leakage.
- Class: operability
- Status: active
- Description: Trace ingestion, extraction, retrieval, generation, and evaluation operations with Langfuse while avoiding secret leakage.
- Why it matters: Observability is necessary for debugging and for auditability in a pharmaceutical document workflow.
- Source: migration from GSD 1.0 OBS-01 and readiness cleanup
- Primary owning slice: M003
- Supporting slices: M001,M002
- Validation: Validated when M003 demonstrates Langfuse traces across ingestion, extraction, retrieval, generation, and evaluation with useful phase/doc/page metadata, while tests confirm missing or failing Langfuse configuration does not crash the app and no secrets are logged.
- Notes: M001/M002 advanced R008 with safe diagnostics and no-op-safe retrieval/RAG trace metadata hooks. Full cross-pipeline Langfuse coverage, including evaluation tracing, remains active M003 scope and must not be dropped.

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

### R002 — Extract structured SDF metadata including document type, vendor, manufacturing date, effective date, revision date, and expiry date with source spans and source page references.
- Class: core-capability
- Status: validated
- Description: Extract structured SDF metadata including document type, vendor, manufacturing date, effective date, revision date, and expiry date with source spans and source page references.
- Why it matters: Compliance officers need reliable structured fields to assess supplier document freshness and risk.
- Source: migration from GSD 1.0 EXTRACT-01
- Primary owning slice: M001
- Validation: Validated across M001 S02-S04: typed metadata schema supports document type, vendor, manufacturing/effective/revision/expiry dates with confidence/review/source evidence; extraction persists rows to SQLite; S04 dashboard tests render persisted field metadata with 1-indexed source page evidence from real SQLite records.
- Notes: M001 provides the baseline extraction-to-dashboard contract; future milestones may improve model accuracy and visual citation UX.

### R003 — Compute compliance risk levels from document age using green, amber, and red thresholds and store the result with extracted fields.
- Class: core-capability
- Status: validated
- Description: Compute compliance risk levels from document age using green, amber, and red thresholds and store the result with extracted fields.
- Why it matters: The primary demo value is immediate identification of expired or at-risk supplier documentation.
- Source: migration from GSD 1.0 EXTRACT-02
- Primary owning slice: M001
- Validation: Validated across M001 S02-S04: compliance risk thresholds are implemented/tested, extraction stores computed risk fields, and S04 dashboard/query tests prove persisted risk levels/reasons render from SQLite records.
- Notes: D010 risk policy remains consumed as persisted data by the dashboard.

### R004 — Display extracted compliance records in Streamlit with sortable fields, risk coloring, confidence, and source page links.
- Class: primary-user-loop
- Status: validated
- Description: Display extracted compliance records in Streamlit with sortable fields, risk coloring, confidence, and source page links.
- Why it matters: The dashboard is the evaluator-facing surface for the compliance workflow.
- Source: migration from GSD 1.0 DASH-01 and DASH-02
- Primary owning slice: M001
- Supporting slices: M003
- Validation: Validated in S04 by SQLite-backed dashboard tests and full regression: Compliance tab renders persisted records with metadata, age/risk display, confidence, review state, run/trace metadata, and source page/span details; empty/missing DB states are friendly and app startup is smoke-tested.
- Notes: S04 establishes the offline evaluator-facing dashboard surface; later M003 work can add richer sorting/filtering/evaluation polish.

### R005 — Provide grounded natural-language Q&A over the document corpus with page-level citations and abstention on insufficient evidence.
- Class: core-capability
- Status: validated
- Description: Provide grounded natural-language Q&A over the document corpus with page-level citations and abstention on insufficient evidence.
- Why it matters: The chatbot is the second primary user loop and must remain grounded for pharma compliance credibility.
- Source: migration from GSD 1.0 RETRIEVE and RAG requirements
- Primary owning slice: M002
- Validation: Validated in M002 S05 by final offline regression: CLI index build, hybrid retrieval, fake-provider answer generation, Streamlit Chat rendering, cited grounded answers, unrelated-query abstention, and provider failure paths passed deterministically with fixture SQLite data and no live secrets.
- Notes: Initial M002 implementation uses the planned hybrid text retrieval baseline. Visual retrieval remains separate under R006.

### R009 — Use Python 3.11 project virtual environment for development and verification; do not rely on global Python 3.14.
- Class: constraint
- Status: validated
- Description: Use Python 3.11 project virtual environment for development and verification; do not rely on global Python 3.14.
- Why it matters: The project dependency set is verified in Python 3.11 and fails under the current global Python 3.14 environment.
- Source: readiness cleanup 2026-05-19
- Primary owning slice: M001
- Validation: Validated by repeated M001/M002 verification through the project Python 3.11 virtualenv using the Windows-compatible `venv/Scripts/python.exe` command path; global Python 3.14 is not the supported project runtime.
- Notes: Global Python 3.14 currently has incompatible Pydantic/pydantic-settings packages. Supported Windows commands should use `venv/Scripts/python.exe` or `.\venv\Scripts\python.exe`, not the POSIX-style `./venv/Scripts/python.exe` prefix.

### R010 — Do not commit local provider tokens, API keys, or machine-specific model settings; keep local settings files ignored.
- Class: compliance/security
- Status: validated
- Description: Do not commit local provider tokens, API keys, or machine-specific model settings; keep local settings files ignored.
- Why it matters: The repo previously contained token-like material; preventing recurrence is a non-negotiable security hygiene requirement.
- Source: readiness cleanup 2026-05-19
- Primary owning slice: M001
- Validation: Validated by project hygiene plus M002 verification that public CLI/service/Chat/tracing diagnostics avoid secrets, raw provider payloads, full page text, image blobs, Docling JSON, and full content hashes.
- Notes: settings.local.json was untracked and added to .gitignore during migration cleanup. Any previously exposed provider key must remain revoked/rotated. Future provider, tracing, and evaluation work must preserve the M002 redaction/bounded-diagnostics contract.

## Deferred

### R006 — Add visual page retrieval with ColQwen-style embeddings and Qdrant multivector reranking for layout-aware document search.
- Class: differentiator
- Status: deferred
- Description: Add visual page retrieval with ColQwen-style embeddings and Qdrant multivector reranking for layout-aware document search.
- Why it matters: Visual retrieval is the differentiated technical feature for scanned, stamped, and table-heavy pharmaceutical documents.
- Source: migration from GSD 1.0 VISUAL-01 and VISUAL-02
- Primary owning slice: future visual retrieval milestone
- Validation: Validated when visual retrieval improves or complements recall on scanned/table-heavy pages in the gold set.
- Notes: Deferred outside M002 under D013: M002 intentionally validates the CPU-friendly text-RAG R005 loop only, while keeping retriever DTO and citation boundaries compatible with future visual ColQwen/Qdrant retrieval. R006 remains future work for a later visual retrieval milestone or roadmap reassessment, with validation criteria preserved.

## Out of Scope

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | validated | M001 | none | Phase 1 implementation exists and Python 3.11 venv pytest suite passed with 15 tests before migration cleanup. |
| R002 | core-capability | validated | M001 | none | Validated across M001 S02-S04: typed metadata schema supports document type, vendor, manufacturing/effective/revision/expiry dates with confidence/review/source evidence; extraction persists rows to SQLite; S04 dashboard tests render persisted field metadata with 1-indexed source page evidence from real SQLite records. |
| R003 | core-capability | validated | M001 | none | Validated across M001 S02-S04: compliance risk thresholds are implemented/tested, extraction stores computed risk fields, and S04 dashboard/query tests prove persisted risk levels/reasons render from SQLite records. |
| R004 | primary-user-loop | validated | M001 | M003 | Validated in S04 by SQLite-backed dashboard tests and full regression: Compliance tab renders persisted records with metadata, age/risk display, confidence, review state, run/trace metadata, and source page/span details; empty/missing DB states are friendly and app startup is smoke-tested. |
| R005 | core-capability | validated | M002 | none | Validated in M002 S05 by final offline regression: CLI index build, hybrid retrieval, fake-provider answer generation, Streamlit Chat rendering, cited grounded answers, unrelated-query abstention, and provider failure paths passed deterministically with fixture SQLite data and no live secrets. |
| R006 | differentiator | deferred | future visual retrieval milestone | none | Validated when visual retrieval improves or complements recall on scanned/table-heavy pages in the gold set. |
| R007 | quality-attribute | active | M003 | none | Validated when M003 eval commands produce repeatable metric reports over a documented gold set, including extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost. |
| R008 | operability | active | M003 | M001,M002 | Validated when M003 demonstrates Langfuse traces across ingestion, extraction, retrieval, generation, and evaluation with useful phase/doc/page metadata, while tests confirm missing or failing Langfuse configuration does not crash the app and no secrets are logged. |
| R009 | constraint | validated | M001 | none | Validated by repeated M001/M002 verification through the project Python 3.11 virtualenv using the Windows-compatible `venv/Scripts/python.exe` command path; global Python 3.14 is not the supported project runtime. |
| R010 | compliance/security | validated | M001 | none | Validated by project hygiene plus M002 verification that public CLI/service/Chat/tracing diagnostics avoid secrets, raw provider payloads, full page text, image blobs, Docling JSON, and full content hashes. |

## Coverage Summary

- Active requirements: 2
- Mapped to slices: 2
- Validated: 7 (R001, R002, R003, R004, R005, R009, R010)
- Unmapped active requirements: 0
