---
id: M001
title: "Phase 2 Extraction and Compliance"
status: complete
completed_at: 2026-05-20T19:29:17.108Z
key_decisions:
  - Keep final-assembly proof offline and credential-free by using the existing provider protocol seam with exact grounded spans.
  - Clarify R005/R006/R007 as future M002/M003 scope instead of treating them as M001 failures.
  - Treat R008 as partial in M001: non-fatal credentials and sanitized metadata are covered; full trace coverage remains active for future milestones.
key_files:
  - tests/test_s05_end_to_end_proof.py
  - src/extraction/models.py
  - src/extraction/pipeline.py
  - src/extraction/repository.py
  - src/extraction/risk.py
  - src/dashboard/compliance.py
  - src/app.py
  - .gsd/milestones/M001/M001-ROADMAP.md
  - .gsd/milestones/M001/M001-VALIDATION.md
lessons_learned:
  - `tests/fixtures/sample.pdf` is not suitable for final ingestion proof because it can persist empty page text; runtime-generated minimal text PDFs provide a deterministic Docling integration fixture.
  - For this Windows repo, `venv/Scripts/python.exe` is the reliable verification command path for GSD evidence.
  - Final validation should distinguish milestone scope from future product requirements so active future requirements do not appear as current milestone failures.
---

# M001: Phase 2 Extraction and Compliance

**M001 completed the baseline PDF ingestion to structured extraction to compliance risk to dashboard workflow, with final realistic offline proof and validation pass.**

## What Happened

M001 delivered the Phase 2 extraction and compliance baseline on top of the existing ingestion foundation. The milestone now has typed six-field SDF extraction models, SQLite schema and repository support for field-level evidence plus document-level compliance rows, an offline extraction pipeline with provider abstraction and sanitized diagnostics, deterministic compliance risk computation, and a Streamlit Compliance tab backed by persisted SQLite records. The final remediation slice added a realistic PDF final-assembly proof that generates a one-page Supplier Declaration Form PDF, ingests it through Docling, verifies grounded page text, runs the real extraction pipeline with a fake provider citing exact spans, persists extraction/risk records, and verifies dashboard adapter formatting. M001 also now includes an explicit boundary map and clarified requirement scope separating completed extraction/compliance work from future Q&A, visual retrieval, and evaluation milestones.

## Success Criteria Results

- Migration cleanup leaves no tracked local secrets: met through S01 and preserved by S05.
- Python 3.11 venv is documented and verified: met through repeated `venv/Scripts/python.exe` verification.
- Phase 2 extraction stores required metadata with source evidence: met through S02-S03 and S05 final proof.
- Compliance risk levels are computed and visible to the user: met through S03-S04 and S05 dashboard adapter proof.
- Langfuse/tracing behavior remains non-fatal when credentials are absent: met for M001 scope; broader R008 tracing remains future scope.
- Realistic PDF end-to-end proof: met by `tests/test_s05_end_to_end_proof.py`.

## Definition of Done Results

- Python 3.11 venv path verified: S05 closeout ran all commands through `venv/Scripts/python.exe`.
- Structured extraction fields persisted: S02-S03 and S05 verify six field rows with source evidence.
- Compliance risk persisted and visible: S03-S05 verify risk metadata and dashboard-facing formatting.
- Credential-safe startup/diagnostics preserved: S03-S04 regression and S05 offline proof require no live Gemini/Langfuse credentials.
- Boundary map and validation remediation completed: S05 filled boundary/scope artifacts and milestone validation verdict is pass.

## Requirement Outcomes

- R001: Covered by the existing Docling ingestion foundation and exercised by S05 proof.
- R002: Validated by typed extraction schema, pipeline persistence, source evidence, and S05 final proof.
- R003: Validated by deterministic risk computation/persistence and S05 amber-risk proof.
- R004: Validated by SQLite-backed Streamlit Compliance dashboard tests and S05 dashboard adapter proof.
- R005: Future M002 scope, still active.
- R006: Future M002 scope, still active.
- R007: Future M003 scope, still active.
- R008: Advanced/partially covered in M001 for non-fatal missing credentials, sanitized diagnostics, and run/trace metadata; broader tracing remains future work.
- R009: Covered/preserved through Python 3.11 venv verification.
- R010: Covered/preserved through secret hygiene and credential-free S05 proof.

## Deviations

S05 used a credential-free grounded fake provider for final-assembly proof rather than live Gemini. This is intentional because the validation gap was integration evidence, not live model accuracy, and automated proof must not require provider secrets.

## Follow-ups

M002 should implement grounded natural-language Q&A (R005) and visual retrieval with ColQwen/Qdrant (R006). M003 should implement evaluation harness/metrics (R007), dashboard polish, and broader Langfuse tracing coverage for retrieval/generation/evaluation (remaining R008 scope). A future ingestion cleanup can address Docling legacy VLM option deprecation warnings.
