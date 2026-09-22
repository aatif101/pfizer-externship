# Roadmap: Pfizer SDF Intelligence System

## Overview

**Submission recovery (2026-09-22):** Read [SUBMISSION-READINESS.md](SUBMISSION-READINESS.md) and [START-HERE.md](START-HERE.md). Next: `/gsd-plan-phase 2.1`. Preserve historical plans; acceptance requires fresh evidence. The unsupported Phase 7 completion claim is reopened.

This roadmap delivers an end-to-end pharmaceutical document intelligence system in three milestone arcs. Phase 1 (Phases 1-4) builds the baseline pipeline: ingestion, extraction, hybrid retrieval, RAG chatbot, compliance dashboard, and evaluation harness. Phase 2 (Phases 5-6) upgrades to visual retrieval, agentic extraction/RAG, HITL review, and full observability. Phase 3 (Phase 7) benchmarks Phase 2 against Phase 1 on the same gold set and polishes deliverables. Each phase delivers a coherent, independently verifiable capability.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Ingestion** - Doc store, SQLite schema, Streamlit skeleton, Langfuse wiring, and Docling PDF ingestion pipeline
- [x] **Phase 2: Extraction & Compliance** - VLM-powered structured field extraction with Pydantic validation and compliance risk flagging
- [ ] **Phase 2.1: Submission Baseline Recovery** - Reproducible benchmark, clean environment and passing offline gate (INSERTED)
- [ ] **Phase 3: Retrieval & RAG Chatbot** - Hybrid BM25+dense retrieval with reranker, and linear RAG chatbot with page-level citations
- [ ] **Phase 4: Dashboard & Evaluation** - Streamlit compliance table with color-coded risk levels, and eval harness with gold set
- [ ] **Phase 5: Visual Retrieval & Critic Extraction** - ColQwen2 page-image retrieval, extraction critic loop, and per-field confidence ensemble
- [ ] **Phase 5.1: Visual Integration and Extraction Assurance** - Real visual Chat, bounded extraction critique and honest confidence (INSERTED)
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

**Plans**: 4 plans
Plans:

- [x] 01-01-PLAN.md — Project scaffold, pyproject.toml, config, Wave 0 test stubs
- [x] 01-02-PLAN.md — Core ingestion pipeline (DB schema, converter, rasterizer, CLI)
- [x] 01-03-PLAN.md — Streamlit skeleton and Langfuse v3 tracing
- [x] 01-04-PLAN.md — Ingestion integrity hardening: content identity, atomic page writes, exact page mapping, and current Docling preset API

### Phase 2: Extraction & Compliance

**Goal**: Every ingested document has structured metadata extracted and validated, with compliance risk levels computed and stored
**Depends on**: Phase 1
**Requirements**: EXTRACT-01, EXTRACT-02
**Success Criteria** (what must be TRUE):

  1. System extracts doc_type, vendor_name, manufacturing_date, effective_date, revision_date, and expiry_date from each document into a Pydantic-validated model
  2. Each extracted field includes a verbatim source text span and source page reference
  3. Each document is flagged green (<2yr), amber (2-3yr), or red (>3yr) based on document age, stored in the compliance database

**Plans**: 3 plans
Plans:

- [x] 02-01-PLAN.md — Strict fixed-six Gemini schema, bounded retry, July 2026 pricing, and thinking-token provenance
- [x] 02-02-PLAN.md — Manifest-bound per-document run lifecycle, migrations, safe batch failure, and resumability
- [x] 02-03-PLAN.md — Literal grounding, conservative visual review, deterministic risk, completed-run eval provenance, and full gates

### Phase 2.1: Submission Baseline Recovery (INSERTED)

**Goal**: A clean checkout reproduces the public benchmark and passes required offline verification before further tuning
**Depends on**: Phase 2
**Requirements**: SUBMIT-01, SUBMIT-02, SUBMIT-08
**Success Criteria**:
  1. Complete specifications, manifests, licensed rendering assets and frozen splits are tracked; deterministic benchmark check passes on Windows.
  2. Required offline tests pass with sockets blocked and zero unexpected skips/xpasses; optional live/model/GPU gates are separate.
  3. Clean locked install and public development smoke path pass without private data; existing worktree changes are preserved.
  4. Completed 03-00 prerequisites are reconciled with evidence so Phase 3 does not regenerate the frozen corpus.
**Plans**: 0 plans; run `/gsd-plan-phase 2.1` using phase-local CONTEXT.md.

### Phase 3: Retrieval & RAG Chatbot

**Goal**: Users can ask natural-language questions about the document corpus and receive grounded answers with page-level citations
**Depends on**: Phase 2.1
**Requirements**: RETRIEVE-01, RETRIEVE-02, RETRIEVE-03, RAG-01, RAG-02
**Success Criteria** (what must be TRUE):

  1. Text chunks (~500 tokens) are indexed in Qdrant with both BM25 sparse vectors and BGE-large dense vectors in the sdf_text_chunks collection
  2. Retrieval fuses BM25 and dense candidates via RRF and re-ranks with a cross-encoder
  3. User can ask a question in the Chat tab and receive an answer with document filename and page number citations
  4. System returns "I don't have enough information to answer reliably" when retrieval confidence is low instead of generating unsupported answers

**Plans**:

- [ ] 03-00-PLAN.md — Nyquist network/no-skip controls and pre-tuning freeze of `sdf-synthetic-v1`
- [ ] 03-01-PLAN.md — RAGAS dependency isolation, stable chunks, and atomic named-vector Qdrant indexing
- [ ] 03-02-PLAN.md — BM25+BGE hybrid query, RRF/cross-encoder reranking, and calibrated evidence gate
- [ ] 03-03-PLAN.md — Strict claim-grounded Gemini output and bounded deterministic LangGraph answering
- [ ] 03-04-PLAN.md — Mandatory 900-row offline replay seal, public metrics, coverage, and regression gates
- [ ] 03-05-PLAN.md — Real-model/Gemini/RAGAS/adjudication live seal and redacted publishable report

**Submission planning input**: SUBMISSION-READINESS.md. Reconcile 03-00 after recovery; preserve existing CONTEXT/AI-SPEC gates and replan only affected unexecuted work.

### Phase 4: Dashboard & Evaluation

**Goal**: Compliance officers can see all documents in a sortable, color-coded table and the eval harness validates pipeline quality against a gold set
**Depends on**: Phase 2, Phase 3
**Requirements**: DASH-01, DASH-02, EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, SUBMIT-04
**Success Criteria** (what must be TRUE):

  1. Streamlit Compliance tab displays a sortable table with filename, doc type, vendor, revision date, document age, risk flag, confidence score, and source page link for all ingested documents
  2. Risk levels are color-coded red/amber/green inline in the table matching the EXTRACT-02 thresholds
  3. A hand-labeled gold set of ~50 pages exists with an annotation guide covering all document types and extraction fields
  4. Eval harness reports extraction F1 per field, retrieval recall@5, RAGAS faithfulness/relevancy scores, and latency p50/p95 and cost-per-query

**Plans**: TBD
**UI hint**: yes

**Submission acceptance additions**: Isolated evaluation-run identities (including >100 rows), measured end-to-end latency/usage, document-type classification and stratified quality, honest missing metrics, and empty/error/source-preview UAT. Read phase-local CONTEXT and SUBMISSION-READINESS.md.

### Phase 5: Visual Retrieval & Critic Extraction

**Goal**: Existing ColQwen2 visual retrieval foundation is verified on a real GPU with reproducible model/index/ranking evidence; deferred critic and runtime integration are owned by 5.1
**Depends on**: Phase 4
**Requirements**: VISUAL-01; VISUAL-02 foundation evidence (integration closes in 5.1)
**Success Criteria** (what must be TRUE):

  1. Each page image is indexed in Qdrant sdf_page_images collection with ColQwen2.5 embeddings (full multivector with HNSW disabled, plus mean-pooled row and column vectors with HNSW enabled)
  2. Visual retrieval uses two-stage strategy (mean-pooled HNSW prefetch then full multivector MaxSim reranking) fused with Phase 1 text retrieval results
  3. A fresh GPU run exports clean load report, model/environment/index identity and per-query ranks from the submitted revision.
  4. Historical tuned 17-query results are labeled exploratory; no untouched holdout quality claim is inferred.

**Plans**: 4 historical plans plus 05-05 follow-up summary (this slice covers the VISUAL RETRIEVAL TIER — VISUAL-01, VISUAL-02 — only; EXTRACT-03/04 critic-extraction are split into a follow-up phase per 05-CONTEXT.md Deferred Ideas)
Plans:

- [x] 05-01-PLAN.md — Visual tier foundation: visual_index_runs schema, pure Qdrant collection-config + row/col pooling + blob decode + upsert-payload builders, gpu marker (offline-testable)
- [x] 05-02-PLAN.md — Two-stage query payload builder, RRF (k=60) fusion → RetrievalHit, versioned visual run persistence (offline-testable)
- [x] 05-03-PLAN.md — Integration: retrieval_mode config (text-only|visual-fused), retriever fusion seam, source-tag extension, rq_ex3 gold mojibake repair, privacy allowlist proof
- [x] 05-04-PLAN.md — GPU embedder lazy seam + committed Colab L4 notebook deliverable (real VISUAL-01/02 numbers; Example-3 proof) — autonomous: false (Manual-Only Colab run)

Historical follow-up: 05-05-SUMMARY.md records loader/OCR/fusion rescue; no 05-05-PLAN.md exists. Revalidation must inspect that evidence explicitly.

**Reconciliation**: Historical title retained. Verify the existing foundation rather than rebuilding it. The existing deferred critic/confidence and demo runtime wiring are now explicitly owned by 5.1. Fresh GPU evidence remains required.

### Phase 5.1: Visual Integration and Extraction Assurance (INSERTED)

**Goal**: Normal Chat uses the real visual backend and uncertain extracted fields receive bounded image critique with honest confidence
**Depends on**: Phase 5
**Requirements**: VISUAL-02, EXTRACT-03, EXTRACT-04, SUBMIT-03 (visual)
**Success Criteria**:
  1. Scanned development page -> real ColQwen/Qdrant retrieval -> verified evidence -> normal answer service -> source preview succeeds without notebook-only monkeypatches.
  2. Missing GPU/index and stale corpus produce explicit behavior, never synthetic visual scores.
  3. Image critic and reconciliation are bounded to two iterations; uncertain fields retain evidence and become review items.
  4. Confidence inputs are verified before implementing the existing formula; unavailable logprobs require explicit contract resolution, not invented values.
**Plans**: 0 plans; plan using phase-local CONTEXT and SUBMISSION-READINESS.md.

### Phase 6: Agentic RAG & Observability

**Goal**: RAG chatbot uses an agentic pipeline with self-critique, low-confidence extractions surface for human review, and all operations are traced for auditability
**Depends on**: Phase 5.1
**Requirements**: HITL-01, RAG-03, OBS-01, SUBMIT-03 (complete workflow)
**Success Criteria** (what must be TRUE):

  1. RAG chatbot uses LangGraph agentic pipeline: query decomposition, retrieve, evaluate quality, re-retrieve if insufficient (max 2 retries), draft, self-critique for faithfulness, regenerate or abstain (max 1 regen)
  2. Dashboard HITL tab surfaces low-confidence extractions for human review and corrections update the compliance database
  3. All agent steps, LLM calls, retrievals, and extractions are traced in Langfuse with a phase tag on every trace session
  4. System abstains rather than hallucinating when confidence is insufficient across both extraction and RAG pathways

**Plans**: TBD
**UI hint**: yes

**Submission acceptance additions**: Full-document workflow and recovery/resume UAT, source-inspected corrections with history, real sanitized traces; reuse Phase 3 graph and rerun earlier quality/latency gates after agent changes.

### Phase 7: Benchmark & Polish

**Goal**: A reproducible complete demo with honest baseline/upgraded results, accessible Colab and recorded walkthrough, architecture diagrams and engineering design documentation
**Depends on**: Phase 6
**Requirements**: BENCH-01, BENCH-02, POLISH-01, POLISH-02, POLISH-03, SUBMIT-05, SUBMIT-06, SUBMIT-07, SUBMIT-08
**Success Criteria** (what must be TRUE):

  1. Eval harness runs both Phase 1 and Phase 2 pipelines on the same gold set (via pipeline config flag) and reports mean +/- stddev across 3 runs per metric
  2. Dashboard Eval tab shows Phase 1 vs Phase 2 side-by-side comparison table (extraction F1, recall@5, faithfulness, latency, cost)
  3. Architecture diagrams illustrating both Phase 1 and Phase 2 pipeline data flows exist in the project
  4. A recorded demo walkthrough and an engineering design doc with key decisions and trade-offs section are complete

**Plans**: TBD
**UI hint**: yes

**Submission acceptance additions**:
- Fresh Colab starts from permitted PDFs and a pinned submitted revision, runs the complete workflow and user interaction without the developer database.
- Final integrated revision passes the existing holdout contract with real cost/latency, isolated runs, sample counts and fingerprints. Missing live evidence blocks release.
- Repository, notebook, report and actual video links work for the intended reviewer; documentation discloses API data flow and limitations.
- See SUBMISSION-READINESS.md for the complete release checklist and video requirements.

## Progress

**Execution Order:**
Remaining route: 2.1 -> 3 -> 4 -> 5 (foundation verification/gaps) -> 5.1 -> 6 -> 7. Phases 1 and 2 retain historical completion and are revalidated in the final integrated run.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Ingestion | 4/4 | Complete    | 2026-07-12 |
| 2. Extraction & Compliance | 3/3 | Complete | 2026-07-15 |
| 2.1. Submission Baseline Recovery | 0/TBD | Ready to plan | - |
| 3. Retrieval & RAG Chatbot | 0/6 verified | Partially implemented; reconcile 03-00 | - |
| 4. Dashboard & Evaluation | 0/TBD | Not started | - |
| 5. Visual Retrieval & Critic Extraction | 4/4 historical + follow-up | Fresh GPU verification required | - |
| 5.1. Visual Integration and Extraction Assurance | 0/TBD | Context ready | - |
| 6. Agentic RAG & Observability | 0/TBD | Not started | - |
| 7. Benchmark & Polish | 0/TBD | Not started | - |
