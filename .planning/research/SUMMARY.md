# Research Synthesis — Pfizer SDF Intelligence System

**Synthesized:** 2026-04-16
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md
**Overall confidence:** HIGH on stack and architecture; MEDIUM-HIGH on domain features and pitfalls.

## Executive Summary

The Pfizer SDF Intelligence System is a **layout-aware pharmaceutical document intelligence pipeline** that ingests mixed scanned/stamped PDFs (CoAs, vendor certs, compliance forms), extracts regulated metadata (vendor, dates, lot numbers) with per-field confidence, flags compliance risk, and answers grounded natural-language questions with page-level citations.

The research converges on a well-established "2026 playbook": **Docling + Granite-Docling VLM** for parsing, **ColQwen2.5 + Qdrant two-stage multivector retrieval** for visual RAG, **LangGraph** for the Phase 2 agentic critic/reflection loop, **Langfuse v3** for audit-grade observability, and **RAGAS** for eval. Gemini 2.5 Flash is the default VLM (~35x cheaper than Claude for bulk extraction); Claude Sonnet 4.6 is reserved as critic/final-answer model.

The **core architectural discipline** is that Phase 2 *adds* components behind Protocol-based interfaces — it does not rewrite Phase 1. This enables a real head-to-head benchmark (Phase 3) on the same gold set and the same Langfuse project, with a config flag selecting `single_pass | critic_loop` / `hybrid_text | hybrid_text_visual` / `linear | agentic`.

The biggest risks are not technical novelty but **discipline**: VLM hallucination on stamped/rotated pharma PDFs, ColQwen2 VRAM/HNSW mis-configuration, Colab session death mid-index, self-correction fallacy in the critic loop, and gold-set annotation instability. All have well-defined mitigations that must be baked in from Phase 1.

## 1. Recommended Stack (Top 10 Pinned)

| # | Component | Version | Rationale |
|---|-----------|---------|-----------|
| 1 | **Python** | `3.11.x` | Docling 2.70+ dropped 3.9; 3.13+ has ML wheel gaps |
| 2 | **docling** | `>=2.72,<3.0` | Layout-aware PDF SDK; 97.9% table accuracy; Granite-Docling-258M for scanned docs |
| 3 | **colpali-engine** | `>=0.3.11,<0.4` | Required floor for ColQwen2.5-v0.2 (current ViDoRe SOTA) |
| 4 | **qdrant-client** | `>=1.17.1,<2.0` | Native multivector + MaxSim + two-stage prefetch |
| 5 | **langgraph** | `>=1.1.0,<2.0` | Stateful graph with conditional edges |
| 6 | **langfuse** | `>=3.0,<4.0` | **Hard upper bound** — v4 (March 2026) is a breaking rewrite |
| 7 | **ragas** | `==0.4.3` | Exact pin — API-stable; 0.5.x churn ongoing |
| 8 | **streamlit** | `>=1.56,<2.0` | Supports pandas 3.x + rich `column_config` |
| 9 | **pydantic** | `>=2.8` | v1 EOL; models double as structured-output schemas |
| 10 | **bm25s** + **sentence-transformers** (BGE-large-en-v1.5) | latest | bm25s >> rank_bm25 on speed; BGE-large (1024-dim) for dense |

**LLMs:** `gemini-2.5-flash` for bulk extraction/judge ($0.15/M in); `claude-sonnet-4-6` for critic + final answer ($3/M in, reserved use only).
**Visual model:** `vidore/colqwen2.5-v0.2`. Requires **L4 GPU (22.5 GB) recommended**; T4 (15 GB) is marginal (batch_size=2, bf16).

## 2. Table-Stakes Features vs Differentiators

**Table Stakes (Phase 1) — demo fails without these:**
- PDF folder ingestion via Docling (handles scanned/stamped/complex tables)
- Core field extraction: doc_type, vendor, mfg_date, effective_date, revision_date, expiry_date
- Pydantic-validated schema with verbatim source spans (ALCOA++)
- Age/expiry risk flagging: `<2yr green` / `2-3yr amber` / `>3yr red`
- Sortable color-coded compliance table with source-page link
- Hybrid RAG chatbot (BM25 + dense + reranker) with page citations
- Eval harness on ~50-75 hand-labeled gold pages (F1, recall@5, faithfulness, latency, cost)

**Differentiators (Phase 2) — what wins the externship:**
- ColQwen2.5 visual retrieval: captures stamps/tables/handwritten annotations text pipelines miss
- Extraction critic loop with evidence-grounded reconciliation
- LangGraph agentic RAG: decompose/retrieve/evaluate/draft/critique/regenerate-or-abstain
- Per-field confidence ensemble (logprobs + self-consistency + critic agreement) → HITL queue
- Abstention on low confidence (pharma: wrong answer > no answer)
- Before/after benchmark dashboard on same corpus
- Full Langfuse trace with `phase` tag for auditability

**Anti-Features (deliberately not built):**
Auth/RBAC, multi-tenancy, supplier portal integrations, write-back to source systems, CAPA creation, non-PDF ingestion, model fine-tuning, regulatory submission generation, cron re-ingest, signature cryptographic validation.

## 3. Key Architectural Decisions

**3.1 Two Qdrant collections:**
- `sdf_text_chunks`: ~500-token chunks, dense (BGE-1024) + sparse (BM25) → RRF fusion for Phase 1 text RAG
- `sdf_page_images`: one point/page, three named vectors: `original` (full ColQwen2 multivector, **HNSW off** via `HnswConfigDiff(m=0)`) + `mean_pooling_rows` + `mean_pooling_cols` (pooled, HNSW on) for Phase 2 pooled-prefetch→MaxSim-rerank
- **Versioned collection names from day 1** (`sdf_pages_v2_colqwen`) — Qdrant vector configs are immutable

**3.2 Phase 1/2 Protocol abstraction (the benchmark enabler):**
Three swappable Protocol interfaces: `FieldExtractor`, `Retriever`, `Answerer`. Two implementations each. Config flag `pipeline: phase1 | phase2` selects preset. Phase 2 adds implementations — does **not** rewrite Phase 1.

**3.3 LangGraph state machine shape:**
`decompose → retrieve → evaluate`; if `insufficient` and `retry < 2` → rewrite + loop; else `draft → critique`; if `regen` and `retry < 1` → loop; else `finalize | abstain`. Hard caps: retrieve-retry ≤ 2, critique-regen ≤ 1, `recursion_limit=10`.

**3.4 Confidence ensemble:**
`conf = 0.4 × logprob + 0.4 × self_consistency(k=3, T=0.3) + 0.2 × critic_agreement`. HITL trigger at `conf < 0.75` (default; sidebar slider). Weights calibrated against gold set in Phase 3.

**3.5 Ingestion is offline CLI, not Streamlit-embedded.** Docling on a folder takes minutes; CLI (`python -m pipeline.ingest <folder>`) writes to doc store; Streamlit is read-only. Deterministic point IDs (hash of doc_path + page_num) = idempotent upserts.

## 4. Critical Pitfalls (Top 5)

| # | Pitfall | Phase | Prevention |
|---|---------|-------|------------|
| **C1** | ColQwen2 HNSW on multivectors → Qdrant OOM | P2 | `HnswConfigDiff(m=0)` on `original` vector; mean-pooled HNSW for first stage |
| **C3** | Docling memory leak → Colab OOM at ~30-50 docs | P1 | Recreate converter per doc; `gc.collect()` + `torch.cuda.empty_cache()`; `DOCFLOW_PDF_BACKEND=pypdfium2` |
| **C4** | VLM hallucinates plausible-but-wrong pharma fields | P1 | Schema requires `verbatim_text_span`; reject if span not fuzzy-found on page (threshold 0.85). Track `grounding_rate`. |
| **C5** | Critic loop worsens accuracy (self-correction fallacy) | P2 | Critic must re-read source page image; hard cap 2 iterations; **A/B gate**: only ship if delta-F1 > +3% |
| **C6** | Colab session dies mid-indexing | P1+P2 | Deterministic point IDs = idempotent upserts; persist Qdrant to Drive; checkpoint ingest manifest every 5 docs |

## 5. Roadmap — Suggested Phase Ordering

**Foundation (Phase 0):** Doc store + ingestion skeleton, Compliance DB schema (SQLite), Streamlit skeleton (3 tabs), Langfuse wired with `phase` tag.

**Phase 1 — Baseline end-to-end:**
Single-pass extractor (Gemini 2.5 Flash + Pydantic + verbatim spans) → compliance rules → dashboard table → `sdf_text_chunks` Qdrant collection → hybrid text RAG → Chat tab → gold set (50-75 pages) → eval harness v1.

**Phase 2 — Differentiated upgrade** *(run `/gsd-research-phase` at kickoff):*
`sdf_page_images` collection (m=0 HNSW) → ColQwen2.5 embedder → `HybridTextVisualRetriever` → `CriticLoopExtractor` (evidence-grounded, 2-iter cap) → confidence ensemble + HITL queue + abstention → `AgenticRAG` LangGraph StateGraph → bbox citations.

**Phase 3 — Benchmark + Polish:**
Eval harness v2 (both pipelines, 3-run average) → side-by-side eval dashboard → architecture diagrams → walkthrough recording → design doc.

## 6. Open Questions

| # | Question | When | How |
|---|----------|------|-----|
| Q1 | Gemini reliable enough on date fields, or elevate Claude there? | End P1 (gold-set eval) | Per-field F1; if Gemini < 0.90 on dates → Claude for those fields |
| Q2 | T4 viable for ColQwen2.5-v0.2 or must require L4? | Early P2 | 5-page smoke test on T4 with batch_size=2, bf16 |
| Q3 | Confidence ensemble weights (0.4/0.4/0.2) optimal? | P3 calibration | Sweep against gold-set HITL precision/recall |
| Q4 | Gold set 50 pages enough? | End P1 | Run eval twice; if variance > P2 delta → grow to 75-100 |
| Q5 | Risk thresholds Pfizer-specific tuning needed? | P1 demo review | Sidebar sliders; reviewer tunes live |
| Q6 | Bbox precision via separate VLM pass + layout snap achieves >0.9? | Mid-P2 | If not → fall back to page-level citation only |
