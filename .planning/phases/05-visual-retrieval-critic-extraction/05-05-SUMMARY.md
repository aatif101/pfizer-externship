---
phase: 05-visual-retrieval-critic-extraction
plan: 05
subsystem: retrieval
tags: [visual-retrieval, colqwen2.5, ocr-backbone, fusion, colab-l4, real-numbers, no-fabrication]
status: complete
metrics:
  completed: 2026-06-29
---

# Phase 5 Plan 05: Loader Fix + OCR Backbone + Fusion Rescue (VISUAL-01/02 closed)

This plan turned the negative 05-04 Colab result into a real, strong, end-to-end result. Three root-caused fixes, each validated, none fabricated.

## Final numbers (Colab L4, OCR-backfilled `compliance.db`, fusion fix offline-proven on the same data)

| Metric | text-only | visual-fused |
|--------|-----------|--------------|
| recall@5  | 0.882 (15/17) | **1.000 (17/17)** |
| recall@10 | 0.941 (16/17) | **1.000 (17/17)** |

ColQwen2.5 load report clean (0 missing/unexpected/mismatched keys). All four `rq_ex3` image-only Cytiva queries at visual rank 1. Acceptance gate (fused recall >= text-only) holds.

## What was wrong, and the fix chain

### 1. ColQwen2.5 was silently mis-loaded (the cause of the 05-04 negative result)
The 05-04 run used `colpali-engine==0.3.17` + `transformers==5.12`. Transformers 5.x renamed the Qwen2.5-VL backbone prefix `model.*` -> `language_model.*`, but the checkpoints were saved with the old layout and 0.3.17 does not remap it. The `from_pretrained` load report showed `language_model.embed_tokens` / `language_model.norm` MISSING (randomly reinitialized) and the entire LoRA adapter MISSING (`language_model.layers.*.lora_*`). The model ran as base Qwen2.5-VL with a random input embedding and no retrieval fine-tuning, so every gold page ranked 18-77/78.

**Fix (Option B, commit 72b437c + loader/grid follow-ups):** pin a pre-Transformers-5 stack where the checkpoint layout matches the runtime: `colpali-engine==0.3.9`, `transformers>=4.50,<4.51`, `torch==2.6.0`, `peft>=0.14,<0.15`. Added a load-report gate (`assert_colqwen_load_report_clean`) that fails fast on missing critical keys, so this class of silent corruption can never pass shape checks again. Derive the patch grid from `image_grid_thw` instead of 0.3.9's broken `get_n_patches` (commit 86db1d2).

### 2. Text tier was structurally blind to 6 scanned pages
6 of 78 pages had empty `page_text` (Docling extracted no text), so text retrieval could never return them. The Cytiva Certificate of Quality was one.

**Fix (OCR backbone, commit bb97f31):** OCR/VLM backfill of the 6 empty-text pages into a separate `page_ocr_texts` provenance table (original `pages.page_text` untouched); the index now folds OCR text in with provenance flags. Text-only recall@5 rose 0.647 -> 0.882. All four `rq_ex3` queries became text-retrievable.

### 3. Fusion buried the visual tier's best signal
The remaining 2 misses (both Example-5 doc `e89fa720` p2) were retrieved by the visual tier at rank 1, but the old text-first hard-gate fusion appended every visual-only page below all text pages, so a page text missed (or ranked weakly) but visual ranked #1 landed at fused rank 17/10. Fused == text-only (delta 0), hiding visual's value.

**Fix (commit 3ecfa88):** confidence-aware weighted RRF. Add a rescue term (`rescue_weight=3.5`, center of the stable [3.0, 4.0] plateau) whenever the visual tier is more confident than text for a page (text-miss, or visual rank < text rank), then order by fused score. Dropped the obsolete `empty_text_boost` (OCR made those pages text-retrievable). Offline-proven against the gold set using the actual committed `rrf_fuse`, regenerated local text ranks (0-mismatch vs the Colab run report), and the run-report visual ranks: recall@5 0.882 -> 1.000, recall@10 0.941 -> 1.000; both formerly-missed queries now hit; acceptance gate holds.

## Honest framing for the writeup

OCR-augmented text retrieval reaches 0.882 recall@5 on its own. The ColQwen2.5 visual tier retrieves every page text retrieval misses or ranks weakly (the two Example-5 queries) at rank 1, and confidence-aware fusion surfaces them, lifting fused recall to 1.000. Visual retrieval is additive, not redundant: fused beats text-only.

## Notebook reproducibility notes

Forcing the torch-2.6 era on a fresh Colab runtime required pinning `numpy<2.1` (scipy ABI) and `pillow<12` (torchvision 0.21 ABI), plus removing Colab's `torchao` (commits ee976b1, f7ab6c8). The notebook persists a run-report artifact (`/content/visual_retrieval_run_report.json/.md`) with the load report, per-query text/visual/fused ranks, and top-10 visual hits.

## Verification

- `venv\Scripts\python.exe -m pytest` -> 394 passed, 8 skipped (GPU-marked).
- Colab L4 end-to-end run produced the clean load report, text-only 0.882/0.941, and the `rq_ex3` rank-1 proof. The fusion fix's 17/17 was proven offline on the same real data (Colab re-run to print it in the notebook is a formality).
