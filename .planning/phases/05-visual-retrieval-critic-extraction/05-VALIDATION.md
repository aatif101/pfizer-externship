---
phase: 5
slug: visual-retrieval-critic-extraction
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-23
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Scope: VISUAL RETRIEVAL TIER ONLY (VISUAL-01, VISUAL-02). Critic extraction (EXTRACT-03/04) deferred.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing suite, ~332 tests) |
| **Config file** | pyproject.toml |
| **Quick run command** | `venv\Scripts\python.exe -m pytest <new test files> -x -q` |
| **Full suite command** | `venv\Scripts\python.exe -m pytest -q` |
| **Estimated runtime** | ~3.5 min full suite |

**Windows hard rule:** verification via `venv\Scripts\python.exe -m pytest` ONLY — never bash / `/bin/bash`. `compliance.db` and `.env` never staged.

---

## Sampling Rate

- **After every task commit:** Run the quick command on the touched test files.
- **After every plan wave:** Run the full suite.
- **Before `/gsd-verify-work`:** Full offline suite must be green.
- **Max feedback latency:** ~210 s (full suite).

---

## Per-Task Verification Map

*Populated during planning (one row per task). Every offline task carries an `<automated>` pytest command; GPU-bound steps map to the Manual-Only Colab verification below — see the no-fabrication boundary.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Test Type | Automated Command | Status |
|---------|------|------|-------------|------------|-----------|-------------------|--------|
| TBD | — | — | VISUAL-01 / VISUAL-02 | T-05-xx | unit | `venv\Scripts\python.exe -m pytest ...` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New test modules for the offline-testable plumbing (image decode/preprocess from `image_blob`, Qdrant collection config + named-vector spec, two-stage prefetch query payload construction, RRF k=60 fusion math, visual→`RetrievalHit` mapping with 0-indexed `page_num`, gold mojibake fix).
- [ ] Shared fixtures for synthetic multivector shapes (shape/plumbing assertions ONLY — never a fake embedding standing in for the model to fabricate a quality score).

*Heavy deps (colpali-engine, torch-CUDA, qdrant model inference) are GPU/Colab-only and guarded out of the offline suite via a lazy-import seam.*

---

## Manual-Only Verifications

> **This is the no-fabrication boundary.** Retrieval-quality numbers come ONLY from a real ColQwen2.5 run on a real GPU — never from a mock or synthetic score in CI.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ColQwen2.5 page-image embedding + Qdrant index build | VISUAL-01 | Needs a ≥16 GB GPU (L4); 3B model in bf16. Local 8 GB RTX 5070 (Blackwell sm_120) is incompatible with the pinned indexing stack. | Run the committed Colab L4 notebook end-to-end: install pinned stack, load `vidore/colqwen2.5-v0.2`, embed each page from `pages.image_blob`, build the `sdf_page_images` Qdrant collection (3 named vectors). |
| Two-stage visual retrieval quality (recall@5/@10, ndcg@5, citation accuracy) + Example-3 image-only pages retrievable | VISUAL-02 | Quality metrics require real embeddings + MaxSim rerank on a GPU. | In the Colab notebook, run the retrieval eval (text-only vs visual-fused) on the gold set; print the metrics table; confirm the four `rq_ex3_*` gold pages appear in visual top-k. Numbers are the reproducible artifact — anyone with Colab Pro L4 + `compliance.db` re-runs and reproduces them. |

---

## Validation Sign-Off

- [ ] All offline tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive offline tasks without automated verify
- [ ] Wave 0 covers all offline-testable plumbing
- [ ] No watch-mode flags
- [ ] GPU-only quality numbers correctly mapped to Manual-Only Colab verification (no mock substitutes)
- [ ] `nyquist_compliant: true` set in frontmatter (by planner/auditor)

**Approval:** pending
