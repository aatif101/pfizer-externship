---
phase: 05-visual-retrieval-critic-extraction
plan: 03
subsystem: retrieval
tags: [visual-retrieval, retrieval-mode, fusion-seam, gold-repair, privacy-allowlist, offline-plumbing]
requires:
  - "src/retrieval/visual/fusion.py (Plan 02: rrf_fuse, to_retrieval_hits, TextLookupRecord)"
  - "src/retrieval/retriever.py retrieve_evidence text-tier gate + trace allowlist"
  - "src/config.py Settings (pydantic-settings) + get_settings lru_cache"
provides:
  - "retrieval_mode config setting (text-only default | visual-fused)"
  - "retrieve_evidence routing: text-only gate vs visual-fused RRF seam (stable signature)"
  - "_fused_evidence seam + _default_visual_query_fn (raises clear RuntimeError, no fabricated score)"
  - "RetrievalScoreComponents.source documented set {lexical, fts, visual, fused}"
  - "scripts/repair_gold_ex3_mojibake.py (idempotent guarded U+FFFD -> A-diaeresis repair)"
  - "trace allowlist extended with numeric/identifier-only visual keys (retrieval_mode, visual_hit_count)"
affects:
  - "src/config.py (additive Field)"
  - "src/retrieval/models.py (docstring-only)"
  - "src/retrieval/retriever.py (additive kwargs + seam + allowlist)"
tech-stack:
  added: []
  patterns:
    - "Optional-kwarg back-compat: retrieval_mode/visual_query_fn added without changing the existing positional call (db_path, question, top_k)"
    - "Lazy import of the fusion seam inside _fused_evidence keeps retriever offline-importable with no new module-top heavy deps"
    - "Metric-integrity: no-backend visual path raises a clear RuntimeError; only a real (notebook) ranking can fuse — no synthetic score"
    - "Guarded idempotent UPDATE keyed on current value so re-runs change 0 rows (mirrors relabel_gold_field_rules.py)"
    - "Defensive getattr(get_settings(), 'retrieval_mode', 'text-only') tolerates partial Settings stubs"
key-files:
  created:
    - scripts/repair_gold_ex3_mojibake.py
    - tests/eval/test_gold_mojibake_repair.py
    - tests/retrieval/visual/test_mode_select.py
    - tests/retrieval/visual/test_privacy_allowlist.py
  modified:
    - src/config.py
    - src/retrieval/models.py
    - src/retrieval/retriever.py
decisions:
  - "retrieval_mode defaults to text-only so all existing behavior/tests are unchanged; visual-fused is opt-in for the Phase 7 benchmark"
  - "visual-fused without a wired backend raises RuntimeError (never a fabricated similarity/recall) — the real ranking comes only from the Colab notebook (Plan 04)"
  - "Trace allowlist gains only numeric/identifier keys (retrieval_mode, visual_hit_count); image bytes / page text are never allowlisted"
  - "Gold repair is a guarded idempotent UPDATE; the vendor row (no mojibake) is a natural no-op; compliance.db never staged"
metrics:
  duration: ~12 min
  completed: 2026-06-23
---

# Phase 5 Plan 03: Visual Tier Integration Seam Summary

Wired the ColQwen2.5 visual tier into the existing retrieval/eval path without touching any metric code: a config-selectable `retrieval_mode` (text-only default vs visual-fused), a `retrieve_evidence` routing seam that fuses text + visual ranked pages through the Plan-02 RRF fusion while keeping a stable call signature for the eval runner, a documented `source ∈ {lexical, fts, visual, fused}` tag set, an idempotent repair for the corrupted `rq_ex3` gold queries, and proof that the trace allowlist never leaks image bytes or page text. The GPU-bound quality numbers stay deferred to the Colab notebook (Plan 04); a no-backend visual-fused request raises a clear error rather than fabricating a score.

## What Was Built

- **`src/config.py`** — added `retrieval_mode: str = Field(default="text-only", ...)` documenting text-only (Phase 1 baseline) vs visual-fused (ColQwen2.5 + RRF, Phase 7 benchmark). Default keeps existing behavior unchanged.
- **`src/retrieval/models.py`** — extended the `RetrievalScoreComponents` docstring to document `source ∈ {"lexical", "fts", "visual", "fused"}`. No type change (still a free `str`); existing text-tier construction is unaffected.
- **`src/retrieval/retriever.py`**:
  - `retrieve_evidence` gains two OPTIONAL kwargs — `retrieval_mode: str | None = None` (resolved via `getattr(get_settings(), "retrieval_mode", "text-only")` when None) and `visual_query_fn: Any | None = None`. The existing eval-runner call `retrieve_evidence(db_path, query_text, top_k=max_k)` stays valid.
  - `_default_visual_query_fn` raises `RuntimeError("visual-fused mode requires a built sdf_page_images index + GPU query — run via the Colab notebook")` — the metric-integrity guard (no synthetic score path).
  - `_fused_evidence` obtains text-tier ranked hits as today, obtains visual ranked page keys via `visual_query_fn`, builds the `TextLookupRecord` lookup + `visual_only_ids`, fuses with `rrf_fuse` / `to_retrieval_hits` (Plan 02), and returns the SAME `RetrievalResult` the eval harness consumes. The fusion seam is lazy-imported inside the function (no new module-top heavy dep).
  - `_RETRIEVAL_TRACE_ALLOWED_KEYS` extended with `retrieval_mode` + `visual_hit_count` (numeric/identifier only). `visual_hit_count` is computed from hit source tags; image bytes / page text are never allowlisted.
- **`scripts/repair_gold_ex3_mojibake.py`** — mirrors `relabel_gold_field_rules.py`: header docstring, `PROJECT_ROOT` bootstrap, `from src.db.schema import _connect`, `--db-path` argparse. `repair_query` runs a guarded `UPDATE gold_retrieval_queries SET query_text=? WHERE query_id=? AND query_text=?` replacing U+FFFD (`�`) with Ä across the four `rq_ex3_*` ids; the vendor row (no mojibake) is a natural no-op. Prints only `query_id: rows_changed=N` and a "compliance.db never staged" reminder — no query text.
- **Tests (4 modules, 9 new tests):**
  - `tests/eval/test_gold_mojibake_repair.py` — repair applies (`ÄKTA`, no `�`), unrelated gold row byte-identical, second run = 0 rows (idempotent), vendor-style clean row is a no-op. Pure tmp_path SQLite data fix; no GPU, no fabricated metric.
  - `tests/retrieval/visual/test_mode_select.py` — default `Settings.retrieval_mode == "text-only"`; text-only returns the unchanged text-tier result on a seeded corpus; visual-fused with no backend raises the clear RuntimeError; an injected (notebook-style) ranking fuses an image-only page into hits with `source` ⊆ {visual, fused} and empty evidence for the visual-only page.
  - `tests/retrieval/visual/test_privacy_allowlist.py` — captures `safe_update_current_trace` calls for both modes, asserts captured keys ⊆ `_RETRIEVAL_TRACE_ALLOWED_KEYS` and forbidden fragments (`image_blob`, `page_text`, `snippet`, `secret`, `sk-test`, page-text body, PNG magic) absent; a hard guarantee that image/text keys were never added to the allowlist.

## Verification

- `venv\Scripts\python.exe -m pytest tests/eval/test_gold_mojibake_repair.py -x -q` → **2 passed**.
- `venv\Scripts\python.exe -m pytest tests/retrieval/visual/test_mode_select.py tests/retrieval/visual/test_privacy_allowlist.py -x -q` → **7 passed**.
- `venv\Scripts\python.exe -m pytest tests/test_retriever.py tests/test_retrieval_eval_runner.py -q` → **30 passed** (signature back-compat + text-tier behavior unchanged).
- Full offline suite: `venv\Scripts\python.exe -m pytest -q` → **370 passed, 7 skipped, 0 failed** (Wave 2 baseline was 361 passed / 7 skipped; +9 tests, no regressions).
- Acceptance greps: `retrieval_mode` present in `src/config.py` (default `"text-only"`) and `src/retrieval/retriever.py`; `def retrieve_evidence` still shows `db_path` + `question` + `top_k`; `visual-fused mode requires` present; `image_blob`/`page_text` NOT in `_RETRIEVAL_TRACE_ALLOWED_KEYS`; `UPDATE gold_retrieval_queries` + `PROJECT_ROOT = Path(__file__).resolve().parents[1]` present in the repair script; no `print(...query_text...)` leak.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Partial Settings stub broke retrieve_evidence config resolution**
- **Found during:** Task 2 (full-suite run)
- **Issue:** `tests/eval/test_eval_cli.py::test_run_with_ragas_degrades_gracefully_without_key` monkeypatches `src.config.get_settings` with a partial object exposing only `gemini_api_key`. My new `retrieve_evidence` resolved `get_settings().retrieval_mode` when `retrieval_mode is None` (the eval-runner path), raising `AttributeError` and failing the CLI run (exit code 1 instead of 0).
- **Fix:** Resolve defensively via `getattr(get_settings(), "retrieval_mode", "text-only")` so a partial stub (or an older Settings) falls back to text-only. Preserves the eval-runner call unchanged and the test's RAGAS-degradation intent.
- **Files modified:** src/retrieval/retriever.py
- **Commit:** 19eec1d

## Authentication Gates

None — the integration seam is provider-free; no API keys or logins involved. The visual-fused quality run (GPU) is the Colab notebook's job (Plan 04).

## Known Stubs

None that block the plan goal. The local `visual-fused` path deliberately has no wired GPU backend: `_default_visual_query_fn` RAISES a clear `RuntimeError` rather than returning a stub ranking — this is the metric-integrity guard mandated by 05-CONTEXT (no fabricated score). The real visual ranking + recall/ndcg numbers land in the Colab notebook (Plan 04), which supplies a real `visual_query_fn`. This is an intentional seam, not a silent stub.

## Threat Surface Scan

No new security-relevant surface beyond the plan's `<threat_model>`. All mitigations applied and tested:
- **T-05-11 (trace info disclosure):** allowlist extended with numeric/id keys only; `test_privacy_allowlist.py` asserts captured keys ⊆ allowlist and forbidden fragments absent.
- **T-05-12 (gold tamper):** guarded UPDATE; second run = 0 rows; unrelated row untouched — asserted in `test_gold_mojibake_repair.py`.
- **T-05-13 (fabricated visual results):** `_default_visual_query_fn` raises; no synthetic score path — asserted by `test_visual_fused_without_backend_raises_clear_error`.
- **T-05-14 (image-only evidence_text):** reuses Plan 02 empty-evidence behavior; the visual-only fused hit carries `evidence_text == ""` — asserted in `test_mode_select.py`.
- **T-05-15 (signature drift):** `retrieval_mode`/`visual_query_fn` are optional kwargs; existing `(db_path, query_text, top_k)` call gated green by `test_retrieval_eval_runner.py`.

## Notes for Downstream Plans

- The Colab notebook (Plan 04) supplies the real `visual_query_fn(db_path, question, *, top_k) -> Sequence[(doc_id, page_num)]` (0-indexed page keys) and runs `retrieve_evidence(..., retrieval_mode="visual-fused", visual_query_fn=...)` to produce the benchmark numbers; the eval runner can thread `retrieval_mode` from config for a text-only-vs-visual-fused side-by-side.
- The gold repair must be run once against the live `compliance.db` (`python scripts/repair_gold_ex3_mojibake.py`) before the notebook eval, so the `rq_ex3` queries carry the correct `ÄKTA` text. compliance.db is gitignored and was never staged.
- `_fused_evidence` currently sources `snippet`/`evidence_text` only from text-tier hits (image-only pages stay empty per the ou3 contract); if the notebook wants citation snippets for image-only pages, that is a future evidence-tier decision, not this seam.

## Self-Check: PASSED
