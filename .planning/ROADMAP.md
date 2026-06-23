# Roadmap: Pfizer SDF Intelligence System

## Overview

This roadmap delivers an end-to-end pharmaceutical document intelligence system in three milestone arcs. Phase 1 (Phases 1-4) builds the baseline pipeline: ingestion, extraction, hybrid retrieval, RAG chatbot, compliance dashboard, and evaluation harness. Phase 2 (Phases 5-6) upgrades to visual retrieval, agentic extraction/RAG, HITL review, and full observability. Phase 3 (Phase 7) benchmarks Phase 2 against Phase 1 on the same gold set and polishes deliverables. Each phase delivers a coherent, independently verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation & Ingestion** - Doc store, SQLite schema, Streamlit skeleton, Langfuse wiring, and Docling PDF ingestion pipeline
- [ ] **Phase 2: Extraction & Compliance** - VLM-powered structured field extraction with Pydantic validation and compliance risk flagging
- [ ] **Phase 3: Retrieval & RAG Chatbot** - Hybrid BM25+dense retrieval with reranker, and linear RAG chatbot with page-level citations
- [ ] **Phase 4: Dashboard & Evaluation** - Streamlit compliance table with color-coded risk levels, and eval harness with gold set
- [ ] **Phase 5: Visual Retrieval & Critic Extraction** - ColQwen2 page-image retrieval, extraction critic loop, and per-field confidence ensemble
- [ ] **Phase 6: Agentic RAG & Observability** - LangGraph agentic RAG pipeline, HITL review queue, and Langfuse tracing
- [ ] **Phase 7: Benchmark & Polish** - Side-by-side Phase 1 vs Phase 2 benchmark, eval dashboard, architecture diagrams, walkthrough, and design doc

## Phase Details

### Phase 1: Foundation & Ingestion
**Goal**: A folder of pharmaceutical PDFs can be ingested into a persistent document store with page images, and the project skeleton (SQLite, Streamlit, Langfuse) is wired and running
**Depends on**: Nothing (first phase)
**Requirements**: INGEST-01, INGEST-02
**Success Criteria** (what must be TRUE):
  1. User can run a CLI command pointing at a folder of PDFs and see all documents stored in the doc store with extracted text per page
  2. Each ingested page has a 150 DPI PNG thumbnail stored alongside its text content
  3. Scanned, stamped, and complex-table PDFs are ingested without errors (Docling handles them)
  4. SQLite compliance database schema exists with tables for documents, extractions, and evaluations
  5. Streamlit app launches with skeleton tabs (Compliance, Chat, Eval) and Langfuse connection is verified
**Plans**: 3 plans
Plans:
- [ ] 01-01-PLAN.md — Project scaffold, pyproject.toml, config, Wave 0 test stubs
- [ ] 01-02-PLAN.md — Core ingestion pipeline (DB schema, converter, rasterizer, CLI)
- [ ] 01-03-PLAN.md — Streamlit skeleton and Langfuse v3 tracing

### Phase 2: Extraction & Compliance
**Goal**: Every ingested document has structured metadata extracted and validated, with compliance risk levels computed and stored
**Depends on**: Phase 1
**Requirements**: EXTRACT-01, EXTRACT-02
**Success Criteria** (what must be TRUE):
  1. System extracts doc_type, vendor_name, manufacturing_date, effective_date, revision_date, and expiry_date from each document into a Pydantic-validated model
  2. Each extracted field includes a verbatim source text span and source page reference
  3. Each document is flagged green (<2yr), amber (2-3yr), or red (>3yr) based on document age, stored in the compliance database
**Plans**: TBD

### Phase 3: Retrieval & RAG Chatbot
**Goal**: Users can ask natural-language questions about the document corpus and receive grounded answers with page-level citations
**Depends on**: Phase 1
**Requirements**: RETRIEVE-01, RETRIEVE-02, RETRIEVE-03, RAG-01, RAG-02
**Success Criteria** (what must be TRUE):
  1. Text chunks (~500 tokens) are indexed in Qdrant with both BM25 sparse vectors and BGE-large dense vectors in the sdf_text_chunks collection
  2. Retrieval fuses BM25 and dense candidates via RRF and re-ranks with a cross-encoder
  3. User can ask a question in the Chat tab and receive an answer with document filename and page number citations
  4. System returns "I don't have enough information to answer reliably" when retrieval confidence is low instead of generating unsupported answers
**Plans**: TBD

### Phase 4: Dashboard & Evaluation
**Goal**: Compliance officers can see all documents in a sortable, color-coded table and the eval harness validates pipeline quality against a gold set
**Depends on**: Phase 2, Phase 3
**Requirements**: DASH-01, DASH-02, EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05
**Success Criteria** (what must be TRUE):
  1. Streamlit Compliance tab displays a sortable table with filename, doc type, vendor, revision date, document age, risk flag, confidence score, and source page link for all ingested documents
  2. Risk levels are color-coded red/amber/green inline in the table matching the EXTRACT-02 thresholds
  3. A hand-labeled gold set of ~50 pages exists with an annotation guide covering all document types and extraction fields
  4. Eval harness reports extraction F1 per field, retrieval recall@5, RAGAS faithfulness/relevancy scores, and latency p50/p95 and cost-per-query
**Plans**: TBD
**UI hint**: yes

### Phase 5: Visual Retrieval & Critic Extraction
**Goal**: Retrieval leverages page images via ColQwen2 for layout-aware matching, and extraction uses a critic loop with per-field confidence scoring
**Depends on**: Phase 4
**Requirements**: VISUAL-01, VISUAL-02, EXTRACT-03, EXTRACT-04
**Success Criteria** (what must be TRUE):
  1. Each page image is indexed in Qdrant sdf_page_images collection with ColQwen2.5 embeddings (full multivector with HNSW disabled, plus mean-pooled row and column vectors with HNSW enabled)
  2. Visual retrieval uses two-stage strategy (mean-pooled HNSW prefetch then full multivector MaxSim reranking) fused with Phase 1 text retrieval results
  3. Extraction critic loop challenges proposed fields by re-reading the source page image, with disagreements triggering reconciliation (capped at 2 iterations)
  4. Per-field confidence ensemble score (0.4 logprob + 0.4 self-consistency + 0.2 critic agreement) is computed and fields below 0.75 threshold are routed to HITL queue
**Plans**: 4 plans (this slice covers the VISUAL RETRIEVAL TIER — VISUAL-01, VISUAL-02 — only; EXTRACT-03/04 critic-extraction are split into a follow-up phase per 05-CONTEXT.md Deferred Ideas)
Plans:
- [x] 05-01-PLAN.md — Visual tier foundation: visual_index_runs schema, pure Qdrant collection-config + row/col pooling + blob decode + upsert-payload builders, gpu marker (offline-testable)
- [x] 05-02-PLAN.md — Two-stage query payload builder, RRF (k=60) fusion → RetrievalHit, versioned visual run persistence (offline-testable)
- [x] 05-03-PLAN.md — Integration: retrieval_mode config (text-only|visual-fused), retriever fusion seam, source-tag extension, rq_ex3 gold mojibake repair, privacy allowlist proof
- [x] 05-04-PLAN.md — GPU embedder lazy seam + committed Colab L4 notebook deliverable (real VISUAL-01/02 numbers; Example-3 proof) — autonomous: false (Manual-Only Colab run)

### Phase 6: Agentic RAG & Observability
**Goal**: RAG chatbot uses an agentic pipeline with self-critique, low-confidence extractions surface for human review, and all operations are traced for auditability
**Depends on**: Phase 5
**Requirements**: HITL-01, RAG-03, OBS-01
**Success Criteria** (what must be TRUE):
  1. RAG chatbot uses LangGraph agentic pipeline: query decomposition, retrieve, evaluate quality, re-retrieve if insufficient (max 2 retries), draft, self-critique for faithfulness, regenerate or abstain (max 1 regen)
  2. Dashboard HITL tab surfaces low-confidence extractions for human review and corrections update the compliance database
  3. All agent steps, LLM calls, retrievals, and extractions are traced in Langfuse with a phase tag on every trace session
  4. System abstains rather than hallucinating when confidence is insufficient across both extraction and RAG pathways
**Plans**: TBD
**UI hint**: yes

### Phase 7: Benchmark & Polish
**Goal**: A compelling demo with real numbers showing Phase 2 improvements over Phase 1, supported by architecture diagrams, a recorded walkthrough, and an engineering design doc
**Depends on**: Phase 6
**Requirements**: BENCH-01, BENCH-02, POLISH-01, POLISH-02, POLISH-03
**Success Criteria** (what must be TRUE):
  1. Eval harness runs both Phase 1 and Phase 2 pipelines on the same gold set (via pipeline config flag) and reports mean +/- stddev across 3 runs per metric
  2. Dashboard Eval tab shows Phase 1 vs Phase 2 side-by-side comparison table (extraction F1, recall@5, faithfulness, latency, cost)
  3. Architecture diagrams illustrating both Phase 1 and Phase 2 pipeline data flows exist in the project
  4. A recorded demo walkthrough and an engineering design doc with key decisions and trade-offs section are complete
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Ingestion | 0/3 | Not started | - |
| 2. Extraction & Compliance | 0/TBD | Not started | - |
| 3. Retrieval & RAG Chatbot | 0/TBD | Not started | - |
| 4. Dashboard & Evaluation | 0/TBD | Not started | - |
| 5. Visual Retrieval & Critic Extraction | 0/TBD | Not started | - |
| 6. Agentic RAG & Observability | 0/TBD | Not started | - |
| 7. Benchmark & Polish | 0/TBD | Not started | - |
