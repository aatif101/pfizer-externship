"""Gated weighted RRF fusion math assertions.

These assert deterministic rank-fusion MATH ONLY (metric-integrity rule): known
ranked lists -> known fused order, text-first preservation, image-only empty-page
boosting, and the recall non-regression guard. NO fabricated embedding score is
used; all inputs are hand-authored ranked page identities.
"""
from __future__ import annotations

import pytest

from src.retrieval.visual.fusion import assert_fused_recall_not_below_text, rrf_fuse


def test_weighted_rrf_scores_page_in_both_tiers_highest_but_preserves_text_order() -> None:
    visual = [("doc_a", 0), ("doc_b", 1), ("doc_c", 2)]
    text = [("doc_d", 3), ("doc_a", 0), ("doc_b", 1)]
    fused = rrf_fuse(visual, text, k=60)
    fused_keys = [key for key, _score in fused]

    assert fused_keys[:3] == text
    # doc_a score = visual rank 0 (1/61) + text rank 1 weighted (4/62)
    assert abs(dict(fused)[("doc_a", 0)] - (1.0 / 61 + 4.0 / 62)) < 1e-12


def test_visual_only_pages_append_after_text_hits() -> None:
    visual = [("doc_a", 0), ("doc_b", 1)]
    text = [("doc_b", 1), ("doc_c", 2)]
    fused = rrf_fuse(visual, text, k=60)
    fused_keys = [key for key, _score in fused]
    assert fused_keys == [("doc_b", 1), ("doc_c", 2), ("doc_a", 0)]


def test_empty_text_visual_only_page_is_prioritized_among_visual_additions() -> None:
    # Example-3 proof: image-only page (5543408c4dacc48b, 2) is ONLY in the
    # visual tier (text retrieval scored 0 on it) yet must appear in fused output.
    visual = [("doc_x", 0), ("5543408c4dacc48b", 2)]
    text = [("doc_y", 1)]
    page_text_lengths = {("doc_x", 0): 120, ("5543408c4dacc48b", 2): 0}
    fused = rrf_fuse(visual, text, k=60, page_text_lengths=page_text_lengths)
    fused_keys = [key for key, _score in fused]
    assert fused_keys == [("doc_y", 1), ("5543408c4dacc48b", 2), ("doc_x", 0)]


def test_visual_only_stable_tie_break_is_deterministic() -> None:
    visual = [("doc_b", 5), ("doc_a", 9)]
    text = []
    fused = rrf_fuse(visual, text, k=60)
    fused_keys = [key for key, _score in fused]
    assert [k for k, _ in rrf_fuse(visual, text, k=60)] == fused_keys


def test_weighted_rrf_default_k_is_60() -> None:
    visual = [("doc_a", 0)]
    fused = rrf_fuse(visual, [])
    assert abs(dict(fused)[("doc_a", 0)] - (1.0 / 61)) < 1e-12


def test_fused_recall_non_regression_guard_passes_when_text_order_is_preserved() -> None:
    gold = {"q1": [("doc_t", 0)], "q2": [("doc_img", 2)]}
    text = {"q1": [("doc_t", 0), ("wrong", 1)], "q2": [("wrong", 2)]}
    visual = {"q1": [("bad_visual", 9)], "q2": [("doc_img", 2)]}
    fused = {
        qid: [page_key for page_key, _score in rrf_fuse(visual[qid], text[qid])]
        for qid in gold
    }

    assert_fused_recall_not_below_text(gold, text, fused, k_values=(1, 2))


def test_fused_recall_non_regression_guard_fails_on_demoted_text_hit() -> None:
    gold = {"q1": [("doc_t", 0)]}
    text = {"q1": [("doc_t", 0)]}
    fused = {"q1": [("bad_visual", 9), ("doc_t", 0)]}

    with pytest.raises(AssertionError, match="below text-only"):
        assert_fused_recall_not_below_text(gold, text, fused, k_values=(1,))
