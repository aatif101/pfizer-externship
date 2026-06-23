---
phase: 05-visual-retrieval-critic-extraction
plan: 01
subsystem: retrieval
tags: [visual-retrieval, colqwen, qdrant, schema, offline-plumbing, tdd]
requires: []
provides:
  - "src/retrieval/visual package (provider-free, offline-safe)"
  - "build_vectors_config (3-named-vector Qdrant config: original HNSW-off, pooled HNSW-on, MAX_SIM size=128)"
  - "build_upsert_point + deterministic_point_id (0-indexed page_num payload, idempotent ids)"
  - "mean_pool_rows_cols (pure row/col patch-grid reshape, torch-lazy)"
  - "blob_to_image (deterministic PNG->PIL RGB decode)"
  - "VisualIndexRun DTO + deterministic_visual_run_id"
  - "visual_index_runs table + idempotent migration"
  - "pytest gpu marker"
affects:
  - "src/db/schema.py (additive: new table + migration)"
  - "pyproject.toml (pytest markers)"
tech-stack:
  added: []
  patterns:
    - "Lazy-import seam: heavy SDKs (torch, qdrant_client) imported inside function bodies so modules stay offline-importable"
    - "Pure builder split: config/payload construction testable without a live client; GPU/Qdrant execution deferred to the Colab notebook"
    - "0-indexed page_num identity invariant carried into the Qdrant payload"
    - "Privacy boundary: DTOs/payloads/rows carry counts/run_ids/identifiers only, never image bytes or page text"
key-files:
  created:
    - src/retrieval/visual/__init__.py
    - src/retrieval/visual/models.py
    - src/retrieval/visual/pooling.py
    - src/retrieval/visual/collection.py
    - tests/retrieval/visual/__init__.py
    - tests/retrieval/visual/conftest.py
    - tests/retrieval/visual/test_blob_decode.py
    - tests/retrieval/visual/test_pooling.py
    - tests/retrieval/visual/test_collection.py
    - tests/retrieval/visual/test_payload.py
  modified:
    - src/db/schema.py
    - pyproject.toml
decisions:
  - "Lazy torch/qdrant imports keep the visual package importable with no heavy deps; offline tests importorskip those deps and skip cleanly when absent (qdrant-client is not installed locally)"
  - "Offline tests assert SHAPE/IDENTITY only — never a fabricated similarity/recall/ndcg number (metric-integrity rule)"
  - "visual_index_runs mirrors retrieval_index_runs + model_version/collection_name; migration is additive ALTER guarded by _table_columns (idempotent, non-destructive)"
metrics:
  duration: ~25 min
  completed: 2026-06-23
---

# Phase 5 Plan 01: Visual Retrieval Plumbing Foundation Summary

Provider-free, offline-testable foundation for the ColQwen2.5 visual retrieval tier: the pure Qdrant collection-config/upsert-payload builders, row/column patch-grid pooling, deterministic blob decode, the `VisualIndexRun` DTO, the `visual_index_runs` schema table with an idempotent migration, and the pytest `gpu` marker that keeps GPU code out of the offline suite. Every contract downstream plans (querier, fusion, run versioning, embedder, notebook) build against is now established — all 100% deterministic and unit-tested without a GPU.

## What Was Built

- **`src/retrieval/visual/` package** — provider-free, offline-safe. Module docstrings state the privacy/offline contract; all heavy SDK imports (`torch`, `qdrant_client`) live inside function bodies.
- **`collection.py`** — `build_vectors_config()` (3 named vectors: `original` HNSW-off via `HnswConfigDiff(m=0)`, `mean_pooling_rows`/`mean_pooling_columns` HNSW-on, all `size=128` COSINE MAX_SIM), `collection_name(version)`, `deterministic_point_id()` (sha256 of `doc_id:page_num`), `build_upsert_point()` (payload `{doc_id, page_num(0-indexed int)}` only — no bytes/text).
- **`pooling.py`** — `blob_to_image()` (lazy PIL, deterministic PNG→RGB), `mean_pool_rows_cols()` (pure tensor reshape: row/col mean-pool + concat of non-image tokens; `dim` derived from `emb.shape[-1]`; torch lazy).
- **`models.py`** — frozen `VisualIndexRun` DTO (counts/run_id/model_version/collection_name only — no `image_blob`/`page_text` fields) + `deterministic_visual_run_id()`.
- **`src/db/schema.py`** — `visual_index_runs` table (mirrors `retrieval_index_runs` + `model_version`/`collection_name`) + `_migrate_visual_index_runs_table()` additive guarded migration called inside `init_db`, plus two indexes.
- **`pyproject.toml`** — registered the `gpu` pytest marker.
- **10 offline test modules' worth of behaviors** across 4 test files; schema/DTO/marker/blob-decode (Task 1), pooling shapes + blob decode (Task 2), collection config + payload identity (Task 3).

## Verification

- `venv\Scripts\python.exe -m pytest tests/retrieval/visual -q` → **10 passed, 5 skipped** (the 5 skips are qdrant-client-absent config/payload tests — they run on Colab; the pure `collection_name`/`deterministic_point_id` checks run unconditionally and pass).
- Full offline suite: `venv\Scripts\python.exe -m pytest -q` → **342 passed, 5 skipped, 0 failed** — the additive schema change caused no regressions.
- Offline-import proof: `import src.retrieval.visual.collection, src.retrieval.visual.pooling, src.retrieval.visual.models` succeeds with neither torch (blocked) nor qdrant-client installed.
- No module-top `import torch` / `import qdrant_client` in any `src/retrieval/visual/*.py` (grep clean).
- No `image_blob` / `page_text` in `models.py` or `collection.py` (grep clean).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `importorskip` ordering in `test_all_vectors_size_128_and_max_sim`**
- **Found during:** Task 3
- **Issue:** The test ran `from qdrant_client import models` before `pytest.importorskip("qdrant_client")`, so it raised `ModuleNotFoundError` (hard failure) instead of skipping cleanly when qdrant-client is absent locally.
- **Fix:** Moved `pytest.importorskip("qdrant_client")` to the first line of the test, before the `qdrant_client` import.
- **Files modified:** tests/retrieval/visual/test_collection.py
- **Commit:** d4358b4

## Authentication Gates

None — the visual plumbing tier is provider-free; no API keys or logins involved.

## Known Stubs

None. This plan deliberately delivers only the offline, deterministic plumbing contracts. The GPU-bound embedder, the live Qdrant build/query, and the recall/ndcg numbers are out of scope for plan 05-01 (they land in later plans + the Colab notebook deliverable per the phase plan), not stubs.

## Notes for Downstream Plans

- `build_upsert_point` keeps `page_num` 0-indexed (int-cast); `display_page_num = page_num + 1` is a citation-only concern for the fusion layer.
- `mean_pool_rows_cols` returns `(pooled_rows, pooled_cols)` with non-image (special/query-augmentation) tokens concatenated, matching the Qdrant ColPali pattern and Pattern 4's `using="original"` rerank expectation.
- The `gpu` marker is registered but unused so far; embedder forward-pass tests in later plans should carry `@pytest.mark.gpu` so they never run offline.
- `visual_index_runs` stores counts/run_id/model_version/collection_name only — the run-versioning plan should persist via an `_insert` mirroring `repository._insert_index_run`, never image bytes.

## Self-Check: PASSED
