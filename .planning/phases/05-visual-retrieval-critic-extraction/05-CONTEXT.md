# Phase 5: Visual Retrieval & Critic Extraction - Context

**Gathered:** 2026-06-23
**Status:** Ready for planning
**Source:** Direct user decisions (interactive session, not discuss-phase)

<domain>
## Phase Boundary

**This planning pass covers the VISUAL RETRIEVAL TIER ONLY — Phase 5 success criteria 1–2 (requirements `VISUAL-01`, `VISUAL-02`).**

Deliver a real, evaluated ColQwen2.5-v0.2 page-image retrieval tier:
- Rasterize every corpus page to an image and embed it with ColQwen2.5 (ColBERT-style multivector output).
- Index the embeddings in a versioned Qdrant `sdf_page_images` collection using named vectors (full multivector with HNSW disabled + mean-pooled vector(s) with HNSW enabled).
- Retrieve with the canonical two-stage strategy: mean-pooled HNSW prefetch → full multivector MaxSim rerank.
- Fuse the visual candidates with the existing SQLite-FTS5 text tier into the unified retrieval result the RAG/eval path already consumes.
- Run the real retrieval eval (recall@5/@10, ndcg@5, citation accuracy) on the gold set and report honest numbers — including the four `rq_ex3_*` queries whose gold pages are scanned image-only.

**Explicitly OUT OF SCOPE for this phase** (deferred — see Deferred Ideas): the critic/reflection extraction loop (`EXTRACT-03`), the per-field confidence ensemble + HITL routing (`EXTRACT-04`). Phase 5 success criteria 3–4 are NOT planned here.

**Why this slice:** The user asked specifically to "complete the ColQwen2.5 visual retrieval." Bundling the critic-extraction half would balloon scope. Visual retrieval is also the direct fix for the diagnosed Example 3 failure (image-only gold pages unreachable by text retrieval).
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### Compute topology — where the real numbers come from
- **The real ColQwen2.5 index-build + retrieval eval run on Google Colab Pro L4, full precision (bf16), delivered as a committed, reproducible notebook in the repo.** This is the canonical CLAUDE.md path ("Colab Pro acceptable," "L4 recommended default"). The numbers reported in any SUMMARY come from that run.
- **Do NOT plan local GPU indexing.** The user's local GPU is an 8 GB RTX 5070 Laptop (Blackwell, sm_120): below ColQwen2.5's ~16 GB floor for indexing the 3B model, and a torch-CUDA wheel-compat hazard (CLAUDE.md pins `torch<2.6`, which predates stable Blackwell support). The local machine runs the text tier + dashboard only.
- **Demo runtime is deferred** ("get real numbers first, wire the demo later"). Do not plan Streamlit wiring of the visual tier in this phase. A local query path on the 5070 (single short-query encoding, possibly 4-bit) is a *later* decision, not this phase.

### No fabrication — the metric integrity rule (HARD REQUIREMENT)
- **No mocks/stubs/synthetic similarity scores anywhere in the metric path.** Every reported retrieval-quality number must come from a real ColQwen2.5 run on a real GPU, reproducible by anyone via the committed Colab notebook.
- **Offline unit tests may ONLY cover deterministic, non-GPU plumbing:** PDF→image rasterization at ~150 DPI, Qdrant collection config (named vectors, HNSW on/off, MaxSim comparator), Qdrant query/prefetch payload construction, RRF/fusion math, and eval-metric computation (recall/ndcg/citation accuracy formulas). A test must NEVER inject a fake embedding or fake score that stands in for the model and then assert a quality metric off it.
- This mirrors the project's existing lazy-import seams (RAGAS/Langfuse) ONLY in the sense of "heavy dep loaded when present" — it does NOT mean mocking the model to fabricate results. The retrieval logic itself is real code; the GPU-bound execution simply runs where a GPU exists (Colab).

### Motivating defect this must fix (Example 3)
- Doc `5543408c4dacc48b`, gold target **page 2 (internal 0-indexed)** is the Cytiva "Certificate of Quality" (mfg `20210126` / expiry `20230126`). It is scanned **image-only**: `pages.page_text` length 0, `pages.image_blob` ~271 KB present.
- The text indexer at `src/retrieval/indexer.py:192` (`AND TRIM(COALESCE(p.page_text,'')) <> ''`) deliberately excludes empty-text pages, so doc `5543408c` indexes only pages `[3,4,5,6,8,9,10]` — pages 0,1,2,7 (all scanned) are absent. Text recall@5 is therefore structurally 0 on all four `rq_ex3_*` queries.
- **The visual tier must make these image-only pages retrievable.** Success is demonstrated by the `rq_ex3_*` gold pages appearing in top-k via visual retrieval.
- **Also fix the gold-data defect:** the four `rq_ex3_*` gold query texts contain mojibake — "ÄKTA" rendered as U+FFFD (`�KTA`). Repair the gold query text (does not by itself lift recall, but the gold set is corrupted).

### Stack (LOCKED per CLAUDE.md)
- `colpali-engine>=0.3.11,<0.4`; model `vidore/colqwen2.5-v0.2` (Qwen2.5-VL-3B backbone, dynamic resolution up to 768 patches, ColBERT multivector).
- `transformers>=4.45,<4.50`; `torch>=2.3,<2.6` (bf16 on L4); `qdrant-client>=1.17,<2.0`.
- `pypdfium2` for rasterization (cross-platform, no poppler) at 144–200 DPI (target ~150).
- Qdrant: **embedded local mode** on Colab via `QdrantClient(path=...)` for the build (no Docker in Colab). Named vectors `{"pooled": <mean-pooled 128-d, HNSW on>, "multivector": <N×128 original, HNSW off, MaxSim comparator>}`. Query with `prefetch`: pooled HNSW top-N → rerank with multivector MaxSim → top-k.
- The `pages` table already stores per-page images (`image_blob`); source PDFs live in gitignored `local_data/private/`. Rasterize from source PDFs at the chosen DPI for index quality (the stored `image_blob` may be a lower-res thumbnail — verify during research).

### Integration boundary with existing system
- The visual tier must produce candidates that fuse into the SAME unified retrieval result type the RAG service + eval harness already consume (see `src/retrieval/models.py` `RetrievalHit`, `src/retrieval/retriever.py`, `src/eval/`). Fusion combines visual + text candidates (RRF or score-normalized union — decide in research).
- Respect the existing privacy/trace boundaries: page-image bytes and full page text must NOT enter Langfuse trace allowlists or persisted eval rows (consistent with the `quick-260611-ou3` evidence_text contract).
- Pipeline config flag: the system is meant to support a Phase-1-vs-Phase-2 benchmark (ROADMAP Phase 7). Visual retrieval should be selectable via config so text-only and visual-fused modes can both be evaluated on the same gold set.

### Verification (Windows hard rule)
- All offline verification via `venv\Scripts\python.exe -m pytest ...` only — never bash/`/bin/bash`.
- `compliance.db` and `.env` are NEVER staged. GPU-dependent tests are skipped/guarded offline and exercised only in the Colab notebook run.

### Claude's Discretion (implementation details to settle in research/planning)
- Exact fusion algorithm (RRF k-constant vs normalized-score union) and how visual/text scores are reconciled.
- Mean-pooling scheme: single mean-pooled vector vs the roadmap's "mean-pooled rows + columns" two-vector variant (Qdrant ColPali optimization). Research the current Qdrant-recommended pattern and pick the one that matches `colqwen2.5-v0.2` output.
- Rasterization DPI within 144–200 and image preprocessing for ColQwen.
- Batch sizes / memory strategy for the Colab L4 index build.
- How the Colab notebook persists the built index back for downstream use (Drive mount vs exported artifact) given the demo is deferred.
- Collection versioning scheme for `sdf_page_images` (mirror the existing `retrieval_index_runs` versioning).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked stack + project rules
- `CLAUDE.md` — Technology Stack tables (Visual Retrieval, Vector Database, Version Pinning, Colab Compatibility), Windows verification rule, GSD workflow enforcement.
- `.planning/research/STACK.md` — prior stack research.
- `.planning/research/ARCHITECTURE.md` — intended pipeline data flow.
- `.planning/research/PITFALLS.md` — known landmines.

### Existing retrieval/eval code to integrate with (verify against real code, NOT the stale roadmap)
- `src/retrieval/models.py` — `RetrievalHit` / `RetrievalScoreComponents` DTOs the visual tier must produce.
- `src/retrieval/retriever.py` — current text retrieval + scoring + trace allowlist (`_RETRIEVAL_TRACE_ALLOWED_KEYS`); the fusion seam.
- `src/retrieval/indexer.py` — text index build (line 192 empty-text exclusion that strands image-only pages); mirror its versioning (`retrieval_index_runs`).
- `src/retrieval/repository.py` — index persistence/query repository pattern.
- `src/eval/` (esp. `src/eval/cli.py`, retrieval metric computation, `src/eval/ragas_quality.py`) — where recall@5/ndcg/citation-accuracy are computed and where visual-mode numbers must flow.
- `src/db/schema.py` — `pages` table (`page_text`, `image_blob`), `documents`, retrieval index tables.
- `.planning/quick/260611-ou3-widen-rag-evidence-from-truncated-index-/260611-ou3-SUMMARY.md` — the privacy/trace-allowlist contract and evidence boundary to preserve.

### Gold set + the Example 3 defect
- `gold_retrieval_queries` / `gold_retrieval_targets` tables in `compliance.db` (the `rq_ex3_*` queries with the ÄKTA mojibake; targets pointing at image-only pages).
- `docs/field-definitions.md` — shared field rulebook (if present).
</canonical_refs>

<specifics>
## Specific Ideas

- Two-stage Qdrant retrieval is the canonical ColPali/ColQwen pattern Qdrant documents (mean-pooled HNSW prefetch → multivector MaxSim rerank; ~13× speedup, NDCG retained). Follow the Qdrant "Optimizing ColPali" guidance for `colqwen2.5-v0.2`.
- The committed Colab notebook is itself a phase deliverable and the reproducibility artifact: it installs the pinned stack, downloads `vidore/colqwen2.5-v0.2`, rasterizes + embeds the corpus, builds the Qdrant collection, runs the retrieval eval, and prints the metrics table. Anyone with Colab Pro L4 can re-run it and get the same numbers.
- The single most important proof point: the four `rq_ex3_*` gold pages (image-only) must show up in visual top-k where text retrieval scored 0 — turning recall@5 above the current 0.647 text ceiling.
</specifics>

<deferred>
## Deferred Ideas

**Moved to a future phase (NOT planned here):**
- `EXTRACT-03` — extraction critic/reflection loop (critic re-reads source page image, challenges claims, reconciliation capped at 2 iterations). Phase 5 success criterion 3.
- `EXTRACT-04` — per-field confidence ensemble (`0.4 logprob + 0.4 self-consistency(k=3) + 0.2 critic_agreement`) with sub-0.75 fields routed to the HITL queue. Phase 5 success criterion 4.

These remain valid Phase 5 roadmap requirements; they are split out so the visual-retrieval tier can land, be evaluated, and deliver real numbers first. They should become their own phase (e.g., an inserted "Critic Extraction & Confidence" phase) after this tier is verified.

**Also deferred (other phases / later decisions):**
- Demo runtime wiring (Streamlit visual-tier integration; local 5070 query path / Colab API bridge).
- LangGraph agentic RAG, HITL dashboard tab, full Langfuse phase tagging (Phase 6).
- Phase-1-vs-Phase-2 side-by-side benchmark dashboard (Phase 7) — but keep the visual tier config-selectable so that benchmark is possible later.
</deferred>

---

*Phase: 05-visual-retrieval-critic-extraction*
*Context gathered: 2026-06-23 via direct user decisions*
