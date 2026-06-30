"""Confidence-aware weighted RRF fusion math assertions.

These assert deterministic rank-fusion MATH ONLY (metric-integrity rule): known
ranked lists -> known fused order/score. The central property under test is the
confidence rescue: a page the text tier MISSES or ranks weakly, but the visual
tier ranks highly, must surface near the top (the rq_ex5 failure that the old
text-first hard gate buried). NO fabricated embedding score is used; all inputs
are hand-authored ranked page identities.
"""
from __future__ import annotations

import pytest

from src.retrieval.visual.fusion import assert_fused_recall_not_below_text, rrf_fuse


def test_page_in_both_tiers_scores_text_plus_visual_no_rescue() -> None:
    # A page at the same rank in both tiers: visual is not MORE confident than
    # text (rank 0 == rank 0), so no rescue term is added.
    visual = [("doc_a", 0)]
    text = [("doc_a", 0)]
    fused = dict(rrf_fuse(visual, text, k=60))
    assert abs(fused[("doc_a", 0)] - (4.0 / 61 + 1.0 / 61)) < 1e-12


def test_confidence_rescue_surfaces_text_miss_above_text_hits() -> None:
    # KEY FIX: a page text MISSES entirely but the visual tier ranks #1 must beat
    # a text hit. img score = (visual 1 + rescue 3.5)/61; other = text 4/61.
    visual = [("img", 2)]
    text = [("other", 1)]
    fused_keys = [key for key, _ in rrf_fuse(visual, text, k=60)]
    assert fused_keys[0] == ("img", 2)
    assert fused_keys == [("img", 2), ("other", 1)]


def test_confidence_rescue_lifts_text_weak_strong_visual_to_top() -> None:
    # rq_ex5_vendor shape: gold ranks WEAKLY in text (rank 2) but #1 in visual.
    # The rescue fires because visual rank (0) < text rank (2), lifting it above
    # the stronger text hits.
    text = [("t0", 0), ("t1", 1), ("gold", 9)]
    visual = [("gold", 9)]
    fused_keys = [key for key, _ in rrf_fuse(visual, text, k=60)]
    assert fused_keys[0] == ("gold", 9)


def test_no_rescue_when_text_is_more_confident() -> None:
    # Page is text rank 0 but visual rank 5 -> visual is NOT more confident, so
    # the score carries text + plain visual weight only (no rescue term).
    text = [("p", 0)]
    visual = [("q", 9), ("r", 8), ("s", 7), ("u", 6), ("v", 5), ("p", 0)]
    fused = dict(rrf_fuse(visual, text, k=60))
    # p is at visual index 5 -> visual term 1/(60+6); text term 4/(60+1); no rescue.
    assert abs(fused[("p", 0)] - (4.0 / 61 + 1.0 / 66)) < 1e-12


def test_text_miss_visual_only_page_gets_rescue_term() -> None:
    visual = [("a", 0)]
    fused = dict(rrf_fuse(visual, [], k=60))
    assert abs(fused[("a", 0)] - ((1.0 + 3.5) / 61)) < 1e-12


def test_default_k_is_60() -> None:
    fused = dict(rrf_fuse([("doc_a", 0)], [("doc_a", 0)]))
    # in both tiers, same rank -> no rescue -> 4/61 + 1/61
    assert abs(fused[("doc_a", 0)] - (4.0 / 61 + 1.0 / 61)) < 1e-12


def test_ordering_is_deterministic_with_stable_tie_break() -> None:
    visual = [("doc_b", 5), ("doc_a", 9)]
    text: list = []
    first = [k for k, _ in rrf_fuse(visual, text, k=60)]
    second = [k for k, _ in rrf_fuse(visual, text, k=60)]
    assert first == second


def test_fused_recall_non_regression_guard_passes_when_recall_preserved() -> None:
    gold = {"q1": [("doc_t", 0)], "q2": [("doc_img", 2)]}
    text = {"q1": [("doc_t", 0), ("wrong", 1)], "q2": [("wrong", 2)]}
    fused = {"q1": [("doc_t", 0), ("wrong", 1)], "q2": [("doc_img", 2), ("wrong", 2)]}
    assert_fused_recall_not_below_text(gold, text, fused, k_values=(1, 2))


def test_fused_recall_non_regression_guard_fails_on_demoted_text_hit() -> None:
    gold = {"q1": [("doc_t", 0)]}
    text = {"q1": [("doc_t", 0)]}
    fused = {"q1": [("bad_visual", 9), ("doc_t", 0)]}
    with pytest.raises(AssertionError, match="below text-only"):
        assert_fused_recall_not_below_text(gold, text, fused, k_values=(1,))
