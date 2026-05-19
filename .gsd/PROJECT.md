# Pfizer SDF Intelligence System

## What This Is

An end-to-end AI-powered pharmaceutical document intelligence and compliance system for Pfizer supplier documentation (SDFs). The system ingests a folder of pharmaceutical PDFs (certificates of analysis, vendor certificates, compliance forms — many scanned or stamped) and delivers: automated field extraction with compliance flagging, a visual + hybrid RAG chatbot, and a Streamlit compliance dashboard with full observability. Built as a Pfizer externship demo to showcase AI engineering capability on real-world pharma document workflows.

## Core Value

A pharmaceutical compliance officer can upload a folder of supplier documents and immediately see which ones are expired or at risk, ask natural language questions across the entire corpus, and trust every answer is grounded in a cited source page — with no hallucination.

## Current Implementation State

Migrated from GSD 1.0 `.planning/` artifacts on 2026-05-19. Phase 1 foundation work is implemented in code and verified in the Python 3.11 project virtual environment.

Implemented Phase 1 surfaces:

- SQLite schema for documents, pages, extractions, and evaluations.
- Docling VLM-based PDF conversion wrapper.
- pypdfium2 150 DPI page rasterization into PNG blobs.
- Typer ingestion CLI.
- Streamlit shell with Compliance, Chat, and Eval tabs.
- Langfuse v3 tracing helper.

Verification baseline at migration:

- `./venv/Scripts/python.exe -m pip install -e ".[dev]"` succeeds.
- `./venv/Scripts/python.exe -m pytest -q` passed before migration cleanup with 15 tests passing.
- Global Python 3.14 is not a supported execution environment for this project.

## Milestone Sequence

- [ ] M001: Phase 2 Extraction and Compliance - Extract SDF metadata, compute compliance risk, and display validated results in Streamlit.
- [ ] M002: Retrieval and RAG Chatbot - Build hybrid retrieval and grounded document Q&A with page-level citations.
- [ ] M003: Dashboard Evaluation and Polish - Add eval harness, benchmark reporting, architecture docs, and demo polish.

## Requirements

### Validated

- Phase 1 foundation and ingestion scaffolding is implemented and testable in Python 3.11.

### Active

**Phase 2 Extraction and Compliance:**

- Extract structured metadata (doc type, vendor name, manufacturing date, effective date, revision date, expiry date) via VLM extraction into validated Pydantic models.
- Include source text span and source page reference per extracted field.
- Flag documents by age: green (<2 years), amber (2-3 years), red (>3 years).
- Store extraction results and compliance flags in SQLite.
- Surface extracted compliance records in the Streamlit Compliance tab.

**Future phases retained from GSD 1.0 plan:**

- Hybrid RAG chatbot: BM25 + dense retrieval, fused with reranker.
- Streamlit dashboard: sortable compliance table, source page links, risk coloring.
- Eval harness: extraction F1, retrieval recall@5, answer faithfulness, citation accuracy, latency, cost.
- ColQwen visual retrieval in Qdrant.
- Agentic extraction critic loop and LangGraph agentic RAG.
- HITL low-confidence review queue.
- Phase 1 vs Phase 2 benchmark and demo polish.

### Out of Scope

- Production deployment / hosting infrastructure — demo only.
- Authentication / multi-user access control — single-user demo.
- Ingestion of non-PDF formats — PDF-only for v1.
- Fine-tuning any models — API/pretrained models only.

## Context

- Externship context: Pfizer demo project for stakeholders/evaluators.
- Documents: mix of real Pfizer SDFs and synthetic/publicly available pharma PDFs.
- Runtime: local development on Python 3.11; Colab Pro L4 remains acceptable for GPU-heavy visual retrieval.
- Current repo was originally generated with GSD 1.0 and has been normalized into current `.gsd/` artifacts for future work.

## Constraints

- Python 3.11 is the supported local runtime.
- Avoid global Python 3.14 for test/dev commands unless dependencies are repaired separately.
- Tech stack remains Python, Docling, Qdrant, LangGraph, Langfuse, Streamlit, Pydantic, RAGAS, and API-based VLMs.
- Do not track local secrets or provider tokens; `settings.local.json` is local-only.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 3.11 is the supported runtime | Global Python 3.14 produced dependency failures; project venv Python 3.11 passes tests | Active |
| Keep Phase 1 implementation and proceed through cleanup before Phase 2 | Phase 1 code is small and testable; cleanup reduces risk before extraction work | Active |
| Treat `settings.local.json` as local-only | A token-like value had been tracked previously; local settings must not be committed | Active |
| Use Docling for PDF conversion and pypdfium2 for page rasterization | Existing implementation passes tests; Docling page image generation remains separate from rasterization path | Active |
| Revisit Docling VLM API before heavy ingestion work | Current tests show deprecation warning for legacy VLM options | Active |

## Evolution

This document is the current-state replacement for `.planning/PROJECT.md`. Historical GSD 1.0 artifacts remain under `.planning/` for reference.