# Requirements — Pfizer SDF Intelligence System

**Version:** v1 (Phase 1 + Phase 2 + Phase 3)
**Last updated:** 2026-09-22 (submission acceptance added; historical implementation status is not release verification)

---

## v1 Requirements

### Ingestion

- [x] **INGEST-01**: User can point the CLI at a folder of pharmaceutical PDFs and ingest them into the document store using Docling (v2.72+, Granite-Docling-258M) — handling scanned, stamped, and complex-table PDFs
- [x] **INGEST-02**: System renders each page as a 150 DPI PNG thumbnail and stores alongside extracted text (required for source-page links and Phase 2 visual retrieval)

### Extraction

- [ ] **EXTRACT-01**: System extracts structured metadata from each document — doc_type, vendor_name, manufacturing_date, effective_date, revision_date, expiry_date — into a Pydantic-validated model with a verbatim source text span and source page reference per field
- [ ] **EXTRACT-02**: System flags each document with a compliance risk level based on document age: green (<2 years), amber (2–3 years), red (>3 years), stored alongside extracted fields

### Retrieval

- [ ] **RETRIEVE-01**: System indexes extracted text chunks (~500 tokens) with BM25 sparse vectors (bm25s) in Qdrant (`sdf_text_chunks` collection, versioned)
- [ ] **RETRIEVE-02**: System indexes text chunks with dense vectors (BGE-large-en-v1.5, 1024-dim) in the same Qdrant collection
- [ ] **RETRIEVE-03**: System fuses BM25 and dense candidate sets via RRF and re-ranks top candidates with a cross-encoder (MS-MARCO MiniLM-L-6-v2)

### RAG Chatbot

- [ ] **RAG-01**: User can ask natural-language questions about the document corpus and receive answers with page-level citations (doc filename + page number) using a linear retrieve → prompt → answer pipeline
- [ ] **RAG-02**: System abstains (returns "I don't have enough information to answer reliably") rather than generating unsupported answers when retrieval confidence is low

### Dashboard

- [ ] **DASH-01**: Streamlit dashboard displays a sortable compliance table showing: filename, doc type, vendor, revision date, document age, risk flag (color-coded), confidence score, and source page link — for all ingested documents
- [ ] **DASH-02**: Risk levels are color-coded red/amber/green per EXTRACT-02 rules, visible inline in the compliance table

### Evaluation

- [ ] **EVAL-01**: Project maintains a hand-labeled gold set of ~50 pages covering all document types and extraction fields, with a written annotation guide ensuring consistent labeling
- [ ] **EVAL-02**: Eval harness computes extraction F1 (precision/recall) per field against the gold set
- [ ] **EVAL-03**: Eval harness computes retrieval recall@5 (are relevant pages in the top 5 retrieved?) against the gold set
- [ ] **EVAL-04**: Eval harness computes RAGAS faithfulness and answer relevancy scores for RAG answers against gold-set questions
- [ ] **EVAL-05**: Eval harness measures latency p50/p95 and cost-per-query for the full extraction + retrieval + answer pipeline

---

## v2 Requirements (Phase 2 — Differentiated Upgrade)

- [ ] **VISUAL-01**: System indexes each page image with ColQwen2.5-v0.2 embeddings (three named Qdrant vectors: full multivector with HNSW disabled, mean-pooled rows, mean-pooled columns) in a versioned `sdf_page_images` collection
- [ ] **VISUAL-02**: Retriever uses a two-stage ColQwen2 strategy: mean-pooled HNSW prefetch → full multivector MaxSim reranking — fused with Phase 1 text retrieval candidates
- [ ] **EXTRACT-03**: Extraction uses a critic/reflection loop — extractor proposes fields, critic re-reads the source page image and challenges each claim, disagreements trigger a reconciliation pass (hard cap: 2 iterations)
- [ ] **EXTRACT-04**: System computes a per-field confidence ensemble score: `0.4 × logprob + 0.4 × self-consistency(k=3) + 0.2 × critic_agreement`; fields below threshold (default 0.75) are routed to the HITL review queue
- [ ] **HITL-01**: Dashboard HITL tab surfaces low-confidence extractions for human review and correction; corrections update the Compliance DB
- [ ] **RAG-03**: RAG chatbot uses a LangGraph agentic pipeline: decompose query → retrieve → evaluate retrieval quality → re-retrieve if insufficient (≤2 retries) → draft answer → self-critique for faithfulness → regenerate or abstain (≤1 regen)
- [ ] **OBS-01**: All agent steps, LLM calls, retrievals, and extractions are traced in Langfuse (v3, pinned <4.0) with `phase` tag on every trace session

---

## v3 Requirements (Phase 3 — Benchmark + Polish)

- [ ] **BENCH-01**: Eval harness runs both Phase 1 and Phase 2 pipelines on the same gold set (via `pipeline: phase1 | phase2` config flag) and reports mean ± stddev across 3 runs per metric
- [ ] **BENCH-02**: Dashboard includes an Eval tab showing Phase 1 vs Phase 2 side-by-side comparison table (extraction F1, recall@5, faithfulness, latency, cost)
- [ ] **POLISH-01**: Project includes architecture diagrams illustrating the Phase 1 and Phase 2 pipeline data flows
- [ ] **POLISH-02**: Project includes a recorded demo walkthrough
- [ ] **POLISH-03**: Project includes an engineering design doc with key decisions and trade-offs section

---

## Out of Scope

- **Non-PDF formats** (Word, Excel, images) — PDF-only for this project
- **Production deployment / hosting** — demo system only, not live infrastructure
- **Authentication / RBAC / multi-tenancy** — single-user demo
- **Incremental re-ingest (change detection)** — full ingest on each run is acceptable for demo scale
- **Streaming responses in chat** — full response delivery is sufficient for demo
- **Write-back to source systems** — read-only, no SAP/Ariba integration
- **CAPA auto-creation / regulatory submission generation** — out of scope
- **Source page thumbnails with highlighted extraction regions** — page-level citation only (may revisit in Phase 2 if bbox implementation proves reliable)
- **ColQwen2 bounding-box citations** — separate VLM pass for field-level bbox is Phase 2 optional; fall back to page-level if crop-verify < 0.9 (see Open Question Q6)
- **Model fine-tuning** — API/pretrained models only
- **Langfuse v4 migration** — explicit tech-debt; address post-project

---

## Traceability

| Requirement | Version | Roadmap Phase | Status |
|-------------|---------|---------------|--------|
| INGEST-01 | v1 | Phase 1: Foundation & Ingestion | Complete |
| INGEST-02 | v1 | Phase 1: Foundation & Ingestion | Complete |
| EXTRACT-01 | v1 | Phase 2: Extraction & Compliance | Pending |
| EXTRACT-02 | v1 | Phase 2: Extraction & Compliance | Pending |
| RETRIEVE-01 | v1 | Phase 3: Retrieval & RAG Chatbot | Pending |
| RETRIEVE-02 | v1 | Phase 3: Retrieval & RAG Chatbot | Pending |
| RETRIEVE-03 | v1 | Phase 3: Retrieval & RAG Chatbot | Pending |
| RAG-01 | v1 | Phase 3: Retrieval & RAG Chatbot | Pending |
| RAG-02 | v1 | Phase 3: Retrieval & RAG Chatbot | Pending |
| DASH-01 | v1 | Phase 4: Dashboard & Evaluation | Pending |
| DASH-02 | v1 | Phase 4: Dashboard & Evaluation | Pending |
| EVAL-01 | v1 | Phase 4: Dashboard & Evaluation | Pending |
| EVAL-02 | v1 | Phase 4: Dashboard & Evaluation | Pending |
| EVAL-03 | v1 | Phase 4: Dashboard & Evaluation | Pending |
| EVAL-04 | v1 | Phase 4: Dashboard & Evaluation | Pending |
| EVAL-05 | v1 | Phase 4: Dashboard & Evaluation | Pending |
| VISUAL-01 | v2 | Phase 5: Visual Retrieval & Critic Extraction | Pending |
| VISUAL-02 | v2 | Phase 5: Visual Retrieval & Critic Extraction | Pending |
| EXTRACT-03 | v2 | Phase 5.1: Visual Retrieval & Critic Extraction | Pending |
| EXTRACT-04 | v2 | Phase 5.1: Visual Retrieval & Critic Extraction | Pending |
| HITL-01 | v2 | Phase 6: Agentic RAG & Observability | Pending |
| RAG-03 | v2 | Phase 6: Agentic RAG & Observability | Pending |
| OBS-01 | v2 | Phase 6: Agentic RAG & Observability | Pending |
| BENCH-01 | v3 | Phase 7: Benchmark & Polish | Pending |
| BENCH-02 | v3 | Phase 7: Benchmark & Polish | Pending |
| POLISH-01 | v3 | Phase 7: Benchmark & Polish | Pending |
| POLISH-02 | v3 | Phase 7: Benchmark & Polish | Pending |
| POLISH-03 | v3 | Phase 7: Benchmark & Polish | Pending |


## Submission acceptance requirements (2026-09-22)

These supplement, not replace, the original requirements. See SUBMISSION-READINESS.md for exact evidence and acceptance contracts. Existing checked implementation items do not substitute for final integrated verification. VISUAL-02 is reopened because a notebook fusion seam is not yet ordinary Chat integration. Extraction Phase 2 has implementation summaries; fresh release-quality evidence remains pending.

- [ ] **SUBMIT-01**: Clean locked install and required offline tests pass on Windows; explicit optional live/model/GPU gates, no unexpected skips/xpasses or outbound network in the offline gate.
- [ ] **SUBMIT-02**: Complete public licensed synthetic corpus/specifications/manifests reproduce; development and frozen holdout remain separated under the existing Phase 3 contract.
- [ ] **SUBMIT-03**: A fresh full SDF packet flows through ingestion, document-type classification, extraction, risk, retrieval, grounded Chat, source inspection and review/recovery; visual mode uses an actual backend.
- [ ] **SUBMIT-04**: Evaluation observations are scoped uniquely to an evaluation run with complete counts; classification, field extraction, retrieval, claims/citations, abstention, failure rates, full latency and measured usage/cost are reproducible across document types/modes.
- [ ] **SUBMIT-05**: Fresh Colab executes the complete workflow from permitted PDFs at an explicit release revision, without the developer's database, hidden patches or cached setup.
- [ ] **SUBMIT-06**: Final baseline/upgraded comparison and existing quality gates are measured from the integrated revision using isolated repeated runs, frozen data and real model/provider evidence with complete provenance.
- [ ] **SUBMIT-07**: Reviewer can access the actual walkthrough video, repository, Colab and results; recording demonstrates full-document processing, source evidence, abstention, metrics and limitations.
- [ ] **SUBMIT-08**: README/design/architecture/setup accurately describe behavior, model/runtime requirements and external API data flow; release identity and public artifacts are coherent and confidential data/secrets are excluded.

| Requirement | Implementation owner | Final verification |
|-------------|----------------------|--------------------|
| SUBMIT-01 | 2.1 | 7 |
| SUBMIT-02 | 2.1 | 3 and 7 |
| SUBMIT-03 | 3 text; 5.1 visual; 6 complete workflow | 7 |
| SUBMIT-04 | 4 | 7 |
| SUBMIT-05 | 7 | 7 fresh-session UAT |
| SUBMIT-06 | 7 (reuses 3/4 gates) | 7 |
| SUBMIT-07 | 7 | 7 playback/access check |
| SUBMIT-08 | 2.1 initial corrections; 7 final package | 7 |

Original EXTRACT-03/04 are owned by Phase 5.1, following the explicit deferral in 05-CONTEXT.md. VISUAL-01 foundation is verified in 5; VISUAL-02 integration closes in 5.1. Original numerical Phase 3 gates are unchanged. Any confidence-formula or gate amendment must be explicit before affected implementation/evaluation, never silently weakened to pass.
