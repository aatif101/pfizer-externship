---
phase: 05-visual-retrieval-critic-extraction
plan: 04
subsystem: retrieval
tags: [visual-retrieval, colqwen2.5, gpu-seam, colab-notebook, offline-structural-test, no-fabrication]
requires:
  - "src/retrieval/visual/{collection,pooling,querier,fusion,run}.py (Plans 01-02 pure builders)"
  - "src/retrieval/retriever.py retrieve_evidence (text-tier ranked hits for fusion)"
  - "src/eval/retrieval_metrics.py compute_retrieval_recall_at_k / compute_page_level_citation_accuracy (unchanged)"
  - "compliance.db pages.image_blob (reproducible 150-DPI PNG embedding source) — uploaded to Colab, never committed"
provides:
  - "src/retrieval/visual/embedder.py: lazy-import GPU seam (load_colqwen, embed_images, embed_queries, pooled_vectors_for_image) — Task 1, committed 28664e3"
  - "notebooks/visual_retrieval_colab.ipynb: reproducible Colab L4 deliverable (install -> embed -> index -> two-stage retrieve -> text-only vs visual-fused eval -> metrics table -> rq_ex3 proof -> artifact export)"
  - "tests/retrieval/visual/test_notebook_structure.py: offline structural validation (nbformat envelope, pins, shared-builder tokens, rq_ex3 proof, secret-absence) — asserts NO quality number"
affects:
  - "notebooks/ (new directory)"
  - "tests/retrieval/visual/ (new structural + embedder-offline tests)"
tech-stack:
  added: []
  patterns:
    - "Lazy-import GPU seam: torch/colpali_engine imported INSIDE function bodies so embedder.py imports offline; load_colqwen raises ImportError without the deps (mirrors src.eval.ragas_quality)"
    - "Notebook reuses the SAME pure src.retrieval.visual builders the offline suite tests — only the GPU forward pass + printed numbers are notebook-exclusive (no plumbing re-implementation)"
    - "Embed pages FROM pages.image_blob (reproducible 150-DPI PNG via pooling.blob_to_image), NEVER from gitignored source PDFs"
    - "Metric-integrity / no-fabrication boundary: offline structural test validates AUTHORING only (it never executes the notebook and asserts NO recall/ndcg/citation number); real VISUAL-01/VISUAL-02 numbers come only from the manual Colab L4 run"
    - "Structural test parses the .ipynb via stdlib json so it runs offline WITHOUT nbformat (no skip); uses nbformat.validate opportunistically when installed"
key-files:
  created:
    - src/retrieval/visual/embedder.py
    - tests/retrieval/visual/test_embedder_offline.py
    - notebooks/visual_retrieval_colab.ipynb
    - tests/retrieval/visual/test_notebook_structure.py
  modified: []
decisions:
  - "GPU work is a lazy-import seam (offline-importable; ImportError on call without the pinned stack) so the local Blackwell-incompatible box never loads torch<2.6 / colpali at import (threat T-05-18)"
  - "The notebook imports the shared pure builders (collection/pooling/querier/fusion/run + embedder) rather than re-implementing plumbing, so what runs on Colab is what the offline suite tests"
  - "Embed from pages.image_blob (reproducible) not the gitignored source PDFs — anyone with the .db + Colab L4 reproduces the same build"
  - "Offline structural test uses stdlib json (not a hard nbformat dependency) so it executes in CI without adding a test dep; nbformat.validate runs only if present"
  - "Task 3 (the real Colab L4 run that produces the numbers) is a human-verify checkpoint — NOT executed here; no GPU/quality number is fabricated"
metrics:
  duration: ~18 min
  completed: 2026-06-23
---

# Phase 5 Plan 04: GPU Embedder Seam + Colab L4 Visual-Retrieval Notebook Summary

Authored the no-fabrication GPU boundary for the ColQwen2.5 visual tier: a lazy-import embedder seam (`embedder.py`, Task 1, already committed at `28664e3`) and the committed Colab L4 notebook (`notebooks/visual_retrieval_colab.ipynb`, Task 2) that is the phase reproducibility deliverable — install the pinned stack, load `vidore/colqwen2.5-v0.2`, embed every corpus page **from `pages.image_blob`**, build the three-named-vector `sdf_page_images` Qdrant collection, run two-stage retrieval, evaluate **text-only vs visual-fused** on the gold set, print the metrics table, and prove the four `rq_ex3_*` image-only gold pages appear in visual top-k. The notebook imports the SAME pure builders the offline suite covers, so only the GPU forward pass and the printed numbers are notebook-exclusive. The real VISUAL-01/VISUAL-02 quality numbers are produced ONLY by the manual Colab L4 run (Task 3, a human-verify checkpoint) and are recorded into this SUMMARY after that run — none are fabricated here.

## What Was Built

### Task 1 — GPU embedder lazy-import seam (already committed at `28664e3`)
- **`src/retrieval/visual/embedder.py`** — offline-safe module: `torch` / `colpali_engine` imported INSIDE function bodies, mirroring `src.eval.ragas_quality`. `load_colqwen(model_id="vidore/colqwen2.5-v0.2", dtype="bfloat16", device="cuda:0")` returns `(model, processor)` from the REAL checkpoint; `embed_images` / `embed_queries` run the `torch.no_grad()` forward pass; `pooled_vectors_for_image` derives the per-image dynamic grid via `processor.get_n_patches` + `processor.get_image_mask` and delegates the reshape to the Plan-02 pure `pooling.mean_pool_rows_cols` (dim derived from `emb.shape[-1]`, RESEARCH A2). Never mocks/fabricates an embedding.
- **`tests/retrieval/visual/test_embedder_offline.py`** — asserts the module imports with no torch/colpali installed, that heavy imports are indented (lazy), that `load_colqwen()` raises `ImportError` when the deps are absent, and carries a `@pytest.mark.gpu` smoke test (skipped offline). Asserts NO quality metric.

### Task 2 — Colab L4 notebook + offline structural test (committed `3226fc0`)
- **`notebooks/visual_retrieval_colab.ipynb`** — valid nbformat v4, 9-section pipeline:
  1. Title + purpose (real VISUAL-01/VISUAL-02 numbers; Colab L4, bf16; no secrets needed).
  2. Pinned install cell — `colpali-engine>=0.3.11,<0.4`, `transformers>=4.45,<4.50`, `qdrant-client>=1.17,<2.0`, `pypdfium2`, `pillow`.
  3. Repo clone so `src.retrieval.visual.*` is importable (shared builders, not re-impl).
  4. **Version print + smoke embed** — prints `colpali_engine.__version__`, `transformers.__version__`, `torch.__version__`; loads the model via `embedder.load_colqwen`; embeds ONE image; asserts per-token dim `== 128` (RESEARCH A1) and inspects `model.patch_size` / `spatial_merge_size` (A2) BEFORE the full build (Pitfall 4 / Open Q A3).
  5. Upload `compliance.db`; read every page via parameterized-shape SQL `SELECT ... FROM pages JOIN documents`; decode each via `pooling.blob_to_image` (FROM `image_blob`, not source PDFs).
  6. Build `sdf_page_images_v1` via `collection.build_vectors_config()` (original HNSW-off + rows/cols); embed in bf16 `batch_size=2` with `empty_cache()+gc.collect()` between batches (Pitfall 3); pooled vectors via `embedder.pooled_vectors_for_image`; upsert via `collection.build_upsert_point` (0-indexed `page_num` payload); persist the run via `run.build_visual_index_run`.
  7. Two-stage retrieval over the gold queries via `querier.build_query_payload` + `map_response_to_candidates`.
  8. **Text-only vs visual-fused eval** on the SAME gold set with the UNCHANGED `compute_retrieval_recall_at_k` / `compute_page_level_citation_accuracy`; visual-fused = `fusion.rrf_fuse(visual, text, k=60)`; prints the metrics table.
  9. **Example-3 proof cell** — for each `rq_ex3_*` query prints text/visual/fused HIT/miss for each gold page (incl. doc `5543408c4dacc48b` page 2, 0-indexed).
  10. Artifact export — zips `/content/qdrant_storage` + a manifest (collection, run_id, point count, version triple) for the deferred demo. No API keys / secrets anywhere.
- **`tests/retrieval/visual/test_notebook_structure.py`** — 9 offline tests: nbformat-v4 envelope (stdlib json; `nbformat.validate` opportunistically), pins present, locked model + `load_colqwen`, shared-builder tokens (`build_vectors_config`, `build_query_payload`, `rrf_fuse`, `collection_name`, `blob_to_image`, `build_visual_index_run`, `pooled_vectors_for_image`), embed-from-`image_blob` (and `Downloads` absent), `rq_ex3` + doc-id proof, both-mode eval, and secret-absence (`sk-`, `AIza`, `_SECRET_KEY=`). Never executes the notebook; asserts NO quality number.

## Verification

- `venv\Scripts\python.exe -m pytest tests/retrieval/visual/test_notebook_structure.py -x -q` -> **9 passed** (runs offline without nbformat — no skip).
- `venv\Scripts\python.exe -m pytest tests/retrieval/visual -q` -> **48 passed, 8 skipped** (the 8 skips are `@pytest.mark.gpu` model-execution tests).
- `venv\Scripts\python.exe -m pytest -q` (full offline suite) -> **382 passed, 8 skipped** — suite stays green.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Structural test must run offline without an nbformat install**
- **Found during:** Task 2 verification.
- **Issue:** The first draft used `pytest.importorskip("nbformat")`; nbformat is not installed in the venv, so all 9 structural tests SKIPPED — defeating the offline authoring guard (the test would never actually validate the notebook in CI).
- **Fix:** Rewrote the test to parse the `.ipynb` via stdlib `json` (a notebook is a JSON document) and validate the nbformat-v4 envelope + required cell keys directly; `nbformat.validate` now runs only opportunistically when the package is present. The structural guard executes offline with zero new test dependencies.
- **Files modified:** `tests/retrieval/visual/test_notebook_structure.py`.
- **Commit:** `3226fc0`.

## Known Stubs

None. The notebook is a complete, runnable deliverable; the only "pending" element is the human Colab L4 execution (Task 3), which is the intended no-fabrication boundary — not a stub. No hardcoded empty/mock data flows to any metric.

## Checkpoint Pending — Task 3 (Manual-Only Colab L4 run)

Task 3 is a `checkpoint:human-verify` (autonomous: false) and was NOT executed here — running it offline or inventing its numbers would violate the metric-integrity rule. The user runs `notebooks/visual_retrieval_colab.ipynb` on Colab Pro **L4** and records, into this SUMMARY:

- The printed **metrics table** (text-only vs visual-fused recall@5/@10, citation accuracy).
- The **Example-3 proof** outcome (the four `rq_ex3_*` gold pages HIT in visual/fused top-k where text missed).
- The exact loadable **`(colpali-engine, transformers, torch)` version triple** the notebook printed.

### Real Colab L4 numbers (to be filled in after the run)

| Metric | text-only | visual-fused | delta |
|--------|-----------|--------------|-------|
| recall@5  | _pending Colab L4 run_ | _pending_ | _pending_ |
| recall@10 | _pending Colab L4 run_ | _pending_ | _pending_ |
| citation_acc@5  | _pending_ | _pending_ | _pending_ |
| citation_acc@10 | _pending_ | _pending_ | _pending_ |

**rq_ex3 proof:** _pending Colab L4 run_ (expect text miss -> visual/fused HIT for doc `5543408c4dacc48b` page 2 + the other rq_ex3 targets).

**Loadable version triple:** colpali-engine `_pending_`, transformers `_pending_`, torch `_pending_`.

## Self-Check: PASSED

- Files: `src/retrieval/visual/embedder.py`, `tests/retrieval/visual/test_embedder_offline.py`, `notebooks/visual_retrieval_colab.ipynb`, `tests/retrieval/visual/test_notebook_structure.py`, `.planning/phases/05-visual-retrieval-critic-extraction/05-04-SUMMARY.md` — all FOUND.
- Commits: `28664e3` (Task 1 embedder seam), `3226fc0` (Task 2 notebook + structural test) — both FOUND.
- Autonomous tasks (1-2) complete and committed; Task 3 is a pending human-verify Colab L4 checkpoint (no numbers fabricated).
