---
id: M002
title: "Retrieval and RAG Chatbot"
status: complete
completed_at: 2026-05-21T03:18:47.042Z
key_decisions:
  - M002 validates the CPU-friendly text-RAG chatbot loop rather than visual ColQwen/Qdrant retrieval.
  - R006 remains a deferred differentiator for a future visual retrieval milestone, not a dropped feature.
  - R007 and R008 remain active M003/future scope so evaluation and full observability are preserved.
  - RAG citations remain service-owned and derived from retrieval evidence, not provider output.
key_files:
  - .gsd/REQUIREMENTS.md
  - .gsd/milestones/M002/M002-VALIDATION.md
  - src/retrieval/indexer.py
  - src/retrieval/retriever.py
  - src/rag/service.py
  - src/dashboard/chat.py
  - src/app.py
lessons_learned:
  - Milestone validators need requirement ownership and future-scope status to distinguish preserved upstream features from missing current-scope implementation.
  - On this Windows project, use `venv/Scripts/python.exe` or `.\venv\Scripts\python.exe` for project verification, not `./venv/Scripts/python.exe`.
  - Deferred differentiators should remain explicit requirements with validation criteria so milestone closure does not silently shrink the final product.
---

# M002: Retrieval and RAG Chatbot

**M002 delivered and validated the grounded text Retrieval and RAG Chatbot loop while preserving future visual retrieval, evaluation, and observability scope.**

## What Happened

M002 delivered the first grounded Retrieval and RAG Chatbot loop for the Pfizer SDF Intelligence System. The milestone established a repeatable SQLite-backed retrieval index over ingested pages, added a CPU-friendly hybrid text retriever with evidence gating and safe snippets, introduced a provider-safe RAG answer service with deterministic fake-provider tests and lazy Gemini support, wired the service into the Streamlit Chat tab, and proved operational failure states without live secrets. A remediation slice clarified that visual ColQwen/Qdrant retrieval remains future scope rather than missing M002 work, preserving the full intended product feature set while allowing the text-RAG milestone to close honestly.

After an initial needs-attention validation, requirement records were clarified so M002 is judged against its actual ownership: R005 is validated here; R001-R004 are already validated and regression-preserved; R006 remains deferred visual retrieval; R007/R008 remain active future evaluation/observability scope; R009/R010 are validated constraints. The rerun validation passed across requirements coverage, cross-slice integration, acceptance criteria, and verification classes.

## Success Criteria Results

- SQLite-backed ingested document pages can be indexed through a repeatable command with clear metadata and corpus states: PASS via S01/S05.
- CPU-friendly hybrid text retriever returns ranked contexts with stable identifiers, filenames, 1-indexed pages, scores, and snippets: PASS via S02/S05.
- RAG service refuses weak/off-topic questions and does not fabricate citations: PASS via S02/S03/S05.
- Live Gemini path exists behind offline-safe provider seam while tests use fake providers and no secrets: PASS via S03/S04/S05.
- Streamlit Chat exercises the real service path from local SQLite through retrieval, evidence gating, generation, citation rendering, and error states: PASS via S04/S05.
- Final verification proves CLI indexing, offline service path, Chat rendering path, and operational failures with deterministic tests: PASS via S05/S06 and pass validation rerun.

## Definition of Done Results

- All six M002 slices are complete with all tasks done per `gsd_milestone_status`.
- Milestone validation was rerun after requirement-scope cleanup and returned `pass`.
- Contract verification passed through deterministic offline tests and fixture data with fake providers.
- Integration verification passed for SQLite pages → retrieval index CLI → retriever → RAG answer service → Streamlit Chat rendering.
- Operational verification passed for missing/empty/stale index states, weak evidence, missing Gemini credentials, provider failures, malformed/blank provider output, and no-op-safe Langfuse hooks.
- UAT evidence passed through S04/S05 summaries for cited answers, abstention, setup/provider failures, and offline Chat rendering without live secrets.

## Requirement Outcomes

- R001-R004: Already validated by M001 and regression-preserved by M002; no ownership change or feature loss.
- R005: Validated by M002 through CLI indexing, hybrid retrieval, evidence-gated RAG answers, Streamlit Chat rendering, citations, abstention, and provider failure handling.
- R006: Explicitly deferred to future visual retrieval work; ColQwen/Qdrant remains in the product contract.
- R007: Active M003/future scope; M002 advanced deterministic retrieval/citation proof scaffolding but does not replace full gold-set evaluation.
- R008: Active M003/future scope; M002 advanced no-op-safe retrieval/RAG trace metadata hooks but does not replace full cross-pipeline Langfuse coverage.
- R009: Validated through repeated project Python 3.11 virtualenv verification.
- R010: Validated through secret-safe diagnostics/redaction proof across M002 public surfaces.

## Deviations

Initial validation returned needs-attention because broad project requirements were interpreted as if M002 had to fully satisfy all of them. Requirement ownership was clarified without removing features: R001-R004 remain validated by M001 and regression-preserved by M002; R005 is validated by M002; R006 remains deferred future visual retrieval; R007/R008 remain active M003 scope; R009/R010 are validated constraints. Validation was rerun and passed.

## Follow-ups

Preserve and execute remaining product scope in future milestones: R006 visual ColQwen/Qdrant retrieval, R007 full gold-set evaluation harness with metrics, and R008 full Langfuse tracing across ingestion, extraction, retrieval, generation, and evaluation.
