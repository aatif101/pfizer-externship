# Project

## What This Is

Pfizer SDF Intelligence System is an end-to-end AI-powered pharmaceutical document intelligence and compliance system for supplier documentation. The project ingests pharmaceutical PDFs into SQLite with Docling page text and page images, extracts structured SDF metadata with source evidence, computes compliance risk, supports grounded document Q&A, and exposes Streamlit Compliance, Chat, and Eval dashboards.

The current system has completed ingestion, baseline extraction/compliance, text retrieval and RAG chat, observability, and evaluation dashboard milestones. A real confidential 5-document SDF baseline has been created locally from already-ingested supplier PDFs, with human-approved gold extraction labels and measured baseline/candidate runs.

## Core Value

A pharmaceutical compliance reviewer can inspect supplier documents and trust that extracted fields, risk flags, and answers are grounded in cited source evidence, while the engineering evaluator can compare extraction candidates honestly against a real human-approved baseline without leaking confidential artifacts.

## Project Shape

- **Complexity:** complex
- **Why:** The project crosses PDF ingestion, SQLite persistence, LLM extraction, visual fallback, Streamlit dashboards, evaluation metrics, confidential local artifacts, and live Gemini API usage.

## Current State

- M001 validated Docling ingestion, structured SDF extraction, compliance risk, and Compliance dashboard basics.
- M002 validated CPU-friendly text retrieval and grounded RAG Chat.
- M003 validated evaluation dashboard history, optional metrics, and tracing/observability hardening.
- A local real 5-document SDF evaluation baseline exists in ignored `compliance.db` and `local_data/` artifacts.
- Latest hardening added dashboard latest-write warnings, prompt packet policy, placeholder/date guards, and a guarded candidate eval run.

## Architecture / Key Patterns

- Python 3.11 project virtual environment is the supported runtime.
- SQLite is the local persistence boundary for documents, pages, extraction rows, compliance rows, retrieval index rows, gold labels, eval runs, and eval metrics.
- Extraction uses provider-neutral Pydantic contracts under `src/extraction`, with Gemini behind a lazy runtime adapter and fake providers in routine tests.
- Non-abstained fields require source page and verbatim span. Abstained fields require a reason.
- Compliance risk is deterministic and conservative.
- RAG answer generation is service-owned: retrieval evidence is authoritative and provider output does not own citations.
- Trace and observation metadata must be allowlisted and bounded; raw page text, prompts, provider payloads, images, Docling JSON, full hashes, and secrets must not leak.

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Phase 2 Extraction and Compliance — Ingest and extract SDF fields into compliance dashboard records.
- [x] M002: Retrieval and RAG Chatbot — Build grounded text retrieval and cited answer generation.
- [x] M003: Dashboard Evaluation and Polish — Persist and display evaluation history, optional metrics, and trace-safe observability.
- [ ] M004: Real SDF Extraction Evaluation Hardening — Preserve extraction runs, capture Gemini cost, add targeted visual fallback, and compare against the real 5-document baseline.
