# Pfizer SDF Intelligence System

## What This Is

An end-to-end AI-powered pharmaceutical document intelligence and compliance system for Pfizer supplier documentation (SDFs). The system ingests a folder of pharmaceutical PDFs (certificates of analysis, vendor certificates, compliance forms — many scanned or stamped) and delivers: automated field extraction with compliance flagging, a visual + hybrid RAG chatbot, and a Streamlit compliance dashboard with full observability. Built as a Pfizer externship demo to showcase AI engineering capability on real-world pharma document workflows.

## Core Value

A pharmaceutical compliance officer can upload a folder of supplier documents and immediately see which ones are expired or at risk, ask natural language questions across the entire corpus, and trust every answer is grounded in a cited source page — with no hallucination.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Phase 1 — Baseline pipeline:**
- [ ] Ingest folder of pharmaceutical PDFs using IBM Docling (v2.72+, Granite-Docling-258M) for layout-aware extraction
- [ ] Extract structured metadata (doc type, vendor name, manufacturing date, effective date, revision date, expiry date) via single-pass VLM extraction into validated Pydantic models
- [ ] Flag documents older than 3–4 years as compliance risks
- [ ] Hybrid RAG chatbot: BM25 + dense retrieval, fused with reranker
- [ ] Streamlit compliance dashboard: sortable table (filename, doc type, vendor, revision date, age, risk flag, confidence, source page link), color-coded risk levels (red >3yr, amber 2–3yr, green <2yr)
- [ ] Eval harness: hand-labeled gold set (~50 pages), extraction F1 per field, retrieval recall@5, answer faithfulness, citation accuracy, latency p50/p95, cost per query

**Phase 2 — Upgraded pipeline:**
- [ ] ColQwen2 visual retrieval: page images embedded directly, indexed in Qdrant (HNSW first stage + full multivector late-interaction reranking)
- [ ] Agentic extraction critic loop: extractor proposes fields → critic re-reads source page and challenges each claim → reconciliation pass on disagreements. Each extraction includes confidence score + bounding-box citation
- [ ] Low-confidence extractions routed to HITL review queue
- [ ] LangGraph agentic RAG: query decomposition → retrieve → evaluate quality → re-retrieve if insufficient → draft → self-critique for faithfulness → regenerate if needed
- [ ] Confidence calibration: system abstains rather than hallucinate
- [ ] Langfuse tracing: all agent steps, LLM calls, retrievals, extractions traced for auditability

**Phase 3 — Demo polish:**
- [ ] Architecture diagrams
- [ ] Eval dashboard with Phase 1 vs Phase 2 benchmark comparison (same documents, real numbers)
- [ ] Recorded walkthrough
- [ ] Engineering design doc with decisions/trade-offs section

### Out of Scope

- Production deployment / hosting infrastructure — this is a demo, not a live system
- Authentication / multi-user access control — single-user demo
- Ingestion of non-PDF formats (Word, Excel, etc.) — PDF-only for v1
- Fine-tuning any models — API/pretrained models only

## Context

- **Externship context:** Pfizer externship demo project. Audience is Pfizer stakeholders and externship evaluators. Deliverable is a working system + recorded walkthrough + engineering design doc.
- **Documents:** Mix of real Pfizer SDFs (provided by Pfizer) and synthetic/publicly available pharma PDFs. Real docs used for demo; synthetics fill gaps during dev.
- **Self-benchmarking:** Phase 1 is the "baseline" (single-pass VLM + basic RAG). Phase 2 is the upgrade (ColQwen + agentic critic + LangGraph). Phase 3 benchmarks Phase 2 against Phase 1 on the same document set. This is intentional — both sides are controlled, comparison is airtight.
- **Runtime:** Colab is preferred for live demo walkthrough (GPU access via Colab Pro for ColQwen inference). Development can happen locally. Not a hard constraint.
- **Existing codebase:** Some existing code in the repo — not yet mapped.

## Constraints

- **Tech stack**: Python 3.11+, Docling, colpali-engine (ColQwen2), Qdrant, LangGraph, Langfuse, Streamlit, Pydantic, RAGAS — locked by design
- **VLM API**: Claude Sonnet or Gemini 2.5 Flash for extraction/generation — API-based, no self-hosted LLM
- **GPU**: ColQwen2 visual retrieval requires GPU; Colab Pro acceptable for demo
- **Timeline**: No hard deadline — build it right

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Phased build: Phase 1 as baseline, Phase 2 as upgrade | Enables a self-controlled before/after benchmark with real numbers | — Pending |
| IBM Docling over PyMuPDF+Tesseract | Layout-aware extraction handles scanned/stamped docs and complex tables better | — Pending |
| ColQwen2 for visual retrieval | Page images embedded directly — captures layout, stamps, tables that text extraction misses | — Pending |
| Confidence calibration + abstention | Pharmaceutical context: wrong answer is worse than no answer | — Pending |
| LangGraph for agentic RAG | Explicit state machine for query decomp → retrieve → evaluate → regenerate loop | — Pending |
| Langfuse for observability | Full audit trail of all agent steps — required for pharmaceutical compliance credibility | — Pending |

---
*Last updated: 2026-04-16 after initialization*

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state
