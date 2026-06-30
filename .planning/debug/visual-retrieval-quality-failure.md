---
status: diagnosed
trigger: "ColQwen2.5 visual-fused retrieval underperformed text-only on the 2026-06-28 Colab L4 run; rq_ex3 image-only Certificate of Quality queries missed at top-5 for text, visual, and fused retrieval."
created: "2026-06-28"
updated: "2026-06-28"
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
- next_action: read `.planning/phases/05-visual-retrieval-critic-extraction/05-05-DIAGNOSIS.md` and run the loading-audit / compatibility-matrix experiments before changing pooling or fusion code.

## Outcome

Diagnosis written to `.planning/phases/05-visual-retrieval-critic-extraction/05-05-DIAGNOSIS.md`.

Primary conclusion: the failure is real, the Qdrant/ColPali architecture is mostly canonical, and the highest-probability root cause is the `colpali-engine==0.3.17` / Transformers 5.x model-loading path. Upstream `colpali-engine` main contains an unreleased ColQwen2/ColQwen2.5 checkpoint conversion fix for `model.embed_tokens` and `model.norm`; the 0.3.17 wheel used in the Colab run does not. A separate but important design issue is equal-weight RRF, which allowed weak visual ranks to demote correct text-only hits.
