# Architecture Patterns

**Domain:** AI-powered pharmaceutical document intelligence (SDF compliance + hybrid/visual RAG)
**Researched:** 2026-04-16
**Overall confidence:** HIGH (Qdrant/ColQwen2, LangGraph, Langfuse, Docling patterns are all documented in official sources; confidence-score computation is MEDIUM)

---

## 1. System Overview (Recommended Architecture)

Seven loosely-coupled subsystems communicating through three shared artifacts: a **document store** (parsed `DoclingDocument` JSON + page images), a **Qdrant collection** (three named vectors + payload metadata), and a **SQLite/DuckDB metadata store** (compliance table, confidence, HITL queue, trace IDs).

```
                          ┌─────────────────────────────────────────┐
                          │   Streamlit UI (single process, 3 pages)│
                          │   - Compliance Dashboard                │
                          │   - Chatbot                             │
                          │   - Eval / Phase 1 vs Phase 2           │
                          └───────────────┬─────────────────────────┘
                                          │ (in-process Python calls)
        ┌─────────────────────────────────┼─────────────────────────────┐
        │                                 │                             │
        ▼                                 ▼                             ▼
┌───────────────┐               ┌──────────────────┐           ┌─────────────────┐
│  Ingestion    │               │  Retrieval /     │           │  Metadata /     │
│  Pipeline     │──writes──────▶│  RAG Orchestrator│◀──reads──▶│  Compliance DB  │
│ (Docling +    │               │  (LangGraph)     │           │  (SQLite)       │
│  Extractor)   │               └─────────┬────────┘           └─────────────────┘
└───────┬───────┘                         │
        │ writes                          │ queries
        ▼                                 ▼
┌──────────────────┐              ┌──────────────────┐
│ Doc Store        │              │  Qdrant          │
│ (parquet/JSON +  │              │  (named vectors) │
│  page images PNG)│              │                  │
└──────────────────┘              └──────────────────┘
        ▲                                 ▲
        │                                 │
┌───────┴───────┐              ┌─────────┴───────────┐
│  Indexer      │              │  Embedders          │
│  (BM25/dense/ │──writes─────▶│  - BGE/E5 dense txt │
│   ColQwen2)   │              │  - BM25 sparse      │
└───────────────┘              │  - ColQwen2 visual  │
                               └─────────────────────┘
                                          │
                                          ▼
                               ┌────────────────────────┐
                               │ Langfuse (SaaS/self-host)│
                               │   all spans traced      │
                               └────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Inputs | Outputs | Communicates With |
|-----------|---------------|--------|---------|-------------------|
| **Ingestion Pipeline** | Parse PDF → `DoclingDocument`, emit page images at 150 DPI | PDF path | `DoclingDocument` JSON, page PNGs | Doc Store (write) |
| **Extractor** | VLM field extraction (Pydantic) + confidence | `DoclingDocument`, page images | `ExtractedFields` record with per-field confidence | Compliance DB (write), Langfuse (trace) |
| **Critic** (Phase 2) | Re-read source page, challenge each claim, reconcile | `ExtractedFields` + page image | Revised fields + bounding-box citations | Compliance DB (update), Langfuse |
| **Indexer** | Chunk text, generate sparse/dense/visual embeddings, upsert | `DoclingDocument`, page PNGs | Qdrant points | Qdrant (write), Embedders |
| **Embedders** | Stateless wrappers for BGE/E5 (dense), BM25 (sparse), ColQwen2 (multivector) | text chunks / page images | vectors | called by Indexer and RAG Orchestrator |
| **RAG Orchestrator** | LangGraph state machine: decompose → retrieve → evaluate → draft → critique | user query | answer + citations | Qdrant, Extractor DB, Langfuse, VLM API |
| **Compliance DB** | Structured metadata, risk flags, confidence, HITL queue, eval results | writes from extractor/critic | reads by UI | Streamlit |
| **Streamlit UI** | Three pages (Dashboard / Chat / Eval) | user clicks, query text | rendered UI | All backends (in-process) |
| **Langfuse** | Observability plane — traces every LLM/retrieval/extraction step | callback events | traces, sessions, scores | cross-cutting |

**Key boundary rule:** The **Ingestion Pipeline** is the only writer to Doc Store; the **Indexer** is the only writer to Qdrant; the **Extractor/Critic** are the only writers to the Compliance DB. The UI and RAG Orchestrator are **read-only** over these stores. This makes reindexing/reruns idempotent.

---

## 2. Data Flow: PDF → Streamlit Display

### 2a. Ingestion path (batch, offline)

```
PDF folder
   │
   ▼
[1] Docling DocumentConverter + VLM pipeline (Granite-Docling-258M)
   │   → produces DoclingDocument (Pydantic) with bboxes + provenance
   ▼
[2] Persist: write DoclingDocument JSON + rendered page PNGs (150 DPI) to doc_store/
   │
   ▼
[3] Field Extractor (Phase 1: single VLM pass; Phase 2: extractor + critic loop)
   │   → ExtractedFields(doc_type, vendor, mfg_date, effective_date,
   │                      revision_date, expiry_date,
   │                      per_field_confidence, per_field_bbox, source_page)
   ▼
[4] Compliance rule engine:
   │   age_years = today - revision_date
   │   risk = "red" if age_years > 3 else "amber" if age_years > 2 else "green"
   │   if any field.confidence < τ → hitl_queue = true
   ▼
[5] Write row to compliance_documents table (SQLite)
   │
   ▼
[6] Indexer in parallel:
   │   - Text chunks (500 tok, 100 overlap) → BM25 sparse + BGE dense
   │   - Page images → ColQwen2 multivectors + two mean-pooled projections
   │   - Upsert to Qdrant with payload {doc_id, page, chunk_id, text, bbox}
   ▼
[7] Trace entire ingestion session to Langfuse
```

### 2b. Query path (online, per user request)

```
User query in Streamlit
   │
   ▼
[1] LangGraph graph.invoke(query, config={"callbacks": [langfuse_handler]})
   │
   ▼
[2] Decompose node → sub-queries
   │
   ▼
[3] Retrieve node → hybrid Qdrant query (BM25 + dense + ColQwen2 rerank)
   │
   ▼
[4] Evaluate node (LLM grader) → sufficient? if no, rewrite query → loop
   │
   ▼
[5] Draft node → candidate answer with citations
   │
   ▼
[6] Critique node (faithfulness check) → if hallucination → regenerate
   │
   ▼
[7] Return {answer, citations[{doc_id, page, bbox}], confidence}
   │
   ▼
[8] Streamlit renders answer + clickable citations → open page image w/ bbox overlay
```

---

## 3. Qdrant Collection Schema (Hybrid Retrieval)

**Recommendation:** Two collections, not one. Text chunks and page images have different cardinalities (many chunks per page) and should be queried independently, then fused in the LangGraph retrieval node.

### Collection A: `sdf_text_chunks`

One point per text chunk (~500 tokens).

```python
client.create_collection(
    "sdf_text_chunks",
    vectors_config={
        "dense": VectorParams(size=1024, distance=Distance.COSINE),   # BGE-large-en-v1.5
    },
    sparse_vectors_config={
        "bm25": SparseVectorParams(modifier=Modifier.IDF),
    },
)
# Payload: {doc_id, page, chunk_id, text, bbox, doc_type, vendor, revision_date}
```

Query uses Qdrant's `query_points` with two prefetches fused by RRF:

```python
client.query_points(
    "sdf_text_chunks",
    prefetch=[
        Prefetch(query=dense_q, using="dense", limit=40),
        Prefetch(query=sparse_q, using="bm25", limit=40),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=20,
)
```

### Collection B: `sdf_page_images` (Phase 2)

One point per PDF page. Uses Qdrant's documented ColPali/ColQwen2 optimization pattern with three named vectors: original multivector (reranking only, HNSW off) + two mean-pooled projections (first-stage, HNSW on).

```python
client.create_collection(
    "sdf_page_images",
    vectors_config={
        "original": VectorParams(
            size=128,
            distance=Distance.COSINE,
            multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
            hnsw_config=HnswConfigDiff(m=0),   # disabled — reranking only
        ),
        "mean_pooling_rows": VectorParams(
            size=128, distance=Distance.COSINE,
            multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
        ),
        "mean_pooling_columns": VectorParams(
            size=128, distance=Distance.COSINE,
            multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
        ),
    },
)
# Payload: {doc_id, page, page_image_path, ocr_text_hint, doc_type, vendor}
```

Query:

```python
client.query_points(
    "sdf_page_images",
    prefetch=[
        Prefetch(query=colqwen_q, using="mean_pooling_rows", limit=100),
        Prefetch(query=colqwen_q, using="mean_pooling_columns", limit=100),
    ],
    query=colqwen_q,
    using="original",        # MaxSim reranking
    limit=10,
)
```

**Rationale for splitting collections:** Different vector dimensions, different HNSW configurations, different payload shapes, and different update cadences (text chunks may be re-chunked without re-embedding images). Fusion happens at the application layer, not inside Qdrant.

---

## 4. ColQwen2 Mean-Pool HNSW + Multivector Late-Interaction Reranking (How It Actually Works)

### The trade-off this solves

ColQwen2 emits ~1024 patch-level vectors **per page**. Storing them all in an HNSW graph blows up memory (tens of MB/page) and slows query (MaxSim over 1024 × N vectors). But throwing them away loses the late-interaction quality that makes ColQwen2 better than a single dense vector.

### The two-stage pattern

**Stage 1 — Shortlist via pooled vectors (HNSW, fast):**
ColQwen2's patches form a 2D grid (rows × cols of image patches). Average the patch vectors row-wise → a short multivector (~32 row vectors). Do the same column-wise → another short multivector. Index both with HNSW. At query time, send the full query multivector against each pooled index with MaxSim and take top-100 candidates from each.

**Stage 2 — Rerank via full multivectors (no HNSW, precise):**
The `original` named vector holds the full ~1024 patch vectors per point but has `hnsw_config=HnswConfigDiff(m=0)` — the graph is disabled, points are stored but not indexed for ANN. Qdrant loads the full multivectors only for the 100-200 prefetched candidates and computes full MaxSim against the query. Result: ~13× speedup vs. indexing full multivectors directly, with NDCG@20 ≈ 0.952 (nearly identical to full-resolution).

### Conceptual flow

```
query image/text
    │
    ▼
ColQwen2 → ~20 query patch vectors
    │
    ├──────────▶ row-pooled HNSW search → 100 pages
    │                                         │
    ├──────────▶ col-pooled HNSW search → 100 pages
    │                                         │
    │              (union, dedup) ───────────┤
    │                                         ▼
    └──────────▶ MaxSim rerank against "original" full multivectors for union
                          │
                          ▼
                      top-10 pages
```

### What the query node emits to the draft node

For each of the top-10 pages: `{doc_id, page_num, page_image_path, text_overlap_chunks[], score}`. The text chunks are pulled from `sdf_text_chunks` filtered by `doc_id + page_num` so the draft LLM gets both the image and the OCR'd text for grounding.

---

## 5. LangGraph State Machine

### State definition

```python
class RAGState(TypedDict):
    original_query: str
    sub_queries: list[str]
    retrieved: list[Candidate]      # {doc_id, page, bbox, text, score, modality}
    retrieval_verdict: Literal["sufficient", "insufficient", "empty"]
    retry_count: int                # guard against infinite loops
    draft: str
    critique: FaithfulnessReport    # {unsupported_claims: [...], verdict: ok|regen|abstain}
    final_answer: str
    citations: list[Citation]
    confidence: float               # abstention threshold
```

### Node graph

```
         ┌───────────┐
   START │ decompose │
         └─────┬─────┘
               ▼
         ┌───────────┐
   ┌────▶│ retrieve  │─────────┐
   │     └─────┬─────┘         │
   │           ▼               │
   │     ┌───────────┐         │
   │     │  evaluate │         │
   │     └─────┬─────┘         │
   │           │               │
   │      insufficient         │
   │      (retry<2)?──────YES──┘
   │           │
   │          NO
   │           ▼
   │     ┌───────────┐
   │     │   draft   │
   │     └─────┬─────┘
   │           ▼
   │     ┌───────────┐
   │     │ critique  │
   │     └─────┬─────┘
   │           │
   │      unsupported
   │      (retry<1)?
   │           │
   ├───YES─────┤
   │           NO
   │           ▼
   │     ┌───────────┐
   │     │  finalize │──▶ END
   │           (or abstain if low confidence)
```

### Edge policies

- **decompose → retrieve:** always
- **retrieve → evaluate:** always
- **evaluate → retrieve** (conditional): if `retrieval_verdict == "insufficient"` and `retry_count < 2`; increment retry and rewrite sub-queries
- **evaluate → draft:** otherwise
- **draft → critique:** always
- **critique → draft** (conditional): if `critique.verdict == "regen"` and `retry_count < 1`
- **critique → finalize:** if verdict ok, or retries exhausted → either emit final answer or set `confidence < τ` and abstain with "I cannot confirm this from the documents"

### Why LangGraph over vanilla chain

LangGraph's `StateGraph` with conditional edges gives explicit retry semantics and checkpointing — each node's state is observable in Langfuse as a distinct span, enabling per-step eval (recall@5, faithfulness, self-consistency) in Phase 3 benchmarking.

---

## 6. Phase 1 ↔ Phase 2 Abstraction Boundaries (A/B-able)

To produce airtight head-to-head numbers, define **protocol boundaries** — interfaces with two implementations each — rather than separate codebases.

### Three swappable interfaces

```python
# 1. Extraction strategy
class FieldExtractor(Protocol):
    def extract(self, doc: DoclingDocument) -> ExtractedFields: ...

class SinglePassExtractor(FieldExtractor):       # Phase 1
    ...
class CriticLoopExtractor(FieldExtractor):       # Phase 2
    def __init__(self, extractor, critic, reconciler): ...

# 2. Retrieval strategy
class Retriever(Protocol):
    def retrieve(self, query: str, k: int) -> list[Candidate]: ...

class HybridTextRetriever(Retriever):            # Phase 1: BM25 + dense + CE rerank
    ...
class HybridTextVisualRetriever(Retriever):      # Phase 2: + ColQwen2 pages, fused
    ...

# 3. Answering strategy
class Answerer(Protocol):
    def answer(self, query: str) -> AnswerWithCitations: ...

class LinearRAG(Answerer):                       # Phase 1: retrieve → generate
    ...
class AgenticRAG(Answerer):                      # Phase 2: LangGraph with critic loop
    ...
```

### Configuration switch

```python
# config.yaml
pipeline:
  extractor: single_pass | critic_loop
  retriever: hybrid_text | hybrid_text_visual
  answerer: linear | agentic
```

One CLI flag (`--pipeline phase1|phase2`) selects a preset. The eval harness (Phase 3) runs both presets on the same document set and writes results to a shared `eval_runs` table keyed by `(run_id, pipeline_label, metric, doc_id)` — giving a real delta, not a guess.

### What is NOT swappable (shared)

- Docling parsing output (identical `DoclingDocument` for both runs)
- Qdrant collections (both collections always populated; Phase 1 simply ignores `sdf_page_images`)
- Compliance DB schema (Phase 2 adds `critic_verdict`, `bbox_citation` columns; Phase 1 leaves null)
- Langfuse (same project, different `session_tags=["phase1"|"phase2"]`)
- Gold set and eval metrics

This is the **key architectural discipline:** Phase 2 adds components; it does not rewrite them. Phase 1 code stays in production and becomes the baseline.

---

## 7. VLM Confidence Scores (How to Compute & Store)

The Pfizer requirement is "per-field confidence" with HITL routing when low. Confidence from closed VLM APIs (Claude Sonnet, Gemini 2.5) is **not free** — the APIs do not return calibrated probabilities. Combine three signals.

### Signal 1 — Logprobs (where available)
Gemini 2.5 Flash and some Claude endpoints expose token-level logprobs. For a field that spans tokens `t_1..t_n`:
`conf_logprob = exp(mean(logprob(t_i)))`.
Fast, zero extra cost, but noisy on short/structured fields.

### Signal 2 — Self-consistency (Phase 2)
Run the extractor **k=3** times at temperature 0.3. For each field, take the mode; confidence = fraction of runs agreeing (3/3 = 1.0, 2/3 = 0.67). Catches failure modes logprobs miss (e.g., confidently wrong dates). Costs 3× tokens but runs in parallel.

### Signal 3 — Critic agreement (Phase 2)
Critic node re-reads the source page independently and scores each field `{agree, disagree, unclear}`. Final confidence:

```
conf = 0.4 * conf_logprob + 0.4 * conf_self_consistency + 0.2 * critic_agreement
```

(weights tuned against the gold set in Phase 3).

### Storage schema

```sql
CREATE TABLE extracted_fields (
    doc_id TEXT,
    field_name TEXT,
    value TEXT,
    confidence REAL,              -- 0..1 combined score
    conf_logprob REAL,
    conf_self_consistency REAL,
    critic_verdict TEXT,          -- agree|disagree|unclear|null (phase 1)
    source_page INTEGER,
    bbox TEXT,                    -- JSON [x0,y0,x1,y1] relative to page
    needs_review BOOLEAN,         -- conf < τ (τ=0.75 default)
    trace_id TEXT,                -- Langfuse trace for audit
    PRIMARY KEY (doc_id, field_name)
);

CREATE TABLE hitl_queue (
    doc_id TEXT, field_name TEXT,
    reason TEXT,                  -- 'low_confidence' | 'critic_disagreement'
    resolved BOOLEAN DEFAULT 0,
    human_value TEXT, resolved_at TIMESTAMP,
    PRIMARY KEY (doc_id, field_name)
);
```

Threshold τ is a config parameter; the Eval page lets you sweep τ and see precision/recall of the HITL trigger.

---

## 8. Langfuse Integration Pattern for LangGraph

### Pattern (official, verified)

```python
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()   # reads env: LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST

# Every LangGraph/LangChain invocation gets the handler in config
result = graph.invoke(
    {"original_query": user_query},
    config={
        "callbacks": [langfuse_handler],
        "configurable": {"session_id": st.session_state.session_id,
                         "user_id":    "demo_user"},
        "metadata": {"pipeline": "phase2", "doc_set_version": "v3"},
    },
)
```

### Session / trace hierarchy for this project

```
session_id = Streamlit chat session
  └─ trace: graph.invoke per user message
       ├─ span: decompose        (LLM call)
       ├─ span: retrieve         (2 sub-spans: text_retriever, visual_retriever)
       ├─ span: evaluate         (LLM call)
       ├─ span: retrieve (retry) (if triggered)
       ├─ span: draft            (LLM call)
       ├─ span: critique         (LLM call)
       └─ span: finalize
```

### Non-LangChain spans (ingestion, extraction)

For the batch ingestion pipeline (not a LangChain graph), use the Langfuse SDK `@observe()` decorator or manual `langfuse.trace()` context managers. Tag traces with `{"pipeline": "ingestion", "doc_id": ...}` so they show up in the same project as the RAG traces.

### Eval hooks

Phase 3's eval harness attaches scores post-hoc via `langfuse.score(trace_id=..., name="faithfulness", value=...)`. This lets you filter in the Langfuse UI by pipeline variant × metric and produces the Phase 1 vs Phase 2 leaderboard automatically.

---

## 9. Patterns to Follow

### Pattern: Protocol-based pluggable pipelines
Define `Protocol` classes for every stage that differs between Phase 1 and Phase 2. The orchestrator depends only on the protocol, not the implementation. Enables eval harness to instantiate `phase1_pipeline()` and `phase2_pipeline()` side by side.

### Pattern: Two-stage visual retrieval (mean-pool → multivector rerank)
Standard Qdrant recipe for ColQwen2. Never index full multivectors with HNSW.

### Pattern: Shared state TypedDict in LangGraph
All nodes read/write a single `RAGState` dict. No direct node-to-node calls. Makes retry/conditional logic declarative.

### Pattern: Write-once doc store, rebuildable indices
Docling output and page PNGs are canonical. Qdrant and the Compliance DB can both be dropped and rebuilt from Doc Store alone. Enables cheap re-indexing when you tune chunk size or swap embedders.

### Pattern: Confidence = ensemble of signals
Never rely on a single confidence source. Combine logprobs + self-consistency + critic agreement.

### Pattern: Trace everything, score later
Every LLM call goes through the Langfuse handler. Attach eval scores post-hoc via trace_id — don't block the request path on eval.

---

## 10. Anti-Patterns to Avoid

### Anti-pattern: One giant Qdrant collection with all vectors
**Why bad:** Text chunks and page images have different cardinalities, dimensionalities, and update cadences. Mixing them forces awkward payload filters and wastes index memory.
**Instead:** Two collections, fused at application layer.

### Anti-pattern: Indexing ColQwen2 full multivectors with HNSW
**Why bad:** Tens of MB per page, huge RAM cost, slow queries, with no quality gain over the two-stage pattern.
**Instead:** Always use `hnsw_config=HnswConfigDiff(m=0)` on the `original` vector and rely on mean-pooled HNSW prefetches.

### Anti-pattern: Letting Phase 2 rewrite Phase 1 code
**Why bad:** You lose the baseline for benchmarking. The "Phase 1 vs Phase 2" delta becomes subjective.
**Instead:** Phase 2 adds new `*_v2` implementations behind the same Protocol. Both are live; config selects which runs.

### Anti-pattern: VLM confidence = LLM "self-reported confidence" only
**Why bad:** Models are miscalibrated — will say "95% confident" on wrong answers.
**Instead:** Ensemble logprobs + self-consistency + critic agreement. Calibrate against gold set.

### Anti-pattern: Unbounded LangGraph loops
**Why bad:** Evaluate → retrieve → evaluate can cycle forever on adversarial queries.
**Instead:** Hard retry limits in state (`retry_count < N`); abstain on exhaustion.

### Anti-pattern: Streamlit makes its own LLM calls outside the LangGraph
**Why bad:** Those calls bypass the Langfuse trace tree and break session grouping.
**Instead:** All LLM traffic goes through the RAG Orchestrator, which owns the callback handler.

### Anti-pattern: Embedding the Docling pipeline inside a Streamlit callback
**Why bad:** Docling + Granite VLM on a folder of PDFs can take minutes; Streamlit's rerun model will time out or redo work.
**Instead:** Ingestion is an offline CLI (`python -m pipeline.ingest <folder>`); Streamlit only reads the resulting stores.

---

## 11. Scalability Considerations (Demo → Production Sketch)

| Concern | Demo (~100 docs) | 10K docs | 1M docs |
|---------|------------------|----------|---------|
| Doc store | Local parquet + PNGs | Object storage (S3/GCS) | S3 + CDN for page images |
| Qdrant | Qdrant Cloud Free / local Docker | Qdrant Cloud (single node, 8–16 GB) | Sharded Qdrant cluster + MUVERA compression |
| Embedding | Synchronous in Colab | Celery/RQ batch workers with GPU | Ray/Modal autoscaling GPU pool |
| VLM extraction | Per-PDF sync API call | Batched API + rate-limit budget | Self-host Granite-Docling for tier pricing |
| Compliance DB | SQLite | Postgres | Postgres + read replicas |
| Streamlit | Single process | Multi-instance behind load balancer | FastAPI backend + decoupled UI |
| Langfuse | Cloud free tier | Cloud team tier | Self-host Langfuse OSS |

---

## 12. Suggested Build Order (Dependency-Driven)

The architecture implies a strict partial ordering. Build in this order; later phases wrap earlier ones without modifying them.

**Foundation (week 1 equivalents):**
1. Doc Store + Ingestion Pipeline (Docling + page image renderer) — unblocks everything.
2. Compliance DB schema + SQLite bootstrap.
3. Streamlit skeleton (3 empty pages + navigation).

**Phase 1 baseline (weeks 2–3):**
4. Single-pass `FieldExtractor` + compliance rule engine (populates Dashboard).
5. `sdf_text_chunks` collection + `HybridTextRetriever` (BM25 + dense + CE rerank).
6. `LinearRAG` Answerer (retrieve → generate) — Chatbot page wired up.
7. Gold set (~50 pages) + eval harness v1 (extraction F1, recall@5, faithfulness, latency, cost).
8. Langfuse wired to all LLM calls.

**Phase 2 upgrade (weeks 4–5):**
9. `sdf_page_images` collection + ColQwen2 embedder + mean-pool projections.
10. `HybridTextVisualRetriever` (fuses text + visual candidates).
11. `CriticLoopExtractor` + confidence ensemble + HITL queue.
12. `AgenticRAG` (LangGraph with decompose/retrieve/evaluate/draft/critique/regen).

**Phase 3 comparison (week 6):**
13. Eval harness v2: run both pipelines on the same gold set, write to `eval_runs`.
14. Eval dashboard page in Streamlit (Phase 1 vs Phase 2 numbers side by side).
15. Architecture diagrams, recorded walkthrough, design doc.

### Dependencies to respect
- Critic loop depends on Extractor (Phase 2 wraps Phase 1 component).
- Agentic RAG depends on HybridTextVisualRetriever (needs multimodal candidates).
- Eval dashboard depends on both pipelines being invocable via config switch.
- Langfuse integration touches every LLM call — wire it in during Phase 1 (step 8), not Phase 2.

---

## Sources

High-confidence (Context7-equivalent official docs):
- [Qdrant Multivector Document Retrieval with ColPali/ColQwen](https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/)
- [Optimizing ColPali for Retrieval at Scale, 13x Faster Results](https://qdrant.tech/blog/colpali-qdrant-optimization/)
- [Hybrid Search Revamped - Qdrant Query API](https://qdrant.tech/articles/hybrid-search/)
- [Multivectors and Late Interaction - Qdrant](https://qdrant.tech/documentation/tutorials-search-engineering/using-multivector-representations/)
- [Langfuse LangGraph Integration Cookbook](https://langfuse.com/guides/cookbook/integration_langgraph)
- [Langfuse LangChain Callback Handler](https://langfuse.com/integrations/frameworks/langchain)
- [Build a custom RAG agent with LangGraph](https://docs.langchain.com/oss/python/langgraph/agentic-rag)
- [Self-Reflective RAG with LangGraph (blog)](https://blog.langchain.com/agentic-rag-with-langgraph/)
- [Docling DoclingDocument reference](https://docling-project.github.io/docling/concepts/docling_document/)
- [Docling pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/)

Medium-confidence (community/blog + official concepts):
- [Next-Generation Agentic RAG with LangGraph (2026)](https://medium.com/@vinodkrane/next-generation-agentic-rag-with-langgraph-2026-edition-d1c4c068d2b8)
- [Building Agentic RAG Systems with LangGraph: The 2026 Guide](https://rahulkolekar.com/building-agentic-rag-systems-with-langgraph/)
- [Late Interaction Retrieval Models: ColBERT, ColPali, ColQwen (Weaviate)](https://weaviate.io/blog/late-interaction-overview)
- [Unlocking LLM Confidence Through Logprobs](https://gautam75.medium.com/unlocking-llm-confidence-through-logprobs-54b26ed1b48a)
- [Confidence Improves Self-Consistency in LLMs (arXiv)](https://arxiv.org/html/2502.06233v1)
- [Critic-V: VLM Critics Help Catch VLM Errors (CVPR 2025)](https://openaccess.thecvf.com/content/CVPR2025/papers/Zhang_Critic-V_VLM_Critics_Help_Catch_VLM_Errors_in_Multimodal_Reasoning_CVPR_2025_paper.pdf)
- [Streamlit Multipage Apps](https://docs.streamlit.io/develop/concepts/multipage-apps)
- [Streamlit Client-Server Architecture](https://docs.streamlit.io/develop/concepts/architecture/architecture)
- [Revolutionizing Document Intelligence: Granite-Docling VLM](https://medium.com/@mustafa.gencc94/revolutionizing-document-intelligence-the-strategic-advantage-of-ibm-granite-docling-vlm-71f8bf1357e4)

### Confidence summary

| Area | Level | Reason |
|------|-------|--------|
| Qdrant collection design | HIGH | Verbatim from Qdrant official tutorials |
| ColQwen2 two-stage retrieval | HIGH | Qdrant blog + tutorial explicitly document NDCG/Recall numbers and HNSW=0 pattern |
| LangGraph state machine shape | HIGH | Matches official `docs.langchain.com` pattern + multiple 2026 implementations |
| Langfuse integration | HIGH | Verbatim from Langfuse official cookbook |
| Docling `DoclingDocument` / Pydantic / bbox | HIGH | Official docs confirm bbox + Pydantic schema + confidence surfacing |
| Confidence ensemble formula | MEDIUM | No single canonical formula; weights are starting point to calibrate on gold set |
| Phase 1/2 abstraction (Protocol-based) | MEDIUM | Generic software engineering; not pharma-specific, but directly enables requirement |
