# Phase 3 Context — Retrieval & RAG Chatbot

**Captured:** 2026-07-15  
**Mode:** autonomous / decisions delegated by project owner

## Phase Boundary

Deliver a locally operational, benchmarkable hybrid text retriever and grounded question-answering path that preserves page provenance and fails closed. This phase satisfies RETRIEVE-01/02/03 and RAG-01/02. It does not implement the open-ended decomposition/self-critique agent in RAG-03, production authentication, or regulated-system validation.

## Locked Decisions

- Preserve the existing `retrieve_evidence(...)`, `answer_question(...)`, `AnswerResult`, and Streamlit Chat contracts while replacing their internals.
- Use deterministic ~500-token, page-bounded chunks with stable IDs, offsets, hashes, and 50-token overlap.
- Store named BM25 sparse and BGE-large-en-v1.5 1024-d vectors in versioned Qdrant collection `sdf_text_chunks`.
- Fuse sparse and dense candidate ranks with RRF, then re-rank a bounded union using `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- Use local embedded Qdrant by default and dependency-injected in-memory/fake model adapters for offline tests. Demo/release mode may never silently substitute fake embeddings.
- Implement Phase 3's linear answer path as a fixed LangGraph 1.2.9 graph with deterministic routing, one retrieval refinement maximum, one structured generation call maximum, and no model-controlled loops or tools.
- Gemini output is a strict Pydantic claim schema. Each claim selects request-local evidence IDs and supplies literal quotes. The server resolves citations and rejects the complete answer if any claim cannot be grounded.
- Canonical abstention is the only public outcome for insufficient, stale, contradictory, injected, malformed, timed-out, over-budget, or unprovable evidence. No partial answer is rendered.
- RAGAS 0.4.3 moves to an isolated `tools/ragas-eval` project; the application runtime uses current LangGraph/LangChain Core and direct `google-genai` nodes.
- Thresholds are calibrated only on development data, versioned, and hash-bound. Holdout examples are never used for tuning.
- Langfuse automatic input/output capture stays disabled. Trace metadata excludes raw questions, answers, document text/images, provider payloads, secrets, and full hashes.

## Release Gates

- Retrieval: recall@5 >= 0.95; recall@10 >= 0.98; nDCG@5 >= 0.90; bootstrap 95% lower bound for recall@5 >= 0.90.
- RAG: claim faithfulness >= 0.95; answer correctness >= 0.90; citation precision >= 0.98; citation completeness >= 0.95.
- Safety: abstention accuracy >= 0.95; unsupported-claim rate <= 0.02.
- Stability: three seeded runs, primary-metric SD <= 0.02.
- Performance: live warm p95 answer latency <= 6 seconds; each answer/abstention <= $0.01.
- Every score includes denominator, sample count, run mode, commit, environment, dataset/index/model/prompt/schema/config/scorer fingerprints, usage, and checksums.

## Deferred

- Visual ColQwen2.5 remains an optional GPU fusion seam; a visual-only hit cannot authorize a factual answer without verified text.
- RAG-03 query decomposition, model-based retrieval critique, and regeneration remain Phase 6.
- Click-through PDF page preview and broader dashboard design polish are Phase 4/release work; Phase 3 provides immutable citation DTO data.
- Any GxP/Part 11 validation, authentication, RBAC, multi-tenancy, and deployment are explicitly outside this demo.

## Implementation Freedom

Exact module boundaries, internal class names, migration details, batching, cache paths, and test fixture organization may follow existing repository patterns as long as the locked contracts and release gates above remain true.
