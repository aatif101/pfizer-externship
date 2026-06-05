# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R014 — Run targeted visual extraction fallback for abstained, suspicious, ungrounded, low-confidence, or missing SDF fields using stored page images from local compliance.db.
- Class: core-capability
- Status: active
- Description: Run targeted visual extraction fallback for abstained, suspicious, ungrounded, low-confidence, or missing SDF fields using stored page images from local compliance.db.
- Why it matters: The real 5-document baseline showed a text-layer ceiling where visually present certificate values were missing from Docling page text.
- Source: user
- Primary owning slice: M004/S04
- Supporting slices: M004/S01,M004/S03
- Validation: Mapped to M004/S04. Validated when visual fallback fills or improves only eligible suspicious fields and records bounded failures for missing images or provider errors.
- Notes: This is a targeted visual extraction fallback, not full ColQwen or Qdrant visual retrieval. Good grounded text values must not be overwritten by visual candidates.

### R015 — Compare real extraction candidates against the human-approved 5-document gold baseline and existing packet-aware candidate runs.
- Class: quality-attribute
- Status: active
- Description: Compare real extraction candidates against the human-approved 5-document gold baseline and existing packet-aware candidate runs.
- Why it matters: The project needs measured evidence, not subjective claims, to decide whether visual fallback improved real SDF extraction.
- Source: user
- Primary owning slice: M004/S05
- Supporting slices: M004/S01,M004/S02,M004/S03,M004/S04
- Validation: Mapped to M004/S05. Validated when a final candidate eval run is persisted and compared against real-text and packet-aware baselines in metrics and dashboard surfaces.
- Notes: Comparison must include the real text baseline, packet-aware candidate, guarded candidate, and final visual-fallback candidate where available.

### R016 — Keep confidential SDF PDFs, local SQLite databases, page images, snapshots, and private benchmark artifacts local and ignored during real evaluation work.
- Class: compliance/security
- Status: active
- Description: Keep confidential SDF PDFs, local SQLite databases, page images, snapshots, and private benchmark artifacts local and ignored during real evaluation work.
- Why it matters: Supplier documentation is confidential and must not be exposed through source control, logs, traces, or planning artifacts.
- Source: user
- Primary owning slice: M004/S05
- Supporting slices: M004/S01,M004/S02,M004/S03,M004/S04
- Validation: Mapped to M004/S05. Validated by git status and ignored-file checks after real evaluation runs.
- Notes: Do not commit compliance.db, .env, local_data, private, PDFs, page images, snapshots, or provider outputs. Public artifacts must contain only bounded metadata and metrics.

### R017 — Verify M004 with Windows-native commands only and never invoke /bin/bash or gsd_exec runtime=bash.
- Class: constraint
- Status: active
- Description: Verify M004 with Windows-native commands only and never invoke /bin/bash or gsd_exec runtime=bash.
- Why it matters: This Windows environment can fail falsely when tooling assumes /bin/bash or POSIX command paths.
- Source: user
- Primary owning slice: M004/S05
- Supporting slices: M004/S01,M004/S02,M004/S03,M004/S04
- Validation: Mapped to M004/S05. Validated when slice and milestone verification evidence uses Windows-safe commands only.
- Notes: Use gsd_exec runtime=node spawning venv\\Scripts\\python.exe for verification evidence, or Windows-native venv/Scripts/python.exe commands without POSIX assumptions.

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

### R007 — Maintain an evaluation harness with extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost metrics.
- Class: quality-attribute
- Status: validated
- Description: Maintain an evaluation harness with extraction F1, retrieval recall, faithfulness/relevancy, citation accuracy, latency, and cost metrics.
- Why it matters: The demo needs evidence, not just claims, especially for compliance-oriented AI.
- Source: migration from GSD 1.0 EVAL and BENCH requirements
- Primary owning slice: M003
- Validation: Validated across M003 evaluation slices and S08 closeout evidence: persisted SQLite eval run history supports extraction/retrieval/RAG metric families including extraction F1, retrieval recall, citation accuracy, faithfulness/relevancy, latency, cost, and token metrics. S08 runtime UAT artifacts prove the Streamlit Eval tab renders two synthetic complete runs, metric history, comparison deltas, fresh-database no-runs guidance, and no traceback. Fresh closeout verification: `venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_app.py tests/test_s08_uat_seed.py` exited 0 with 30 passed; artifact validation confirmed 2 populated runs, 12 required metric names, and 0 rows in fresh eval tables.
- Notes: M003 S08 provides final runtime UAT evidence for dashboard-visible persisted evaluation history using sanitized synthetic data. Optional live services remain gracefully absent; no provider payloads, raw prompts/answers/snippets, document text/images, Docling JSON, full hashes, or secrets are included in evidence.

### R008 — Trace ingestion, extraction, retrieval, generation, and evaluation operations with Langfuse while avoiding secret leakage.
- Class: operability
- Status: validated
- Description: Trace ingestion, extraction, retrieval, generation, and evaluation operations with Langfuse while avoiding secret leakage.
- Why it matters: Observability is necessary for debugging and for auditability in a pharmaceutical document workflow.
- Source: migration from GSD 1.0 OBS-01 and readiness cleanup
- Primary owning slice: M003
- Supporting slices: M001,M002
- Validation: Validated in M003 S07 by focused offline pytest verification covering Langfuse trace metadata across ingestion/storage, extraction, retrieval/generation existing trace safety, and retrieval evaluation/optional metrics. Evidence: `venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py tests/test_extraction_pipeline.py tests/test_ingest.py` exited 0 with 51 passed and 18 warnings, proving missing/failing Langfuse does not crash and forbidden raw content/secrets are excluded.
- Notes: M003 S07 completed full cross-pipeline Langfuse tracing through `src.tracing.safe_update_current_trace` allowlisted metadata. Dashboard tracing was intentionally out of scope; S08 remains for Eval tab UAT evidence rather than R008 implementation.

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

### R011 — Preserve extraction and compliance results by run so baseline and candidate runs can coexist without overwriting historical meaning.
- Class: continuity
- Status: validated
- Description: Preserve extraction and compliance results by run so baseline and candidate runs can coexist without overwriting historical meaning.
- Why it matters: Candidate experiments must be honestly comparable against the real baseline without silently changing what dashboard state means.
- Source: user
- Primary owning slice: M004/S01
- Validation: M004/S01 closeout verification passed: tests persist two SDFExtractionRecord values for the same doc_id with different run_id values, reconstruct each run independently through run-scoped repository APIs, and confirm latest-write get/list compatibility remains intact.
- Notes: Validated by Windows-safe pytest closeout run .gsd/exec/0712d0ec-1619-4cbd-9db7-f155b778e736.stdout.

### R012 — Let the Compliance dashboard select and clearly label extraction runs, including baseline, candidate, and current latest-write state.
- Class: primary-user-loop
- Status: validated
- Description: Let the Compliance dashboard select and clearly label extraction runs, including baseline, candidate, and current latest-write state.
- Why it matters: Evaluators need to know exactly which extraction run they are inspecting before trusting compliance records.
- Source: user
- Primary owning slice: M004/S02
- Supporting slices: M004/S01
- Validation: M004/S02 validated by repository-backed pytest coverage and fake Streamlit render tests for the Compliance dashboard run selector. Closeout verification via Windows-safe gsd_exec runtime=node ran venv\Scripts\python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py tests/test_dashboard_ui_helpers.py tests/test_app.py tests/test_extraction_persistence.py tests/test_extraction_run_history_schema.py and reported 54 passed with exit code 0.
- Notes: The dashboard can select latest compatibility state or explicit historical extraction runs and labels baseline, candidate, historical, and latest views without falling back from selected empty historical runs to latest rows.

### R013 — Capture bounded Gemini extraction token and cost observations for text and visual extraction calls.
- Class: operability
- Status: validated
- Description: Capture bounded Gemini extraction token and cost observations for text and visual extraction calls.
- Why it matters: Real extraction quality must be evaluated alongside cost and token usage, especially once visual calls are introduced.
- Source: user
- Primary owning slice: M004/S03
- Supporting slices: M004/S04,M004/S05
- Validation: M004/S03 validated by Windows-native pytest gates proving mocked Gemini usage metadata persists bounded observations and aggregates into eval_metrics without raw confidential content: gsd_exec 376a460c-b25a-4cd4-9015-fc2fd7f6303d ran all planned S03 commands and passed (10 + 36 + 26 tests).
- Notes: S03 covers text extraction calls and establishes the observation/eval contract for S04 visual fallback reuse.

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
| R007 | quality-attribute | validated | M003 | none | Validated across M003 evaluation slices and S08 closeout evidence: persisted SQLite eval run history supports extraction/retrieval/RAG metric families including extraction F1, retrieval recall, citation accuracy, faithfulness/relevancy, latency, cost, and token metrics. S08 runtime UAT artifacts prove the Streamlit Eval tab renders two synthetic complete runs, metric history, comparison deltas, fresh-database no-runs guidance, and no traceback. Fresh closeout verification: `venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_app.py tests/test_s08_uat_seed.py` exited 0 with 30 passed; artifact validation confirmed 2 populated runs, 12 required metric names, and 0 rows in fresh eval tables. |
| R008 | operability | validated | M003 | M001,M002 | Validated in M003 S07 by focused offline pytest verification covering Langfuse trace metadata across ingestion/storage, extraction, retrieval/generation existing trace safety, and retrieval evaluation/optional metrics. Evidence: `venv/Scripts/python.exe -m pytest -q tests/test_tracing.py tests/test_retrieval_eval_runner.py tests/test_retrieval_eval_optional_metrics.py tests/test_extraction_pipeline.py tests/test_ingest.py` exited 0 with 51 passed and 18 warnings, proving missing/failing Langfuse does not crash and forbidden raw content/secrets are excluded. |
| R009 | constraint | validated | M001 | none | Validated by repeated M001/M002 verification through the project Python 3.11 virtualenv using the Windows-compatible `venv/Scripts/python.exe` command path; global Python 3.14 is not the supported project runtime. |
| R010 | compliance/security | validated | M001 | none | Validated by project hygiene plus M002 verification that public CLI/service/Chat/tracing diagnostics avoid secrets, raw provider payloads, full page text, image blobs, Docling JSON, and full content hashes. |
| R011 | continuity | validated | M004/S01 | none | M004/S01 closeout verification passed: tests persist two SDFExtractionRecord values for the same doc_id with different run_id values, reconstruct each run independently through run-scoped repository APIs, and confirm latest-write get/list compatibility remains intact. |
| R012 | primary-user-loop | validated | M004/S02 | M004/S01 | M004/S02 validated by repository-backed pytest coverage and fake Streamlit render tests for the Compliance dashboard run selector. Closeout verification via Windows-safe gsd_exec runtime=node ran venv\Scripts\python.exe -m pytest -q tests/test_compliance_dashboard.py tests/test_dashboard_compliance_tab.py tests/test_dashboard_ui_helpers.py tests/test_app.py tests/test_extraction_persistence.py tests/test_extraction_run_history_schema.py and reported 54 passed with exit code 0. |
| R013 | operability | validated | M004/S03 | M004/S04,M004/S05 | M004/S03 validated by Windows-native pytest gates proving mocked Gemini usage metadata persists bounded observations and aggregates into eval_metrics without raw confidential content: gsd_exec 376a460c-b25a-4cd4-9015-fc2fd7f6303d ran all planned S03 commands and passed (10 + 36 + 26 tests). |
| R014 | core-capability | active | M004/S04 | M004/S01,M004/S03 | Mapped to M004/S04. Validated when visual fallback fills or improves only eligible suspicious fields and records bounded failures for missing images or provider errors. |
| R015 | quality-attribute | active | M004/S05 | M004/S01,M004/S02,M004/S03,M004/S04 | Mapped to M004/S05. Validated when a final candidate eval run is persisted and compared against real-text and packet-aware baselines in metrics and dashboard surfaces. |
| R016 | compliance/security | active | M004/S05 | M004/S01,M004/S02,M004/S03,M004/S04 | Mapped to M004/S05. Validated by git status and ignored-file checks after real evaluation runs. |
| R017 | constraint | active | M004/S05 | M004/S01,M004/S02,M004/S03,M004/S04 | Mapped to M004/S05. Validated when slice and milestone verification evidence uses Windows-safe commands only. |

## Coverage Summary

- Active requirements: 4
- Mapped to slices: 4
- Validated: 12 (R001, R002, R003, R004, R005, R007, R008, R009, R010, R011, R012, R013)
- Unmapped active requirements: 0
