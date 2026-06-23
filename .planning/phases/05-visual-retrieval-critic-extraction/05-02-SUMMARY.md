---
phase: 05-visual-retrieval-critic-extraction
plan: 02
subsystem: retrieval
tags: [visual-retrieval, two-stage-query, rrf-fusion, run-versioning, offline-plumbing, tdd]
requires:
  - "src/retrieval/visual package (Plan 01: collection_name, VisualIndexRun, deterministic_visual_run_id, visual_index_runs schema)"
  - "src/retrieval/models.py RetrievalHit / RetrievalScoreComponents (0-indexed page_num)"
provides:
  - "build_query_payload — pure two-stage query kwargs (2 pooled Prefetch + using='original')"
  - "map_response_to_candidates — Qdrant points → 0-indexed VisualCandidate identity mapping"
  - "rrf_fuse — pure RRF(k=60) over (doc_id,page_num) ranked lists, deterministic order"
  - "to_retrieval_hits — fused pages → canonical RetrievalHit (source visual|fused, empty evidence for image-only)"
  - "plan_visual_run / build_visual_index_run — deterministic visual-built-{hash} run over ALL pages incl. image-only"
  - "save_visual_index_run / get_latest_visual_index_run_id — idempotent visual_index_runs persistence"
affects:
  - "src/retrieval/visual/ (4 new modules; no changes to existing files)"
tech-stack:
  added: []
  patterns:
    - "Pure-builder split: query payload + RRF + run plan are deterministic/offline; GPU embed + live Qdrant execution deferred to the notebook"
    - "Lazy qdrant_client import inside build_query_payload keeps querier offline-importable"
    - "Fusion emits the SAME RetrievalHit eval/RAG consume unchanged (page-identity keyed on 0-indexed (doc_id,page_num))"
    - "Image-only pages survive RRF and carry empty snippet/evidence_text (ou3 empty-page contract — no fabricated grounding)"
    - "Versioned run mirrors retrieval_index_runs INSERT ON CONFLICT idempotency; identifiers/counts only, never raw content"
key-files:
  created:
    - src/retrieval/visual/querier.py
    - src/retrieval/visual/fusion.py
    - src/retrieval/visual/run.py
    - src/retrieval/visual/repository.py
    - tests/retrieval/visual/test_query_payload.py
    - tests/retrieval/visual/test_fusion.py
    - tests/retrieval/visual/test_fused_hits.py
    - tests/retrieval/visual/test_run_versioning.py
  modified: []
decisions:
  - "RRF stable tie-break on (doc_id,page_num) ascending makes fused order fully deterministic (T-05-09)"
  - "Offline tests assert RRF MATH + DTO mapping + payload shape + run versioning ONLY — never a model-derived recall/ndcg number (metric-integrity rule)"
  - "Visual run hashes identifiers only (no page text, no image bytes); visual tier indexes ALL pages incl. image-only — does NOT reuse the text indexer empty-text exclusion"
metrics:
  duration: ~8 min
  completed: 2026-06-23
---

# Phase 5 Plan 02: Visual Retrieval Query, Fusion & Run Versioning Summary

The offline-testable retrieval logic for the visual tier: the pure two-stage Qdrant query-payload builder (two mean-pooled `Prefetch` entries reranked with `using="original"` full-multivector MAX_SIM), the RRF (k=60) fusion that maps visual + text candidates into the existing `RetrievalHit` DTO keyed on 0-indexed `(doc_id, page_num)`, and the versioned `visual_index_runs` persistence mirroring `retrieval_index_runs`. All pure/deterministic — the GPU forward pass and live Qdrant execution stay deferred to the Colab notebook (Plan 04). Because fusion emits the same `RetrievalHit` the eval harness already consumes, the recall@5 / ndcg / citation-accuracy metric code needs ZERO change.

## What Was Built

- **`src/retrieval/visual/querier.py`** — `build_query_payload(query_embedding, *, prefetch_limit=200, search_limit=20, version=1)` returns the canonical two-stage `query_points` kwargs: `prefetch=[Prefetch(using="mean_pooling_columns"), Prefetch(using="mean_pooling_rows")]` (each `limit=prefetch_limit`), reranked top-level with `using="original"`, `limit=search_limit`, `with_payload=True`, `with_vector=False`, against `collection_name(version)`. `qdrant_client` is lazy-imported inside the function (offline-safe). `map_response_to_candidates(points)` maps Qdrant points → frozen `VisualCandidate(doc_id, page_num, display_page_num, score)` with 0-indexed `page_num` (int-cast) and `display_page_num = page_num + 1`; malformed/identity-missing points are skipped, never raised. A thin `execute_query(client, ...)` wrapper runs the payload (notebook/GPU only — not asserted offline).
- **`src/retrieval/visual/fusion.py`** — `rrf_fuse(visual_ranked, text_ranked, *, k=60)` implements `score += 1/(k+rank+1)` per tier keyed on `(doc_id, page_num)`, returning entries sorted by descending fused score with a stable `(doc_id, page_num)` tie-break (deterministic). `to_retrieval_hits(fused, lookup, *, visual_only_ids=frozenset())` maps each fused page → canonical `RetrievalHit` (0-indexed `page_num`, `display_page_num=page_num+1`, `score=round(rrf_score,4)`, `source="visual"` when text-absent else `"fused"`); image-only pages (absent from `lookup`) keep `snippet=""`/`evidence_text=""` via the `TextLookupRecord` empty default (mirrors `_bounded_evidence_text` ou3 fallback). stdlib + `src.retrieval.models` only.
- **`src/retrieval/visual/repository.py`** — `save_visual_index_run(db_path, run)` (INSERT ... ON CONFLICT(run_id) DO UPDATE, parameterized, `built_at` COALESCE to now) and `get_latest_visual_index_run_id(db_path)` (ORDER BY built_at DESC, run_id DESC LIMIT 1; `None` when empty). Targets the `visual_index_runs` table (Plan 01 schema, with `model_version`/`collection_name`).
- **`src/retrieval/visual/run.py`** — `plan_visual_run(pages_meta, *, model_version, version=1)` hashes the sorted `(doc_id, page_num, filename)` identifier tuples (no page text, no image bytes), sets `run_id = deterministic_visual_run_id(content_hash)`, counts = distinct docs / total pages (ALL pages incl. image-only — does NOT reuse the text indexer's empty-text exclusion). `build_visual_index_run(...)` plans + persists via `save_visual_index_run`; the GPU embed/upsert is the notebook's job.
- **4 offline test modules (19 new tests):** `test_query_payload.py` (two-stage shape + version + candidate identity mapping + skip/cast/empty-payload edges), `test_fusion.py` (both-tier outranking, known fused order, image-only-page survival, stable tie-break, default k=60), `test_fused_hits.py` (0/1-index, source tags, empty evidence for image-only, missing-lookup safety, rank-order preservation), `test_run_versioning.py` (ON CONFLICT idempotency = 1 row, latest-run lookup, no-raw-content column guarantee, plan determinism + image-only counts, corpus-change run_id shift, build+persist).

## Verification

- `venv\Scripts\python.exe -m pytest tests/retrieval/visual/test_query_payload.py -x -q` → **4 passed, 2 skipped** (the 2 skips are qdrant-client-absent `build_query_payload` shape assertions; they run on Colab — the pure mapping tests run unconditionally).
- `venv\Scripts\python.exe -m pytest tests/retrieval/visual/test_fusion.py tests/retrieval/visual/test_fused_hits.py -x -q` → **9 passed**.
- `venv\Scripts\python.exe -m pytest tests/retrieval/visual/test_run_versioning.py -x -q` → **6 passed**.
- Full offline suite: `venv\Scripts\python.exe -m pytest -q` → **361 passed, 7 skipped, 0 failed** in ~156s (Wave 1 was 342 passed / 5 skipped; +19 tests, +2 qdrant-skips, no regressions).
- Offline-import proof: `import src.retrieval.visual.querier, src.retrieval.visual.fusion, src.retrieval.visual.run, src.retrieval.visual.repository` succeeds with no qdrant-client installed.
- Privacy/identity grep clean: no `image_blob` / `page_text` in querier.py, fusion.py, repository.py; the only `run.py` match is a docstring line explaining the tier does NOT reuse `load_indexable_pages` (no code use).
- Metric-integrity honored: every new test asserts deterministic plumbing (RRF math, DTO mapping, payload shape, run versioning) — none fabricates an embedding/score and asserts a quality metric off it.

## Deviations from Plan

None — plan executed exactly as written. The plan's `_PAGES_META`-style fixtures, the `TextLookupRecord` lookup shape, the `VisualCandidate` frozen dataclass, and the `source` tag logic all landed as specified.

## Authentication Gates

None — the visual retrieval logic is provider-free; no API keys or logins involved.

## Known Stubs

None. This plan deliberately delivers only the offline, deterministic retrieval logic. The GPU embedder forward pass, the live Qdrant query/upsert execution, and the recall/ndcg/citation numbers are out of scope (they land in the Colab notebook deliverable, Plan 04) — not stubs. `execute_query` is a thin real wrapper over `client.query_points`, exercised only where a live populated collection exists (notebook), consistent with the metric-integrity split.

## Threat Surface Scan

No new security-relevant surface beyond the plan's `<threat_model>`. All five registered threats are mitigated and tested:
- **T-05-06 (fused page identity):** `rrf_fuse` + `to_retrieval_hits` key on 0-indexed `(doc_id, page_num)`; tests assert `display_page_num = page_num + 1`.
- **T-05-07 (visual_index_runs row):** rows store counts/run_id/model_version/collection_name only; `test_persisted_row_carries_no_raw_content` asserts no `image_blob`/`page_text` columns.
- **T-05-08 (image-only evidence_text):** image-only pages keep `evidence_text=""`; asserted in `test_image_only_page_has_empty_snippet_and_evidence_text`.
- **T-05-09 (RRF non-determinism):** stable `(doc_id, page_num)` tie-break; `test_rrf_stable_tie_break_is_deterministic` asserts exact known order and re-run identity.
- **T-05-10 (run provenance):** deterministic `visual-built-{hash}` run_id; `test_plan_visual_run_deterministic_and_counts_image_only_pages` asserts reproducibility.

## Notes for Downstream Plans

- The notebook (Plan 04) imports `build_query_payload` for the live query and `rrf_fuse` + `to_retrieval_hits` for fusion, so plumbing is shared with these offline tests; only the GPU forward pass + the printed numbers are notebook-exclusive.
- `to_retrieval_hits` expects a `lookup: dict[(doc_id,page_num) -> TextLookupRecord]` built from the text tier and a `visual_only_ids` set (pages that appeared only in the visual ranked list). The fusion-entry seam in `retriever.py` (a later plan) must populate both from the live text + visual candidate lists.
- `plan_visual_run` takes identifier-only `pages_meta` `(doc_id, page_num, filename)` for ALL pages — the notebook should build this from `pages` (incl. image-only `5543408c:0,1,2,7`), NOT from `load_indexable_pages`.
- `VisualCandidate.score` is the raw MAX_SIM rerank score; RRF uses RANK, not score, so the incomparable visual-cosine vs text-lexical scales never mix.

## Self-Check: PASSED
