from __future__ import annotations

from src.eval.retrieval_metrics import (
    compute_page_level_citation_accuracy,
    compute_retrieval_recall_at_k,
)


def test_recall_at_k_perfect_recall_deduped_hits() -> None:
    gold = {"q1": [("docA", 1), ("docA", 2)]}
    # Include a duplicate hit in the top-k; should still count once.
    retrieved = {"q1": [("docA", 1, 0.9), ("docA", 1, 0.8), ("docA", 2, 0.7)]}

    res = compute_retrieval_recall_at_k(gold, retrieved, k=3)

    assert res.k == 3
    assert res.per_query_recall["q1"] == 1.0
    assert res.macro_recall == 1.0


def test_recall_at_k_partial_recall() -> None:
    gold = {"q1": [("docA", 1), ("docA", 2)]}
    retrieved = {"q1": [("docA", 1, 0.9), ("docB", 7, 0.5)]}

    res = compute_retrieval_recall_at_k(gold, retrieved, k=2)

    assert res.per_query_recall["q1"] == 0.5
    assert res.macro_recall == 0.5


def test_recall_at_k_missing_retrieved_hits_is_zero() -> None:
    gold = {"q1": [("docA", 1), ("docA", 2)]}
    retrieved: dict[str, list[tuple[str, int, float]]] = {}

    res = compute_retrieval_recall_at_k(gold, retrieved, k=5)

    assert res.per_query_recall["q1"] == 0.0
    assert res.macro_recall == 0.0


def test_recall_at_k_empty_gold_is_zero_and_nonfatal() -> None:
    gold = {"q1": []}
    retrieved = {"q1": [("docA", 1, 0.9)]}

    res = compute_retrieval_recall_at_k(gold, retrieved, k=5)

    assert res.per_query_recall["q1"] == 0.0
    assert res.macro_recall == 0.0


def test_recall_at_k_ignores_hits_after_k() -> None:
    gold = {"q1": [("docA", 1), ("docA", 2)]}
    retrieved = {"q1": [("docX", 99, 0.9), ("docA", 1, 0.8), ("docA", 2, 0.7)]}

    res = compute_retrieval_recall_at_k(gold, retrieved, k=2)

    assert res.per_query_recall["q1"] == 0.5


def test_citation_accuracy_match_and_no_match() -> None:
    gold = {
        "q1": [("docA", 1)],
        "q2": [("docB", 7)],
    }
    cited = {
        "q1": [("docA", 1), ("docZ", 3)],
        "q2": [("docB", 8)],
    }

    res = compute_page_level_citation_accuracy(gold, cited)

    assert res["per_query_accuracy"]["q1"] == 1.0
    assert res["per_query_accuracy"]["q2"] == 0.0
    assert res["macro_accuracy"] == 0.5


def test_citation_accuracy_empty_gold_and_missing_citations_are_zero() -> None:
    gold = {"q1": [], "q2": [("docB", 7)]}
    cited = {"q2": []}

    res = compute_page_level_citation_accuracy(gold, cited)

    assert res["per_query_accuracy"]["q1"] == 0.0
    assert res["per_query_accuracy"]["q2"] == 0.0
    assert res["macro_accuracy"] == 0.0
