# Phase 5: Visual Retrieval Tier (VISUAL-01, VISUAL-02) - Research

**Researched:** 2026-06-23
**Domain:** ColQwen2.5 page-image multivector retrieval, Qdrant late-interaction indexing, two-stage retrieval, Colab L4 reproducible eval, fusion with existing SQLite-FTS5 text tier
**Confidence:** HIGH (colpali-engine API + Qdrant ColPali config verified against official sources; integration verified against real repo code; version-coupling and Blackwell risks flagged)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Compute topology — where the real numbers come from**
- The real ColQwen2.5 index-build + retrieval eval run on **Google Colab Pro L4, full precision (bf16)**, delivered as a committed, reproducible notebook in the repo. Reported numbers come from that run.
- **Do NOT plan local GPU indexing.** Local GPU is 8 GB RTX 5070 Laptop (Blackwell, sm_120): below ColQwen2.5's ~16 GB indexing floor and a torch-CUDA wheel-compat hazard (`torch<2.6` predates stable Blackwell support). Local machine runs the text tier + dashboard only.
- **Demo runtime is deferred.** No Streamlit wiring of the visual tier this phase. A local query path on the 5070 is a later decision.

**No fabrication — metric integrity rule (HARD)**
- No mocks/stubs/synthetic similarity scores anywhere in the metric path. Every reported retrieval-quality number comes from a real ColQwen2.5 run on a real GPU, reproducible via the committed Colab notebook.
- Offline unit tests may ONLY cover deterministic, non-GPU plumbing: PDF→image rasterization at ~150 DPI, Qdrant collection config, query/prefetch payload construction, RRF/fusion math, eval-metric computation. A test must NEVER inject a fake embedding/score that stands in for the model and then assert a quality metric off it.
- This mirrors existing lazy-import seams (RAGAS/Langfuse) ONLY as "heavy dep loaded when present" — NOT mocking the model to fabricate results.

**Motivating defect this must fix (Example 3)**
- Doc `5543408c4dacc48b`, gold page **2 (0-indexed)** = Cytiva "Certificate of Quality" (mfg `20210126` / expiry `20230126`), scanned **image-only**: `page_text` len 0, `image_blob` ~271 KB present.
- Text indexer `src/retrieval/indexer.py:192` (`AND TRIM(COALESCE(p.page_text,'')) <> ''`) excludes empty-text pages → doc indexes only `[3,4,5,6,8,9,10]`; pages 0,1,2,7 absent. Text recall@5 structurally 0 on all four `rq_ex3_*` queries.
- The visual tier must make image-only pages retrievable. Success = `rq_ex3_*` gold pages in visual top-k.
- **Gold-data fix:** all four `rq_ex3_*` query texts contain mojibake — "ÄKTA" rendered as U+FFFD (`�KTA`). Repair the gold query text.

**Stack (LOCKED per CLAUDE.md)**
- `colpali-engine>=0.3.11,<0.4`; model `vidore/colqwen2.5-v0.2` (Qwen2.5-VL-3B, dynamic resolution ≤768 patches, ColBERT multivector).
- `transformers>=4.45,<4.50`; `torch>=2.3,<2.6` (bf16 on L4); `qdrant-client>=1.17,<2.0`.
- `pypdfium2` rasterization at 144–200 DPI (target ~150).
- Qdrant embedded local mode on Colab via `QdrantClient(path=...)`. Named vectors: full multivector (HNSW off, MAX_SIM) + mean-pooled (HNSW on). Query with prefetch: pooled HNSW top-N → multivector MAX_SIM rerank → top-k.
- `pages.image_blob` already stores per-page images; source PDFs in gitignored `local_data/private/`. Verify whether to rasterize from source PDFs vs use stored blob.

**Integration boundary**
- Visual tier must produce candidates that fuse into the SAME unified result type the RAG service + eval harness consume (`RetrievalHit`, `retrieve_evidence`, `src/eval/`). Fusion = RRF or score-normalized union (decide in research).
- Respect privacy/trace boundaries: page-image bytes and full page text must NOT enter Langfuse allowlists or persisted eval rows (mirror `quick-260611-ou3` evidence_text contract).
- Pipeline config flag: visual retrieval selectable so text-only and visual-fused modes both evaluate on the same gold set (Phase 7 benchmark).

**Verification (Windows hard rule)**
- All offline verification via `venv\Scripts\python.exe -m pytest ...` only — never bash/`/bin/bash`.
- `compliance.db` and `.env` NEVER staged. GPU-dependent tests skipped/guarded offline; exercised only in the Colab notebook run.

### Claude's Discretion
- Exact fusion algorithm (RRF k-constant vs normalized-score union).
- Mean-pooling scheme: single mean-pooled vector vs "mean-pooled rows + columns" two-vector variant. Pick the one matching `colqwen2.5-v0.2` output.
- Rasterization DPI within 144–200 and image preprocessing for ColQwen.
- Batch sizes / memory strategy for Colab L4 build.
- How the Colab notebook persists the built index for downstream use (Drive vs exported artifact).
- Collection versioning scheme for `sdf_page_images` (mirror `retrieval_index_runs`).

### Deferred Ideas (OUT OF SCOPE)
- `EXTRACT-03` — critic/reflection extraction loop (Phase 5 success criterion 3).
- `EXTRACT-04` — per-field confidence ensemble + HITL routing (Phase 5 success criterion 4).
- Demo runtime wiring (Streamlit visual tier; local 5070 query path / Colab API bridge).
- LangGraph agentic RAG, HITL tab, full Langfuse phase tagging (Phase 6).
- Phase-1-vs-Phase-2 benchmark dashboard (Phase 7) — but keep visual tier config-selectable so it stays possible.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VISUAL-01 | Index each page image with ColQwen2.5-v0.2 embeddings (three named Qdrant vectors: full multivector HNSW-disabled, mean-pooled rows, mean-pooled columns) in a versioned `sdf_page_images` collection | `ColQwen2_5`/`ColQwen2_5_Processor` API verified [CITED: huggingface.co/vidore/colqwen2.5-v0.2]; exact three-named-vector Qdrant config verified [CITED: qdrant.tech pdf-retrieval-at-scale]; `image_blob` is the reproducible 150-DPI source [VERIFIED: rasterizer.py + DB blob lengths]; versioning mirrors `retrieval_index_runs` [VERIFIED: schema.py + repository.py] |
| VISUAL-02 | Two-stage ColQwen2 strategy: mean-pooled HNSW prefetch → full multivector MaxSim rerank — fused with Phase 1 text retrieval candidates | `query_points` prefetch-on-pooled / rerank-on-original syntax verified [CITED: qdrant.tech]; fusion seam is `retrieve_evidence()` producing `RetrievalHit` keyed on `(doc_id, page_num)` [VERIFIED: retriever.py, retrieval_eval_runner.py:153-155, retrieval_metrics.py] |
</phase_requirements>

---

## Summary

This phase adds a real ColQwen2.5-v0.2 visual retrieval tier that makes **scanned image-only pages retrievable** — directly fixing the Example 3 defect where the text indexer skips empty-text pages (gold page `5543408c4dacc48b:2` is never indexed, so text recall@5 is structurally 0 on all four `rq_ex3_*` queries). The retrieval-quality numbers come exclusively from a committed, reproducible **Colab Pro L4 notebook** running the pinned stack in bf16; the local 8 GB RTX 5070 (Blackwell sm_120) is too small and a torch-wheel hazard, so it never indexes.

The architecture is the **canonical Qdrant ColPali optimization**: a `sdf_page_images` collection with three named multivectors per page — `original` (full ~768-patch multivector, HNSW disabled via `m=0`, MAX_SIM), `mean_pooling_rows`, and `mean_pooling_columns` (small pooled multivectors with HNSW). Retrieval prefetches the two pooled vectors via HNSW, then reranks candidates with full-multivector MAX_SIM. Visual candidates fuse with the existing SQLite-FTS5 text tier into the **same `RetrievalHit` DTO** that `retrieve_evidence()` returns, so the existing recall@5 / ndcg / citation-accuracy eval and RAG service work unchanged — they only ever compare `(doc_id, page_num)` page identities.

The metric-integrity rule splits the work cleanly: **rasterization, Qdrant collection config, query/prefetch payload construction, the row/column mean-pool reshape math, RRF fusion math, and eval-metric formulas are all deterministic and unit-testable offline without a GPU.** Only the actual embedding forward pass and the resulting quality numbers require the GPU, and those run only in the notebook. No test may inject a fake embedding/score and assert a quality metric off it.

**Primary recommendation:** Build a provider-free `src/retrieval/visual/` module (embedder seam, Qdrant collection builder, two-stage querier, RRF fusion into `RetrievalHit`) whose pure logic is fully offline-tested; drive the GPU build + eval from a committed `notebooks/visual_retrieval_colab.ipynb`; rasterize from the **stored `image_blob`** (the reproducible 150-DPI PNG) rather than the Downloads-only source PDFs; use **RRF with k=60** for fusion; use the **rows+columns pooled-multivector** scheme exactly as Qdrant documents for `colqwen2.5-v0.2`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Page rasterization (PDF/blob → PIL image) | Ingestion / data prep (pure CPU) | — | Already exists in `rasterizer.py`; deterministic, no GPU |
| ColQwen2.5 embedding (image & query → multivector) | GPU compute (Colab L4) | — | 3B VLM; ~16 GB VRAM floor; the only GPU-bound step |
| Mean-pool rows/columns from patch grid | CPU tensor reshape (pure) | GPU (lives next to embed) | Deterministic given embeddings; offline-testable on synthetic tensors |
| `sdf_page_images` collection config + upsert | Vector DB (Qdrant local mode) | — | Schema/config is pure dict construction; testable offline |
| Two-stage prefetch+rerank query | Vector DB (Qdrant) | — | Payload construction testable offline; execution needs a populated collection |
| Fusion (visual + text → `RetrievalHit`) | Retrieval orchestration (pure Python) | — | RRF math is deterministic; testable offline |
| Recall@k / ndcg / citation-accuracy | Eval harness (pure Python) | — | Already exists; consumes `(doc_id, page_num)` only |
| Index persistence / versioning | SQLite (`*_index_runs` pattern) | Qdrant storage artifact | Mirror `retrieval_index_runs`; offline-testable |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| colpali-engine | `>=0.3.11,<0.4` (latest 0.3.17, Jun 8 2026 [VERIFIED: pypi.org/pypi/colpali-engine/json]) | ColQwen2.5 model + processor wrapper | Official illuin-tech library; provides `ColQwen2_5`, `ColQwen2_5_Processor`, `score_multi_vector`, `get_n_patches`, `get_image_mask` [CITED: huggingface.co/vidore/colqwen2.5-v0.2; Context7 /illuin-tech/colpali] |
| transformers | `>=4.45,<4.50` (CLAUDE.md pin) | Model backbone for ColQwen2.5 | Floor for ColQwen2.5; model card states `transformers>4.45.0` [CITED: HF model card]. **See version-coupling pitfall** — colpali-engine 0.3.17 may want newer transformers |
| torch | `>=2.3,<2.6` (bf16 on L4) | GPU inference | Matches Colab L4 CUDA. **Do NOT install on local 5070 (Blackwell sm_120)** |
| qdrant-client | `>=1.17,<2.0` (latest 1.18.0 [VERIFIED: pypi.org/pypi/qdrant-client/json]) | Multivector collection + Query API prefetch | Native multivector, MAX_SIM comparator, two-stage `query_points(prefetch=...)` |
| pypdfium2 | latest (5.7.1 local) | Page rasterization | Already used by `src/pipeline/rasterizer.py` at 150 DPI; cross-platform, no poppler |
| Pillow | latest | PIL images for `process_images` | ColQwen processor consumes `PIL.Image` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | latest | Pooled-vector reshape / RRF math | Offline-testable pooling + fusion |
| flash-attn | optional | `attn_implementation="flash_attention_2"` | Optional speedup on L4; guard with `is_flash_attn_2_available()` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Three named vectors (original + rows + cols) | Single mean-pooled vector + original | Qdrant's documented `colqwen2.5` pattern uses **rows + columns** pooled multivectors; single-vector pooling loses spatial recall. Roadmap (VISUAL-01) explicitly mandates rows + columns. **Use rows+columns.** |
| RRF fusion | Score-normalized union | RRF is rank-based, robust to incomparable score scales (BM25/lexical vs MAX_SIM cosine). Score-union requires per-tier normalization that is brittle. **Use RRF (k=60).** |
| Rasterize from stored `image_blob` | Re-rasterize from source PDF | Source PDFs live in `C:\Users\smati\Downloads\SDFs\` (gitignored, NOT reproducible on Colab). The stored `image_blob` IS the 150-DPI PNG (`rasterizer.py` `DPI_TARGET=150`). **Rasterize from `image_blob` for reproducibility.** |
| `HierarchicalTokenPooler` compression | Full multivector | Pooler reduces vectors at small accuracy cost; not needed for a ~dozens-of-PDFs corpus. Skip for the demo corpus. |

**Installation (Colab notebook cell, pinned):**
```bash
pip install "colpali-engine>=0.3.11,<0.4" "transformers>=4.45,<4.50" \
            "qdrant-client>=1.17,<2.0" pypdfium2 pillow
# torch is preinstalled on Colab L4 (CUDA 12.x); verify torch>=2.3,<2.6 and bf16 support
```

**Version verification performed this session:**
- colpali-engine: latest `0.3.17` (2026-06-08) — within pin. [VERIFIED: PyPI]
- qdrant-client: latest `1.18.0` — within pin. [VERIFIED: PyPI]
- Model classes `ColQwen2_5` / `ColQwen2_5_Processor`, `colpali-engine>0.3.1` (0.3.7 trained), `transformers>4.45.0`. [CITED: HF model card]
- Per-token dim: ColBERT-style **128** (Qdrant config uses `size=128`; HF card does not restate it). [VERIFIED: Qdrant config; ASSUMED for ColQwen2.5 exact value — confirm by printing `image_embeddings.shape[-1]` in the notebook]

---

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────── COLAB PRO L4 (GPU, bf16) ───────────────────┐
                    │                                                                 │
 compliance.db ────►│  pages.image_blob (150-DPI PNG)                                 │
 (image_blob)       │        │                                                        │
                    │        ▼  io.BytesIO → PIL.Image                                 │
                    │  processor.process_images(batch)  ──► model(**batch)            │
                    │        │                                  │                      │
                    │        │                          image_embeddings              │
                    │        │                          [N, seq, 128]                 │
                    │        ▼                                  │                      │
                    │  get_n_patches + get_image_mask           ▼                      │
                    │        │                          mean-pool rows / cols          │
                    │        ▼                                  │                      │
                    │  Qdrant upsert: named vectors {original, rows, cols}             │
                    │        │  (collection sdf_page_images_v{N}, local mode path=...) │
                    └────────┼────────────────────────────────────────────────────────┘
                             │  persist storage artifact (Drive / zip) ──► repo/release
                             ▼
        ┌──────────────── RETRIEVAL (Colab eval; later: local query) ─────────────────┐
        │ query text ─► process_queries ─► query_embedding [q, 128]                    │
        │                          │                                                   │
        │    Qdrant query_points(prefetch=[cols HNSW, rows HNSW], using="original")    │
        │                          │  top-N pooled prefetch → MAX_SIM rerank → top-k   │
        │                          ▼                                                   │
        │            visual hits  (doc_id, page_num, max_sim_score)                    │
        │                          │                                                   │
        │   text tier: retrieve_evidence()/HybridTextRetriever ─► text hits            │
        │                          │                                                   │
        │              RRF FUSION (k=60) over (doc_id, page_num)                       │
        │                          ▼                                                   │
        │              unified tuple[RetrievalHit, ...]  (page-level identity)         │
        │                          │                                                   │
        │   eval: compute_retrieval_recall_at_k / citation_accuracy (UNCHANGED)        │
        └──────────────────────────────────────────────────────────────────────────────┘
```

Key data-flow facts (traced from the real code):
- `retrieval_eval_runner.run_retrieval_eval` calls `retrieve_evidence(db_path, query_text, top_k=max_k)` then reads `[(hit.doc_id, int(hit.page_num)) ...]` (line 153-155). Metrics compare ONLY page identities. So the visual/fused path must expose hits with the same `(doc_id, page_num)` semantics.
- `page_num` is **0-indexed** throughout (DB + metrics + gold targets). `display_page_num` is 1-indexed for citations only. Visual hits must carry the 0-indexed `page_num`.

### Recommended Project Structure

```
src/retrieval/
├── models.py                 # ADD: visual score component / fusion source tags (extend RetrievalScoreComponents.source)
├── retriever.py              # text tier (unchanged core) + fusion entry seam
├── indexer.py                # text indexer (line 192 stays; visual is a separate tier, NOT a relaxation of this)
├── repository.py             # SQLite index-run persistence (mirror for visual run metadata)
└── visual/                   # NEW — provider-free where possible
    ├── __init__.py
    ├── embedder.py           # GPU seam: load ColQwen2_5, embed images/queries (import-guarded)
    ├── pooling.py            # PURE: mean-pool rows/cols from patch grid (offline-testable)
    ├── collection.py         # PURE: Qdrant collection config + upsert/query payload builders
    ├── querier.py            # two-stage query orchestration (payload pure; execution needs Qdrant)
    ├── fusion.py             # PURE: RRF fuse visual + text hits → RetrievalHit (offline-testable)
    └── run.py                # build/version a sdf_page_images run; mirrors retrieval_index_runs

notebooks/
└── visual_retrieval_colab.ipynb   # PHASE DELIVERABLE: pinned install → embed → index → eval → metrics table
```

### Pattern 1: ColQwen2.5 load + embed (GPU seam)
**What:** Load the model/processor, embed page images and text queries.
**When to use:** Only inside the GPU seam (`embedder.py`), import-guarded so the module is offline-safe.
```python
# Source: huggingface.co/vidore/colqwen2.5-v0.2 ; Context7 /illuin-tech/colpali
import torch
from PIL import Image
from colpali_engine.models import ColQwen2_5, ColQwen2_5_Processor

model = ColQwen2_5.from_pretrained(
    "vidore/colqwen2.5-v0.2",
    torch_dtype=torch.bfloat16,
    device_map="cuda:0",
).eval()
processor = ColQwen2_5_Processor.from_pretrained("vidore/colqwen2.5-v0.2")

batch_images = processor.process_images(images).to(model.device)   # images: list[PIL.Image]
batch_queries = processor.process_queries(queries).to(model.device)
with torch.no_grad():
    image_embeddings = model(**batch_images)   # [B, seq, 128]
    query_embeddings = model(**batch_queries)  # [B, q_seq, 128]
# Offline scoring sanity check (NOT used in Qdrant path):
# scores = processor.score_multi_vector(query_embeddings, image_embeddings)
```

### Pattern 2: Patch-grid extraction + row/column mean pooling
**What:** Reduce the full multivector to two small pooled multivectors using the patch grid.
**When to use:** Right after embedding, before Qdrant upsert. The reshape is deterministic — test it offline on synthetic tensors of known shape.
```python
# Source: qdrant.tech pdf-retrieval-at-scale (adapted to ColQwen2.5 processor API)
# Robust grid via the processor rather than scanning for image_token_id:
n_patches_x, n_patches_y = processor.get_n_patches(image_size=image.size, patch_size=model.patch_size)
image_mask = processor.get_image_mask(batch_images)           # [B, seq] bool over image tokens
emb = image_embeddings[i]                                     # [seq, 128]
mask = image_mask[i]                                          # [seq]
patches = emb[mask].view(n_patches_x, n_patches_y, model.dim) # [x, y, 128]
pooled_rows = patches.mean(dim=0)                             # [y, 128]
pooled_cols = patches.mean(dim=1)                             # [x, 128]
# Keep non-image (special/query-augmentation) tokens, per Qdrant pattern:
pooled_rows = torch.cat([pooled_rows, emb[~mask]])
pooled_cols = torch.cat([pooled_cols, emb[~mask]])
```
> NOTE: `model.dim` and `model.patch_size` attribute names should be confirmed at notebook runtime (`print(model.dim, model.patch_size)`). The Qdrant blog used `model.dim`; if absent on ColQwen2.5, derive dim from `emb.shape[-1]`. [ASSUMED: attribute names; VERIFY in notebook]

### Pattern 3: `sdf_page_images` collection config (three named vectors)
```python
# Source: qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/
from qdrant_client import models
client.create_collection(
    collection_name="sdf_page_images_v1",
    vectors_config={
        "original": models.VectorParams(
            size=128, distance=models.Distance.COSINE,
            multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM),
            hnsw_config=models.HnswConfigDiff(m=0),   # CRITICAL: disable HNSW on the full multivector
        ),
        "mean_pooling_columns": models.VectorParams(
            size=128, distance=models.Distance.COSINE,
            multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM),
        ),
        "mean_pooling_rows": models.VectorParams(
            size=128, distance=models.Distance.COSINE,
            multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM),
        ),
    },
)
```

### Pattern 4: Two-stage prefetch + MAX_SIM rerank
```python
# Source: qdrant.tech pdf-retrieval-at-scale
response = client.query_points(
    collection_name="sdf_page_images_v1",
    query=query_embedding,                 # full query multivector [q, 128]
    prefetch=[
        models.Prefetch(query=query_embedding, limit=prefetch_limit, using="mean_pooling_columns"),
        models.Prefetch(query=query_embedding, limit=prefetch_limit, using="mean_pooling_rows"),
    ],
    limit=search_limit,
    with_payload=True, with_vector=False,
    using="original",                      # rerank stage uses full multivector MAX_SIM
)
# payload must carry {"doc_id": ..., "page_num": <0-indexed int>} for fusion/eval identity
```

### Pattern 5: RRF fusion into `RetrievalHit`
**What:** Combine ranked visual hits and ranked text hits by Reciprocal Rank Fusion.
```python
# RRF: score(page) = Σ_tiers 1 / (k + rank_in_tier), k=60 (standard)
def rrf_fuse(visual_ranked, text_ranked, *, k: int = 60):
    scores: dict[tuple[str, int], float] = {}
    for ranked in (visual_ranked, text_ranked):
        for rank, (doc_id, page_num) in enumerate(ranked):   # rank 0-based
            scores[(doc_id, page_num)] = scores.get((doc_id, page_num), 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])
```
Fused output is mapped to `RetrievalHit` with `page_num` (0-indexed), `display_page_num` (page_num+1), `score` = RRF score, `score_components.source = "fused" | "visual" | "fts"`, and `snippet`/`evidence_text` drawn from the text tier when present, empty for image-only pages (consistent with the existing `_bounded_evidence_text` fallback behavior).

### Anti-Patterns to Avoid
- **HNSW on the full multivector:** indexing ~768 patch-vectors/page into HNSW explodes RAM/insert time. Set `hnsw_config=HnswConfigDiff(m=0)` on `original` (Pitfall C1). HNSW lives only on the pooled vectors.
- **Relaxing `indexer.py:192` to "fix" Example 3:** the text indexer SHOULD keep excluding empty-text pages — visual retrieval is the correct fix, a separate tier. Do not weaken the text path.
- **Re-rasterizing from `Downloads/SDFs/...`:** not reproducible on Colab. Use `image_blob`.
- **Mocking embeddings to assert a recall number:** forbidden by the metric-integrity rule.
- **Mixing 0-indexed/1-indexed page numbers:** gold targets and metrics use 0-indexed `page_num`. Visual payload must store 0-indexed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Late-interaction MAX_SIM scoring | Custom token-similarity loop | `MultiVectorComparator.MAX_SIM` + `query_points` rerank | Qdrant does this natively and fast; custom is slow and wrong-edge-cased |
| Two-stage ANN | Manual top-N then manual rerank loop | `query_points(prefetch=[...], using="original")` | Single API call; Qdrant handles candidate merge across the two pooled prefetches |
| Patch-grid dimensions | Guess x/y from seq length | `processor.get_n_patches(...)` + `processor.get_image_mask(...)` | ColQwen2.5 uses dynamic resolution; grid varies per image |
| Query augmentation tokens | Manually pad query | `processor.process_queries(...)` | Adds augmentation tokens automatically |
| Rank fusion | Ad-hoc score addition across BM25 + cosine | RRF (k=60) | Score scales are incomparable; rank-based fusion is robust |
| Index versioning | New scheme | Mirror `retrieval_index_runs` + `_deterministic_run_id` | Existing, tested pattern (`repository.py`, `indexer.py`) |

**Key insight:** ColQwen2.5's dynamic resolution means per-image patch grids differ; never assume a fixed patch count. Always derive the grid from the processor, and let Qdrant own MAX_SIM and the two-stage merge.

---

## Runtime State Inventory

> This phase adds a vector index (new runtime state). Not a rename/refactor, but the new Qdrant artifact and gold-data repair warrant explicit tracking.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `pages.image_blob` for all corpus pages (e.g., doc `5543408c`: 11 pages, all blobs present incl. image-only pages 0,1,2,7) [VERIFIED: DB query] | Read-only source for embedding; no migration |
| Stored data (gold defect) | 4 `rq_ex3_*` gold query texts contain U+FFFD mojibake (`�KTA` should be `ÄKTA`) [VERIFIED: DB query] | **Data fix:** UPDATE `gold_retrieval_queries.query_text` for the 4 rows; provide an idempotent repair script + verify no other gold rows affected |
| Live service config | Qdrant `sdf_page_images_v1` collection built in Colab local mode (`path=...`) | Persist storage artifact (Drive mount or zipped export) for downstream/local reuse; demo deferred |
| OS-registered state | None | None — Colab is ephemeral; no OS registration |
| Secrets/env vars | None new. Existing `HF_HOME` (config.py) caches model weights; `GEMINI_API_KEY` not needed for retrieval | None — retrieval tier is provider-free |
| Build artifacts | Local venv has `transformers 5.6.2` / `torch 2.12.0+cu130` [VERIFIED], far beyond pins — confirms local is NOT the index environment | None; do NOT downgrade local. Colab installs the pinned stack in-notebook |

**The canonical question — what runtime state persists the build?** The Qdrant collection storage directory (Colab local mode). It must be exported (Drive/zip) because the Colab runtime is ephemeral and the demo is deferred. Source PDFs in `Downloads/SDFs/` are NOT a reproducible source — `image_blob` is.

---

## Common Pitfalls

### Pitfall 1: HNSW built over full multivector (Qdrant OOM / slow inserts)
**What goes wrong:** ~768 patch vectors/page indexed into HNSW; RAM explodes, inserts crawl.
**Why:** Default `m=16` builds a graph over every token vector.
**How to avoid:** `hnsw_config=HnswConfigDiff(m=0)` on `original`; HNSW only on pooled vectors.
**Warning signs:** `indexed_vectors_count` in the hundreds of thousands; Colab OOM on upsert. (Matches PITFALLS.md C1.) [CITED: qdrant.tech]

### Pitfall 2: Blackwell (sm_120) torch-wheel incompatibility on local 5070
**What goes wrong:** `torch<2.6` predates stable Blackwell support; `torch.cuda` errors or no kernels for sm_120 on the 8 GB 5070.
**Why:** CLAUDE.md pins `torch>=2.3,<2.6`; that range lacks sm_120 kernels. (Local venv already has torch 2.12+cu130 — incompatible with the pinned indexing stack.)
**How to avoid:** Do NOT index locally. All embedding runs on Colab L4. Guard GPU imports so the local machine never loads colpali/torch-pinned code. [VERIFIED: local venv versions; CONTEXT.md locked]

### Pitfall 3: T4 vs L4 VRAM (OOM during embedding)
**What goes wrong:** ColQwen2.5-3B OOMs on T4 (15 GB) with default batch.
**Why:** Default examples target L4/A100 (16+ GB).
**How to avoid:** Require L4 (22.5 GB) per CLAUDE.md "recommended default"; start `batch_size=2`, bf16, `torch.cuda.empty_cache()` + `gc.collect()` between batches; cap image resolution (≤768 patches). For a ~dozens-of-PDFs corpus this is comfortable on L4. (Matches PITFALLS.md M7.) [CITED: colpali-engine docs]

### Pitfall 4: colpali-engine ↔ transformers version coupling
**What goes wrong:** colpali-engine 0.3.17 (Jun 2026) may require transformers newer than the `<4.50` ceiling; init paths (`config.hidden_size` vs `config.text_config.hidden_size`) have regressed historically.
**Why:** ColQwen2.5 init is sensitive to transformers internals.
**How to avoid:** Pin a known-good pair and verify in the notebook with a smoke embed of ONE image before the full build. If 0.3.17 conflicts with `transformers<4.50`, pin a 0.3.x that the model card era used (model trained on 0.3.7) and document the exact pair that loaded. Print `colpali_engine.__version__`, `transformers.__version__` at notebook top. [ASSUMED: exact conflict; VERIFY in notebook] (Related: PITFALLS.md m4.)

### Pitfall 5: Qdrant local-mode multivector caveats
**What goes wrong:** Local (embedded) mode disallows concurrent process access to the storage path; some server-only features may differ.
**Why:** Embedded mode is single-process.
**How to avoid:** Single-notebook build/eval is fine. Don't open two cells against the same path concurrently. Multivector + MAX_SIM + prefetch ARE supported in client `>=1.17`. (Matches PITFALLS.md m1.) [CITED: qdrant.tech]

### Pitfall 6: Image-only-page identity and 0/1-indexing
**What goes wrong:** Visual hits stored with 1-indexed page or a different doc_id key → recall@k silently 0 despite correct retrieval.
**Why:** Gold targets and metrics key on 0-indexed `(doc_id, page_num)`.
**How to avoid:** Qdrant payload stores 0-indexed `page_num` and the exact `doc_id`. Add an offline test asserting payload identity round-trips. [VERIFIED: retrieval_metrics.py, gold targets use page_num=2 0-indexed]

### Pitfall 7: Privacy leak of image bytes / full page text into traces or eval rows
**What goes wrong:** Adding visual metadata to Langfuse or `eval_metrics` could leak image bytes or page text.
**Why:** New tier, new metadata temptation.
**How to avoid:** Mirror the existing allowlists — `_RETRIEVAL_TRACE_ALLOWED_KEYS`, `_EVALUATION_TRACE_ALLOWED_KEYS`, `_INDEX_TRACE_ALLOWED_KEYS` — and the `quick-260611-ou3` evidence_text contract: only counts/scores/run_ids/reason codes in traces; never image_blob, never full page text. Visual run metadata persists counts + run_id only. [VERIFIED: retriever.py, retrieval_eval_runner.py, models.py docstrings]

### Pitfall 8: Colab session death mid-build
**What goes wrong:** Long index build lost on disconnect.
**How to avoid:** Deterministic point IDs (hash of doc_id+page_num) for idempotent re-upsert; persist Qdrant storage to Drive; checkpoint manifest. For ~dozens of PDFs the build is short, but make it resumable. (Matches PITFALLS.md C6.) [CITED: Colab FAQ]

---

## Code Examples

### Rasterize a stored blob → PIL image (offline, deterministic)
```python
# Source: existing src/pipeline/rasterizer.py uses pypdfium2 at 150 DPI;
# the stored image_blob IS that 150-DPI PNG, so just decode it.
import io
from PIL import Image
def blob_to_image(image_blob: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_blob)).convert("RGB")
```

### Offline-testable collection-config builder (no Qdrant needed to assert shape)
```python
def build_vectors_config():
    from qdrant_client import models
    base = dict(size=128, distance=models.Distance.COSINE)
    msim = models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM)
    return {
        "original": models.VectorParams(**base, multivector_config=msim,
                                        hnsw_config=models.HnswConfigDiff(m=0)),
        "mean_pooling_columns": models.VectorParams(**base, multivector_config=msim),
        "mean_pooling_rows": models.VectorParams(**base, multivector_config=msim),
    }
# Test: assert config["original"].hnsw_config.m == 0; assert all comparators are MAX_SIM.
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single mean-pooled vector + rerank | Mean-pool **rows + columns** (two pooled multivectors) + original rerank | Qdrant ColPali optimization (2024-2025) | ~13x faster first stage, NDCG retained; matches VISUAL-01 |
| `ColQwen2` / colqwen2-v1.0 | `ColQwen2_5` / `colqwen2.5-v0.2` (Qwen2.5-VL-3B) | colpali-engine ≥0.3.1 | Higher ViDoRe accuracy; different processor class names |
| Index full multivector into HNSW | HNSW only on pooled; `m=0` on full | Qdrant multivector guidance | Avoids RAM blowup |

**Deprecated/outdated:**
- Naive multivector HNSW indexing: replaced by pooled-prefetch + full rerank.
- `ColQwen2Processor` class names do NOT apply to v0.2 — use `ColQwen2_5_Processor`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Per-token embedding dim is 128 for colqwen2.5-v0.2 | Standard Stack / Patterns | If different, `size=128` in collection config wrong → upsert fails. **Mitigation:** print `image_embeddings.shape[-1]` first cell |
| A2 | `model.dim` and `model.patch_size` attributes exist on ColQwen2.5 | Pattern 2 | Pooling reshape breaks. **Mitigation:** derive dim from `emb.shape[-1]`; use `get_n_patches` for grid |
| A3 | colpali-engine 0.3.17 loads under `transformers<4.50` | Pitfall 4 | Build fails on Colab. **Mitigation:** notebook smoke-load before full build; pin known-good pair |
| A4 | Stored `image_blob` is full-res 150-DPI (not a downscaled thumbnail) | Stack / Pitfall | If thumbnail, retrieval quality drops. **Mitigation:** `rasterizer.py` shows DPI_TARGET=150 and saves PNG un-optimized; blob lengths (200-800 KB) are consistent with full pages, not thumbnails [VERIFIED via DB]. Low risk |
| A5 | bf16 on L4 reproduces stable scores run-to-run | Validation | Minor score jitter. **Mitigation:** `torch.no_grad()`, eval mode, fixed batch order; report exact env in notebook |

**If A1–A3 fail, they fail loudly at notebook build time (not silently), so the metric-integrity rule is preserved.**

---

## Open Questions

1. **colpali-engine 0.3.17 vs transformers<4.50 compatibility**
   - What we know: model card cites `transformers>4.45.0`; 0.3.17 is recent (Jun 2026).
   - What's unclear: whether 0.3.17 needs transformers ≥4.50.
   - Recommendation: notebook prints both versions and smoke-embeds one image before the full build; if conflict, pin the exact loadable pair and document it.

2. **Persistence of the Colab-built Qdrant index**
   - What we know: Colab is ephemeral; demo deferred.
   - What's unclear: Drive mount vs zipped artifact committed to a release.
   - Recommendation: zip the Qdrant storage dir + a small manifest (collection name, run_id, point count, model version) and attach as a build artifact; document the local-restore path for the future demo phase.

3. **Does ColQwen2.5 require image resizing before `process_images`?**
   - What we know: processor handles dynamic resolution up to 768 patches.
   - What's unclear: whether 150-DPI full pages exceed the patch cap and get auto-downsampled.
   - Recommendation: let the processor handle resizing; if VRAM pressure appears, cap longest side (~1456 px) before `process_images`. Confirm patch count via `get_n_patches`.

---

## Environment Availability

| Dependency | Required By | Available (local) | Available (Colab L4) | Fallback |
|------------|------------|-------------------|----------------------|----------|
| GPU ≥16 GB VRAM (bf16) | ColQwen2.5 embedding | ✗ (5070 8 GB, sm_120) | ✓ (L4 22.5 GB) | None — Colab is the only path (locked) |
| colpali-engine 0.3.x | embedding | ✗ (not installed) | install in notebook | None |
| qdrant-client ≥1.17 | indexing/query | ✗ (not installed) | install in notebook | None |
| pypdfium2 | rasterization | ✓ (5.7.1) | install in notebook | None |
| torch ≥2.3,<2.6 | GPU inference | ✗ (local has 2.12, incompatible by design) | preinstalled/install | None |
| pytest (offline plumbing) | offline tests | ✓ (`venv\Scripts\python.exe -m pytest`) | n/a | None |

**Missing dependencies with no fallback:** GPU + pinned ML stack — by design these exist only on Colab L4. The offline plan never needs them; GPU tests are guarded/skipped locally.

**Missing dependencies with fallback:** None — the split is intentional (offline plumbing vs GPU build).

---

## Validation Architecture

> nyquist_validation is enabled (config.json `workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (Windows: `venv\Scripts\python.exe -m pytest`) |
| Config file | `pyproject.toml` (existing test config) |
| Quick run command | `venv\Scripts\python.exe -m pytest tests/retrieval/visual -x -q` |
| Full suite command | `venv\Scripts\python.exe -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command (offline) | File Exists? |
|--------|----------|-----------|------------------------------|-------------|
| VISUAL-01 | Collection config has 3 named vectors; `original` HNSW disabled (m=0); all MAX_SIM; size=128 | unit (pure) | `pytest tests/retrieval/visual/test_collection.py -x` | ❌ Wave 0 |
| VISUAL-01 | Row/column mean-pool reshape produces correct shapes from a synthetic patch grid | unit (pure, no GPU) | `pytest tests/retrieval/visual/test_pooling.py -x` | ❌ Wave 0 |
| VISUAL-01 | `image_blob` decodes to a PIL RGB image (deterministic) | unit (pure) | `pytest tests/retrieval/visual/test_blob_decode.py -x` | ❌ Wave 0 |
| VISUAL-01 | Upsert payload carries 0-indexed `page_num` + `doc_id`; deterministic point IDs | unit (pure) | `pytest tests/retrieval/visual/test_payload.py -x` | ❌ Wave 0 |
| VISUAL-01 | Visual run versioning mirrors `retrieval_index_runs` (deterministic run_id) | unit | `pytest tests/retrieval/visual/test_run_versioning.py -x` | ❌ Wave 0 |
| VISUAL-02 | `query_points` prefetch payload: 2 pooled prefetches + `using="original"` | unit (pure) | `pytest tests/retrieval/visual/test_query_payload.py -x` | ❌ Wave 0 |
| VISUAL-02 | RRF fusion math: known ranked lists → known fused order; page-identity keys | unit (pure) | `pytest tests/retrieval/visual/test_fusion.py -x` | ❌ Wave 0 |
| VISUAL-02 | Fused hits map to `RetrievalHit` with correct 0/1-index + source tag; feed unchanged eval metrics | unit | `pytest tests/retrieval/visual/test_fused_hits.py -x` | ❌ Wave 0 |
| VISUAL-02 | Config flag selects text-only vs visual-fused mode (selectable pipeline) | unit | `pytest tests/retrieval/visual/test_mode_select.py -x` | ❌ Wave 0 |
| Gold fix | `rq_ex3_*` mojibake repaired; `ÄKTA` present, no U+FFFD; other gold rows untouched | unit | `pytest tests/eval/test_gold_mojibake_repair.py -x` | ❌ Wave 0 |
| Privacy | Visual trace/eval metadata allowlists exclude image bytes + full page text | unit | `pytest tests/retrieval/visual/test_privacy_allowlist.py -x` | ❌ Wave 0 |
| VISUAL-01/02 quality | Real recall@5/@10, ndcg, citation accuracy incl. `rq_ex3_*` lift | **GPU-only, Colab notebook** | (not offline; notebook prints metrics table) | Notebook deliverable |

### Sampling Rate
- **Per task commit:** `venv\Scripts\python.exe -m pytest tests/retrieval/visual -x -q`
- **Per wave merge:** `venv\Scripts\python.exe -m pytest -q` (full offline suite)
- **Phase gate:** Full offline suite green AND the committed Colab notebook produces a real metrics table showing `rq_ex3_*` gold pages in visual/fused top-k (recall lift above the 0.647 text ceiling).

### GPU-only boundary (metric-integrity rule)
- **Offline (unit-testable, no GPU, no mocks-of-model):** rasterization/blob decode, collection config, pooling reshape, upsert/query payloads, RRF fusion, hit mapping, eval-metric formulas (already tested), gold repair, privacy allowlists, run versioning.
- **GPU-only (Colab notebook, real model, NO offline assertion of quality):** embedding forward pass, actual Qdrant retrieval over real embeddings, the recall/ndcg/citation numbers.
- A test must NEVER fabricate an embedding/score and assert a quality metric. Offline tests assert *plumbing correctness* on synthetic-but-honestly-labeled tensors (shape/identity), never retrieval *quality*.

### Wave 0 Gaps
- [ ] `tests/retrieval/visual/` package + `conftest.py` (synthetic-tensor + fake-Qdrant-payload fixtures; GPU-marked skips)
- [ ] `test_collection.py`, `test_pooling.py`, `test_blob_decode.py`, `test_payload.py`, `test_query_payload.py`, `test_fusion.py`, `test_fused_hits.py`, `test_mode_select.py`, `test_run_versioning.py`, `test_privacy_allowlist.py`
- [ ] `tests/eval/test_gold_mojibake_repair.py`
- [ ] GPU marker (`@pytest.mark.gpu`) + skip-unless-CUDA guard so embedder tests never run offline
- [ ] `notebooks/visual_retrieval_colab.ipynb` (the reproducible GPU deliverable)

---

## Sources

### Primary (HIGH confidence)
- Context7 `/illuin-tech/colpali` — ColQwen2 load/process/score, `get_n_patches`, `get_image_mask`, token pooling APIs
- huggingface.co/vidore/colqwen2.5-v0.2 — `ColQwen2_5`/`ColQwen2_5_Processor` class names, version floors, usage snippet
- qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/ — exact 3-named-vector collection config, row/column pooling reshape, two-stage `query_points` prefetch
- qdrant.tech/blog/colpali-qdrant-optimization/ — pooling rationale (1030→pooled), 13x speedup
- PyPI `colpali-engine` (0.3.17, 2026-06-08) and `qdrant-client` (1.18.0) — version currency
- Real repo code: `src/retrieval/{models,retriever,indexer,repository}.py`, `src/eval/{retrieval_eval_runner,retrieval_metrics,cli}.py`, `src/pipeline/rasterizer.py`, `src/db/schema.py`, `src/rag/service.py`, `compliance.db` (gold queries, image-only pages, file paths)

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` — C1 (HNSW on multivector), C2 (versioned collections), C6 (Colab session death), M7 (T4 OOM), m1 (local-mode concurrency), m4 (Colab dep conflicts)

### Tertiary (LOW confidence)
- WebSearch summary of Qdrant pooling (corroborates the verified config; not solely relied upon)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — class names/versions verified against HF card + PyPI; coupling risk flagged.
- Architecture (Qdrant config + two-stage query): HIGH — exact code quoted from Qdrant official tutorial.
- Pooling reshape: MEDIUM-HIGH — Qdrant pattern verified; ColQwen2.5 attribute names to confirm at runtime (A2).
- Integration/fusion seam: HIGH — verified against real `retrieve_evidence`/eval code and `(doc_id, page_num)` identity.
- Pitfalls: HIGH — cross-referenced PITFALLS.md + Qdrant docs + verified local env (Blackwell/version mismatch).

**Research date:** 2026-06-23
**Valid until:** 2026-07-23 (stable libraries; re-verify colpali-engine/transformers pairing if either bumps)
