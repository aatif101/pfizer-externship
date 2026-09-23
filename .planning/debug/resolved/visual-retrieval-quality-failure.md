---
status: resolved
trigger: "ColQwen2.5 visual-fused retrieval underperformed text-only on the 2026-06-28 Colab L4 run; rq_ex3 image-only Certificate of Quality queries missed at top-5 for text, visual, and fused retrieval."
created: "2026-06-28"
updated: "2026-09-23"
---

# Visual Retrieval Quality Failure

## Symptoms

- Expected behavior: image-only scanned supplier pages should become retrievable through the ColQwen2.5/Qdrant visual tier, and visual-fused retrieval should improve over text-only on image-only queries.
- Actual behavior: visual-fused retrieval regressed aggregate recall/citation metrics versus text-only, and all rq_ex3 queries missed the correct image-only Certificate of Quality page at top-5.
- Error messages: none; the pipeline ran cleanly on Colab L4.
- Timeline: negative result observed in the 2026-06-28 real Colab L4 run.
- Reproduction: run `notebooks/visual_retrieval_colab.ipynb` against the Phase 5 corpus/eval set and compare text-only, visual-only, and fused retrieval metrics.

## Current Focus

- hypothesis: version drift, query/image preprocessing mismatch, pooling/prefetch assumptions, or fusion/eval design may be suppressing the visual signal despite clean execution.
- test: read Phase 5 docs and implementation, compare each stage against ColPali/Qdrant best practices and current upstream behavior, then write a diagnosis report with ranked recommendations.
- expecting: one or more high-confidence root causes or design ceilings, with falsifiable experiments where GPU verification is required.
- next_action: none — resolved by 05-05 (see Resolution)

## Outcome

Diagnosis written to `.planning/phases/05-visual-retrieval-critic-extraction/05-05-DIAGNOSIS.md`.

Primary conclusion: the failure is real, the Qdrant/ColPali architecture is mostly canonical, and the highest-probability root cause is the `colpali-engine==0.3.17` / Transformers 5.x model-loading path. Upstream `colpali-engine` main contains an unreleased ColQwen2/ColQwen2.5 checkpoint conversion fix for `model.embed_tokens` and `model.norm`; the 0.3.17 wheel used in the Colab run does not. A separate but important design issue is equal-weight RRF, which allowed weak visual ranks to demote correct text-only hits.

## Resolution

- root_cause: ColQwen2.5 was silently mis-loaded under colpali-engine 0.3.17 + Transformers 5.x (the backbone prefix model.* was renamed to language_model.*, so embed_tokens/norm and the whole LoRA adapter were MISSING and randomly reinitialized). Contributing factors: 6 empty-text scanned pages made the text tier blind, and text-first fusion buried visual rank-1 hits.
- fix: pinned the pre-Transformers-5 stack (colpali-engine==0.3.9, transformers>=4.50,<4.51, torch==2.6.0, peft>=0.14,<0.15) plus a load-report gate (72b437c); patch grid derived from image_grid_thw (86db1d2); OCR backfill into page_ocr_texts (bb97f31); confidence-aware weighted RRF rescue, rescue_weight=3.5 (3ecfa88). Notebook ABI pins in ee976b1 and f7ab6c8.
- verification: Colab L4 load report clean (0 missing/unexpected/mismatched keys). Text-only recall@5 0.882 / recall@10 0.941. Visual-fused recall@5 1.000 (17/17) / recall@10 1.000 (17/17); per 05-05-SUMMARY the fused 17/17 was proven offline on the same real data from the Colab run. All four rq_ex3 queries at visual rank 1. pytest 394 passed, 8 skipped. Details in `.planning/phases/05-visual-retrieval-critic-extraction/05-05-SUMMARY.md` (close-out f04f14d).
- files_changed: [notebooks/visual_retrieval_colab.ipynb, scripts/backfill_ocr_text.py, src/db/schema.py, src/eval/repository.py, src/retrieval/indexer.py, src/retrieval/models.py, src/retrieval/ocr_backfill.py, src/retrieval/repository.py, src/retrieval/retriever.py, src/retrieval/visual/embedder.py, src/retrieval/visual/fusion.py, tests/retrieval/visual/test_embedder_offline.py, tests/retrieval/visual/test_fusion.py, tests/retrieval/visual/test_notebook_structure.py, tests/test_ocr_backfill.py]
