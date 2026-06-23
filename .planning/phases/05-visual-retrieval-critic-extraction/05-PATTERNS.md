# Phase 5: Visual Retrieval Tier (VISUAL-01, VISUAL-02) - Pattern Map

**Mapped:** 2026-06-23
**Files analyzed:** 21 (15 new, 6 modified) + 1 notebook deliverable
**Analogs found:** 19 / 21 (2 genuinely new: ColQwen GPU embedder, Qdrant collection builder — no in-repo analog, but their privacy/seam shape is mirrored)

> All analogs verified against `src/` HEAD, NOT the stale `.planning/ROADMAP.md`. The existing **text retrieval tier** (`src/retrieval/`) is the structural template for the new **visual tier** (`src/retrieval/visual/`); the existing **eval seam** (`src/eval/`) consumes the fused `RetrievalHit` unchanged; the **lazy-import seams** (`ragas_quality.py`, `tracing.py`) are the model for guarding `colpali-engine`/`torch`/`qdrant` out of the offline suite.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/retrieval/visual/__init__.py` | package | — | `src/retrieval/` package layout | exact |
| `src/retrieval/visual/embedder.py` (NEW) | service (GPU seam) | transform (image/text → multivector) | `src/eval/ragas_quality.py` (lazy heavy-dep seam) | role-match (lazy-import seam, not the model) |
| `src/retrieval/visual/pooling.py` (NEW) | utility (pure) | transform (patch grid → pooled rows/cols) | `src/retrieval/indexer.py` `normalize_index_text`/`make_page_snippet` (pure deterministic helpers) | role-match |
| `src/retrieval/visual/collection.py` (NEW) | utility/config (pure) | request-response (Qdrant config + upsert/query payload builders) | `src/retrieval/repository.py` (SQL builders) + RESEARCH Pattern 3/4 | partial (Qdrant has no in-repo analog; mirror the pure-builder shape) |
| `src/retrieval/visual/querier.py` (NEW) | service | request-response (two-stage prefetch+rerank) | `src/retrieval/retriever.py` `_fts_candidates` (candidate fetch + map) | role-match |
| `src/retrieval/visual/fusion.py` (NEW) | utility (pure) | transform (RRF over ranked tiers → `RetrievalHit`) | `src/retrieval/retriever.py` `_score_candidate` (builds `RetrievalHit` + score components) | role-match |
| `src/retrieval/visual/run.py` (NEW) | service | CRUD (versioned `sdf_page_images` run, mirror `retrieval_index_runs`) | `src/retrieval/indexer.py` `build_retrieval_index` + `_deterministic_run_id` | exact (mirror versioning) |
| `src/retrieval/visual/models.py` (NEW, optional) | model | — | `src/retrieval/models.py` (`RetrievalIndexRun`, `RetrievalScoreComponents`) | exact |
| `src/retrieval/models.py` (MODIFY) | model | — | self — extend `RetrievalScoreComponents.source` tag, add visual run DTO | exact |
| `src/retrieval/retriever.py` (MODIFY) | service | request-response | self — add fusion entry seam + config-select; trace allowlist unchanged | exact |
| `src/db/schema.py` (MODIFY) | migration/schema | — | self — add `visual_index_runs` (mirror `retrieval_index_runs`) + idempotent migrate | exact |
| `src/eval/retrieval_eval_runner.py` (MODIFY) | service (eval) | batch | self — config-selectable text-only vs visual-fused retrieval source | exact |
| `src/config.py` (MODIFY) | config | — | self — add `retrieval_mode` flag (text-only / visual-fused) | exact |
| `scripts/repair_gold_ex3_mojibake.py` (NEW) | script (data fix) | CRUD | `scripts/relabel_gold_field_rules.py` (idempotent guarded UPDATE) | exact |
| `notebooks/visual_retrieval_colab.ipynb` (NEW) | notebook deliverable | batch | none (no `.ipynb` in repo) | no analog (greenfield) |
| `tests/retrieval/visual/conftest.py` (NEW) | test fixture | — | `tests/conftest.py` (`tmp_db_path`) + `tests/test_retrieval_eval_runner.py` helpers | exact |
| `tests/retrieval/visual/test_*.py` (NEW ×10) | test | — | `tests/test_retrieval_eval_runner.py`, `tests/test_retriever.py` | exact |
| `tests/eval/test_gold_mojibake_repair.py` (NEW) | test | — | `tests/eval/test_ragas_quality.py` structure | role-match |

---

## Pattern Assignments

### `src/retrieval/visual/embedder.py` (service, GPU seam) — NEW

**Analog:** `src/eval/ragas_quality.py` (the lazy-import seam for a heavy/optional dependency). **NOT a model mock** — this loads the real ColQwen2.5; the seam pattern is only "import the heavy dep inside the function body so importing the module is offline-safe."

**Lazy-import-inside-function pattern to mirror** (`src/eval/ragas_quality.py:106-137`):
```python
def build_ragas_scorer(...) -> RagasScorer:
    """All ragas / langchain_google_genai imports are lazy (inside this function),
    so importing this module stays offline-safe."""
    from src.config import get_settings
    ...
    from ragas.metrics import Faithfulness, ResponseRelevancy   # heavy import INSIDE the body
    from langchain_google_genai import ChatGoogleGenerativeAI
```
Module docstring contract to copy verbatim in spirit (`src/eval/ragas_quality.py:1-16`): *"Importing this module is offline-safe: it imports neither X nor Y at module load. All optional SDK imports live inside function bodies."* For the embedder: `import torch`, `from colpali_engine.models import ColQwen2_5, ColQwen2_5_Processor`, and any `qdrant_client` model use must live inside functions, never at module top.

**Graceful-absence guard to mirror** (`src/eval/retrieval_eval_runner.py:265-277`): heavy path wrapped so `ImportError` (dep not installed offline) degrades, never crashes:
```python
from src.eval.ragas_quality import build_ragas_scorer, compute_ragas_quality
scorer = ragas_scorer
if scorer is None:
    try:
        scorer = build_ragas_scorer()
    except (AnswerConfigurationError, ImportError):
        return   # prerequisites absent → skip, keep core metrics
```
**GPU-config reference (from RESEARCH Pattern 1, notebook-only execution):** `ColQwen2_5.from_pretrained("vidore/colqwen2.5-v0.2", torch_dtype=torch.bfloat16, device_map="cuda:0").eval()`. The embedder forward pass is the ONLY GPU-bound step and runs only in the Colab notebook — no offline test asserts a quality metric off it (metric-integrity rule, CONTEXT.md §"No fabrication").

---

### `src/retrieval/visual/pooling.py` (utility, pure) — NEW

**Analog:** `src/retrieval/indexer.py` pure deterministic helpers (`normalize_index_text` :236, `make_page_snippet` :242, `compute_indexable_corpus_fingerprint` :214). These are dependency-free, fully unit-testable functions — the model for offline-testable pooling math.

**Pure-helper shape to mirror** (`src/retrieval/indexer.py:236-246`):
```python
def normalize_index_text(text: str | None) -> str:
    """Normalize page text for hashing, snippets, and FTS ingestion."""
    return _WHITESPACE_RE.sub(" ", text or "").strip()

def make_page_snippet(text: str | None, *, max_chars: int = _SNIPPET_MAX_CHARS) -> str:
    """Return a short, verbatim-order, whitespace-normalized prefix."""
    normalized = normalize_index_text(text)
    return normalized[:max_chars]
```
**Pooling math (from RESEARCH Pattern 2):** `patches = emb[mask].view(n_patches_x, n_patches_y, dim); pooled_rows = patches.mean(dim=0); pooled_cols = patches.mean(dim=1)`. Keep this a pure tensor-reshape function that accepts an already-computed embedding tensor + grid dims (NO model load), so `tests/retrieval/visual/test_pooling.py` can drive it with a synthetic tensor of known shape and assert shapes only — never a fabricated similarity score. Derive `dim` from `emb.shape[-1]` if `model.dim` is absent (RESEARCH A2).

---

### `src/retrieval/visual/collection.py` (utility/config, pure) — NEW

**Analog:** `src/retrieval/repository.py` SQL-builder style (pure string/dict construction, no I/O at build time) + RESEARCH offline-testable config builder (RESEARCH "Code Examples").

**Offline-testable builder to mirror** (RESEARCH §Code Examples, lines 405-417):
```python
def build_vectors_config():
    from qdrant_client import models                 # lazy import inside fn (offline-safe)
    base = dict(size=128, distance=models.Distance.COSINE)
    msim = models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM)
    return {
        "original": models.VectorParams(**base, multivector_config=msim,
                                        hnsw_config=models.HnswConfigDiff(m=0)),  # HNSW OFF
        "mean_pooling_columns": models.VectorParams(**base, multivector_config=msim),
        "mean_pooling_rows": models.VectorParams(**base, multivector_config=msim),
    }
# Test asserts: config["original"].hnsw_config.m == 0; all comparators MAX_SIM; size==128.
```
**Upsert/query-payload identity contract (CRITICAL — RESEARCH Pitfall 6):** payload MUST carry `{"doc_id": <str>, "page_num": <0-indexed int>}`. This mirrors the 0-indexed `page_num` invariant throughout the text tier — see `src/retrieval/repository.py:228` (`page.page_num` stored as-is, 0-indexed) and `display_page_num = page.page_num + 1`. Deterministic point IDs = hash(doc_id+page_num), mirroring `_deterministic_run_id` (`indexer.py:249`), for idempotent re-upsert (RESEARCH Pitfall 8).

---

### `src/retrieval/visual/querier.py` (service) — NEW

**Analog:** `src/retrieval/retriever.py` `_fts_candidates` (:247-279) — fetch candidates, map rows → typed objects carrying `(doc_id, page_num, display_page_num)`. The querier does the Qdrant equivalent.

**Candidate-fetch-then-map shape to mirror** (`src/retrieval/retriever.py:247-279`): SELECT/query → list of typed candidates with the page-identity tuple; the query payload is pure-constructible and unit-testable separately from execution.

**Two-stage query (RESEARCH Pattern 4):**
```python
response = client.query_points(
    collection_name="sdf_page_images_v1",
    query=query_embedding,
    prefetch=[
        models.Prefetch(query=query_embedding, limit=prefetch_limit, using="mean_pooling_columns"),
        models.Prefetch(query=query_embedding, limit=prefetch_limit, using="mean_pooling_rows"),
    ],
    limit=search_limit, with_payload=True, with_vector=False,
    using="original",   # full-multivector MAX_SIM rerank
)
```
Split into (a) a PURE `build_query_payload(...)` that `test_query_payload.py` asserts (2 pooled prefetches + `using="original"`), and (b) execution that needs a populated collection (notebook/GPU only).

---

### `src/retrieval/visual/fusion.py` (utility, pure) — NEW

**Analog:** `src/retrieval/retriever.py` `_score_candidate` (:307-336) — the canonical "build a `RetrievalHit` with `RetrievalScoreComponents`" mapping. Fusion produces the SAME DTO so the eval/RAG path is unchanged.

**RetrievalHit construction to mirror exactly** (`src/retrieval/retriever.py:318-336`):
```python
components = RetrievalScoreComponents(
    fts_score=..., lexical_score=..., token_coverage=...,
    phrase_bonus=..., proximity_bonus=..., source=source,   # ← add "fused"/"visual" here
)
return RetrievalHit(
    doc_id=candidate.doc_id,
    filename=candidate.filename,
    page_num=candidate.page_num,                 # 0-indexed
    display_page_num=candidate.display_page_num, # page_num + 1
    score=round(score, 4),
    score_components=components,
    snippet=make_query_snippet(text, terms),
    evidence_text=_bounded_evidence_text(candidate.page_text, fallback=candidate.indexed_snippet),
)
```
**RRF math (RESEARCH Pattern 5, k=60):** `score(page) = Σ_tiers 1/(k + rank + 1)`, keyed on `(doc_id, page_num)`. For image-only pages with no text-tier match, `snippet`/`evidence_text` stay empty — consistent with the `_bounded_evidence_text` empty-page fallback behavior (`retriever.py:438-457`, established in `quick-260611-ou3`). `source` tag: `"fused" | "visual" | "fts"` (extends the existing `RetrievalScoreComponents.source` field, `models.py:112`).

---

### `src/retrieval/visual/run.py` (service, CRUD) — NEW

**Analog:** `src/retrieval/indexer.py` `build_retrieval_index` (:69-121) + `_deterministic_run_id` (:249) + `src/retrieval/repository.py` `save_index_run` (:87-130). This is the versioning template the CONTEXT explicitly says to mirror.

**Deterministic run-id + run DTO to mirror** (`src/retrieval/indexer.py:84-98, 249-250`):
```python
run_id = _deterministic_run_id(status, fingerprint.content_hash)   # f"retrieval-{status}-{hash[:16]}"
run = RetrievalIndexRun(run_id=run_id, status=status, built_at=None,
    source_document_count=..., source_page_count=..., indexed_page_count=...,
    content_hash=fingerprint.content_hash, previous_content_hash=previous_hash, ...)
```
For visual: a `visual-built-{hash[:16]}` run_id, a `visual_index_runs` row (counts + run_id + collection name + model version ONLY — never image bytes), persisted via an `_insert` mirroring `repository._insert_index_run` (:303-336). Note: visual is a **separate tier** — it does NOT relax `indexer.py:192` empty-text exclusion (RESEARCH Anti-Pattern; CONTEXT.md §Motivating defect). The visual run indexes ALL pages incl. image-only `5543408c:0,1,2,7`.

---

### `src/retrieval/models.py` (MODIFY) — model

**Analog:** self. Extend the existing `RetrievalScoreComponents.source` semantics (:103-112) to accept `"visual"`/`"fused"`, and add a `VisualIndexRun` DTO mirroring `RetrievalIndexRun` (:45-59). Preserve the module's privacy docstring (`models.py:1-6`): *"These models intentionally expose page metadata, hashes, and display page numbers, but not raw page text."* Visual DTOs expose counts/run_id/model_version only — never image bytes.

---

### `src/retrieval/retriever.py` (MODIFY) — service, fusion entry seam

**Analog:** self. Add the fusion entry seam where `retrieve_evidence` (:343-390) currently returns text-only hits. The trace allowlist `_RETRIEVAL_TRACE_ALLOWED_KEYS` (:31-41) stays the privacy gate — add only numeric/identifier visual keys if any (e.g. `visual_hit_count`), NEVER image bytes or page text. The `@observe`-decorated entry + `_safe_update_trace_metadata` (:501-511) wrapper pattern is the template; mirror it for any fused-trace metadata.

**Config-select seam:** route between text-only and visual-fused based on the new `retrieval_mode` setting; keep `retrieve_evidence`'s signature stable so `retrieval_eval_runner.py:153` calls it unchanged.

---

### `src/db/schema.py` (MODIFY) — migration/schema

**Analog:** self — `retrieval_index_runs` table (:235-247) is the exact template for a `visual_index_runs` table. Mirror the idempotent additive-migration helper `_migrate_retrieval_index_pages_table` (:407-415) and FTS-optional guard `_init_retrieval_index_fts` (:358-370) for any new table so `init_db` stays idempotent on pre-existing local DBs.

**Table template to mirror** (`src/db/schema.py:235-247`):
```sql
CREATE TABLE IF NOT EXISTS retrieval_index_runs (
    run_id TEXT PRIMARY KEY, status TEXT NOT NULL,
    built_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    source_document_count INTEGER NOT NULL DEFAULT 0,
    source_page_count INTEGER NOT NULL DEFAULT 0,
    indexed_page_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT, previous_content_hash TEXT,
    is_stale BOOLEAN NOT NULL DEFAULT 0, stale_reason TEXT, error_reason TEXT
);
```
The `pages.image_blob BLOB` column (:24-31) is the read-only embedding source — verify per-page blobs exist for `5543408c` image-only pages (RESEARCH confirms all 11 present).

---

### `src/eval/retrieval_eval_runner.py` (MODIFY) — service (eval), config-selectable mode

**Analog:** self. The fusion result feeds the eval path with ZERO metric-code change — the runner already consumes ONLY `(doc_id, page_num)` identities (`retrieval_eval_runner.py:153-155`):
```python
retrieval_result = retrieve_evidence(db_path, query_text, top_k=max_k)
retrieved_pairs = [(hit.doc_id, int(hit.page_num)) for hit in retrieval_result.hits]
```
Add a `retrieval_mode` param threaded to `retrieve_evidence` (text-only vs visual-fused) so the same gold set evaluates both modes (Phase 7 benchmark, kept config-selectable per CONTEXT). The `_EVALUATION_TRACE_ALLOWED_KEYS` allowlist (:46-60) and its docstring (*"never includes query text, target content, retrieved snippets, page text..."*) is the privacy gate — extend with numeric keys only.

`compute_retrieval_recall_at_k` (`src/eval/retrieval_metrics.py:63`) and `compute_page_level_citation_accuracy` (:117) are UNCHANGED — they key on `(doc_id, page_num)` (:43 `PageId = tuple[str, int]`).

---

### `scripts/repair_gold_ex3_mojibake.py` (NEW) — script (data fix)

**Analog:** `scripts/relabel_gold_field_rules.py` (exact). Idempotent guarded UPDATE pattern, prints only ids/row-counts (never page text/secrets), gitignored-db safety note.

**Idempotent-guarded-update + root-path bootstrap to mirror** (`scripts/relabel_gold_field_rules.py:23-69`):
```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.db.schema import _connect
...
cursor = conn.execute(
    "UPDATE gold_retrieval_queries SET query_text = ? WHERE query_id = ? AND query_text = ?",
    (repaired_text, query_id, old_mojibake_text),
)
return cursor.rowcount   # guarded → second run changes 0 rows
```
Target the 4 `rq_ex3_*` rows in `gold_retrieval_queries` (schema `:219-224`): replace U+FFFD (`�`) → `Ä` ("`�KTA`" → "`ÄKTA`"); assert no other gold rows affected (RESEARCH Runtime State Inventory). Header docstring mirrors `relabel_gold_field_rules.py:1-14`.

---

### `notebooks/visual_retrieval_colab.ipynb` (NEW) — deliverable, NO in-repo analog

**Location:** `notebooks/` (new dir; no existing `.ipynb` anywhere — confirmed via glob). The phase reproducibility artifact. Pinned install → download `vidore/colqwen2.5-v0.2` → decode `image_blob` → embed (bf16, L4) → build `sdf_page_images_v1` (local Qdrant `path=...`) → two-stage retrieve → run real eval → print metrics table incl. `rq_ex3_*` lift. Imports the SAME pure `src/retrieval/visual/` builders so plumbing is shared with the offline tests; only the GPU forward pass + the printed numbers are notebook-exclusive. Install cell pins from RESEARCH §Standard Stack: `colpali-engine>=0.3.11,<0.4`, `transformers>=4.45,<4.50`, `qdrant-client>=1.17,<2.0`, `pypdfium2`, `pillow`. Prints `colpali_engine.__version__`/`transformers.__version__` + a one-image smoke embed before the full build (RESEARCH Pitfall 4).

---

### `tests/retrieval/visual/` package + tests (NEW) — test

**Analog:** `tests/conftest.py` (`tmp_db_path` fixture, :12-15) + `tests/test_retrieval_eval_runner.py` (tmp_path SQLite + direct INSERT helpers + trace-capture monkeypatch).

**tmp_path SQLite fixture to mirror** (`tests/conftest.py:12-15`):
```python
@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_compliance.db")
```
**Direct-INSERT seed helpers to mirror** (`tests/test_retrieval_eval_runner.py:16-39`): `_insert_document`, `_insert_gold_query`, `_insert_gold_target` build a real SQLite corpus via parameterized INSERTs — for visual tests, an analogous `_insert_page_with_blob` seeds `pages.image_blob`.

**Trace-allowlist assertion to mirror** (`tests/test_retrieval_eval_runner.py:42-79`): capture `safe_update_current_trace` calls, then assert metadata keys ⊆ allowlist AND that a list of forbidden fragments (`"page_text"`, `"snippet"`, `"secret"`, ...) is absent — `test_privacy_allowlist.py` adds `"image_blob"`/bytes-marker to that forbidden list.

**GPU guard (Wave 0 gap):** register a `gpu` marker in `pyproject.toml` `[tool.pytest.ini_options]` (currently only `testpaths`/`addopts` at :44-46 — `markers` must be ADDED) and a `@pytest.mark.gpu` + skip-unless-CUDA guard so the embedder forward-pass tests never run offline. No offline test fabricates an embedding/score and asserts a quality metric (metric-integrity rule).

---

## Shared Patterns

### Lazy-import seam for heavy/optional deps (the model for colpali/torch/qdrant)
**Source:** `src/eval/ragas_quality.py:1-16, 106-137`; `src/tracing.py:30-77`
**Apply to:** `embedder.py`, `querier.py`, `collection.py`, `run.py`, the notebook helpers
- Module top-level imports stay offline-safe; ALL heavy SDK imports (`torch`, `colpali_engine`, `qdrant_client.models`) live INSIDE function bodies.
- Graceful degradation on `ImportError` (`retrieval_eval_runner.py:265-277`): absent dep → skip path, never crash.
- `src/tracing.py:59-77` shows the no-op-fallback decorator pattern when an optional dep is missing — applicable if any visual module needs an import-guarded decorator.
- **CRITICAL distinction (CONTEXT.md §35):** this is "heavy dep loaded when present," NOT mocking the model to fabricate results.

### Privacy / trace-allowlist + evidence boundary contract
**Source:** `src/retrieval/retriever.py:31-41` (`_RETRIEVAL_TRACE_ALLOWED_KEYS`); `src/retrieval/indexer.py:32-42` (`_INDEX_TRACE_ALLOWED_KEYS`); `src/eval/retrieval_eval_runner.py:46-60` (`_EVALUATION_TRACE_ALLOWED_KEYS`); `src/tracing.py:103-146` (`_safe_trace_value` drops bytes/mappings; `filter_trace_metadata` allowlists); `quick-260611-ou3-SUMMARY.md` (evidence boundary)
**Apply to:** every new/modified visual module that touches a trace or persists a row
- Traces & persisted rows carry counts / scores / run_ids / reason codes ONLY.
- NEVER: `image_blob` bytes, full page text, full corpus hash, secrets. `src/tracing.py:118-119` already drops `bytes/bytearray/memoryview` — visual code must never try to put image bytes in metadata anyway.
- ou3 evidence contract: `evidence_text` is bounded (≤2000 chars, `retriever.py:46,438-457`), in-memory only, and NOT in any allowlist — fused image-only hits keep empty `evidence_text` (no text to ground), consistent with the `_bounded_evidence_text` fallback.
- `visual_index_runs` rows store counts + run_id + collection name + model version only.

### 0-indexed `page_num` identity invariant
**Source:** `src/retrieval/repository.py:228` (stores `page.page_num` 0-indexed; `display_page_num = page.page_num + 1`); `src/eval/retrieval_metrics.py:43` (`PageId = tuple[str, int]`); `src/eval/retrieval_eval_runner.py:154`; gold targets `page_num=2` 0-indexed
**Apply to:** `collection.py` (Qdrant payload), `querier.py`, `fusion.py`
- Qdrant payload + fused `RetrievalHit.page_num` MUST be 0-indexed; `display_page_num = page_num + 1` for citations only.
- A wrong index silently yields recall@k = 0 despite correct retrieval (RESEARCH Pitfall 6). Add `test_payload.py` round-trip identity assertion.

### Versioned index-run pattern
**Source:** `src/retrieval/indexer.py:69-121, 249-250`; `src/retrieval/repository.py:87-130, 169-186`; `src/db/schema.py:235-247`
**Apply to:** `run.py`, `schema.py` (`visual_index_runs`)
- Deterministic content-hash → `_deterministic_run_id` → upsert run row with `ON CONFLICT(run_id) DO UPDATE`.
- `load_latest_index_run`-style retrieval of the newest run; mirror `get_latest_retrieval_index_run_id` (`src/eval/repository.py:624`) for a `get_latest_visual_index_run_id`.

### Provider-free module docstring + offline-safe DB access
**Source:** `src/retrieval/indexer.py:1-7`; `src/retrieval/repository.py:1-6`; `src/retrieval/models.py:1-6`
**Apply to:** all new `src/retrieval/visual/*.py`
- Lead each module with the provider-free / privacy docstring (reads metadata + image bytes for embedding only; exposes hashes/counts/run_ids/identifiers — never image bytes or page text in DTOs/traces).
- DB reads via `from src.db.schema import _connect, init_db` (`indexer.py:15`), parameterized SQL only.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `notebooks/visual_retrieval_colab.ipynb` | notebook | batch | No `.ipynb` exists in the repo (verified via glob). New `notebooks/` dir; greenfield. Privacy/install conventions drawn from RESEARCH §Standard Stack and the scripts header style. |
| `src/retrieval/visual/embedder.py` (model load) + `collection.py` (Qdrant client calls) | service/config | transform / request-response | No ColQwen/torch or Qdrant code exists anywhere in `src/` — these are genuinely new integrations. Their *seam shape* (lazy-import, privacy allowlist, 0-indexed identity, pure-builder split) is fully mirrored from the analogs above; only the third-party API surface is new. Planner should lean on RESEARCH Patterns 1-4 (CITED to HF/Qdrant) for the API calls and the analogs here for structure/privacy. |

---

## Metadata

**Analog search scope:** `src/retrieval/`, `src/eval/`, `src/db/`, `src/pipeline/`, `src/config.py`, `src/tracing.py`, `tests/`, `scripts/`, `notebooks/` (glob)
**Files scanned:** 14 source/test/script files read in full or targeted; 1 SUMMARY; CONTEXT + RESEARCH
**Pattern extraction date:** 2026-06-23

## PATTERN MAPPING COMPLETE
