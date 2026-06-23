"""RRF (k=60) fusion math assertions (Task 2).

These assert deterministic rank-fusion MATH ONLY (metric-integrity rule): known
ranked lists → the known fused order, the cross-tier score sum, stable tie-break,
and the Example-3 proof shape (an image-only visual page survives fusion). NO
fabricated recall/ndcg/citation number is asserted off a synthetic embedding.
"""
from __future__ import annotations

from src.retrieval.visual.fusion import rrf_fuse


def test_rrf_page_in_both_tiers_outranks_single_tier_page() -> None:
    # (doc_a, 0) appears rank 0 in BOTH tiers -> highest fused score.
    visual = [("doc_a", 0), ("doc_b", 1), ("doc_c", 2)]
    text = [("doc_a", 0), ("doc_d", 3), ("doc_b", 1)]
    fused = rrf_fuse(visual, text, k=60)
    fused_keys = [key for key, _score in fused]

    assert fused_keys[0] == ("doc_a", 0)  # both tiers rank 0 -> top
    # (doc_a,0) score = 1/61 + 1/61
    top_score = dict(fused)[("doc_a", 0)]
    assert abs(top_score - (1.0 / 61 + 1.0 / 61)) < 1e-12
    # (doc_b,1): visual rank 1 (1/62) + text rank 2 (1/63)
    assert abs(dict(fused)[("doc_b", 1)] - (1.0 / 62 + 1.0 / 63)) < 1e-12


def test_rrf_known_fused_order() -> None:
    visual = [("doc_a", 0), ("doc_b", 1)]
    text = [("doc_b", 1), ("doc_c", 2)]
    fused = rrf_fuse(visual, text, k=60)
    # doc_b: 1/62 (visual rank1) + 1/61 (text rank0) = 0.032..  highest
    # doc_a: 1/61 = 0.0163..
    # doc_c: 1/62 = 0.0161..
    fused_keys = [key for key, _score in fused]
    assert fused_keys == [("doc_b", 1), ("doc_a", 0), ("doc_c", 2)]


def test_rrf_image_only_visual_page_survives_fusion() -> None:
    # Example-3 proof: image-only page (5543408c4dacc48b, 2) is ONLY in the
    # visual tier (text retrieval scored 0 on it) yet must appear in fused output.
    visual = [("5543408c4dacc48b", 2), ("doc_x", 0)]
    text = [("doc_y", 1)]
    fused = rrf_fuse(visual, text, k=60)
    fused_keys = [key for key, _score in fused]
    assert ("5543408c4dacc48b", 2) in fused_keys


def test_rrf_stable_tie_break_is_deterministic() -> None:
    # Two pages tie on score (each rank 0 in exactly one tier) -> deterministic
    # tie-break on (doc_id, page_num) ascending.
    visual = [("doc_b", 5)]
    text = [("doc_a", 9)]
    fused = rrf_fuse(visual, text, k=60)
    assert dict(fused)[("doc_b", 5)] == dict(fused)[("doc_a", 9)]  # equal score
    fused_keys = [key for key, _score in fused]
    assert fused_keys == [("doc_a", 9), ("doc_b", 5)]  # tie broken on key asc
    # Re-running yields the identical order.
    assert [k for k, _ in rrf_fuse(visual, text, k=60)] == fused_keys


def test_rrf_default_k_is_60() -> None:
    visual = [("doc_a", 0)]
    fused = rrf_fuse(visual, [])
    assert abs(dict(fused)[("doc_a", 0)] - (1.0 / 61)) < 1e-12
