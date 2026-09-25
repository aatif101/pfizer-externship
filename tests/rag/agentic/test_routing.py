"""Pure router tests for the agentic graph (no langgraph, no I/O)."""
from __future__ import annotations

from src.rag.agentic.routing import route_after_critique, route_after_evaluate, route_after_rewrite
from src.rag.agentic.state import MAX_REGENERATIONS, MAX_RETRIEVAL_ROUNDS


def test_bounds_constants() -> None:
    assert MAX_RETRIEVAL_ROUNDS == 3
    assert MAX_REGENERATIONS == 1


def test_evaluate_all_strong_drafts() -> None:
    assert route_after_evaluate({"per_query_strong": {"a": True, "b": True}, "retrieval_round": 1}) == "draft"


def test_evaluate_all_strong_on_last_round_still_drafts() -> None:
    assert route_after_evaluate({"per_query_strong": {"a": True}, "retrieval_round": 3}) == "draft"


def test_evaluate_weak_round_1_rewrites() -> None:
    assert route_after_evaluate({"per_query_strong": {"a": False}, "retrieval_round": 1}) == "rewrite"


def test_evaluate_weak_round_2_rewrites() -> None:
    assert route_after_evaluate({"per_query_strong": {"a": True, "b": False}, "retrieval_round": 2}) == "rewrite"


def test_evaluate_weak_round_3_abstains() -> None:
    assert route_after_evaluate({"per_query_strong": {"a": False}, "retrieval_round": 3}) == "abstain"


def test_evaluate_error_class_abstains() -> None:
    state = {"per_query_strong": {"a": True}, "retrieval_round": 1, "error_class": "OperationalError"}
    assert route_after_evaluate(state) == "abstain"


def test_evaluate_empty_per_query_strong_at_round_3_abstains() -> None:
    assert route_after_evaluate({"per_query_strong": {}, "retrieval_round": 3}) == "abstain"


def test_rewrite_exhausted_abstains() -> None:
    assert route_after_rewrite({"rewrite_exhausted": True}) == "abstain"


def test_rewrite_fresh_query_retrieves() -> None:
    assert route_after_rewrite({"rewrite_exhausted": False}) == "retrieve"


def test_critique_error_class_abstains() -> None:
    assert route_after_critique({"error_class": "CriticProviderError", "critic_accepted": True}) == "abstain"


def test_critique_provider_error_abstains() -> None:
    assert route_after_critique({"outcome": "provider_error"}) == "abstain"


def test_critique_accepted_finalizes() -> None:
    assert route_after_critique({"critic_accepted": True, "regeneration_count": 0}) == "finalize"


def test_critique_rejected_first_time_redrafts() -> None:
    assert route_after_critique({"critic_accepted": False, "regeneration_count": 0}) == "draft"


def test_critique_rejected_after_regeneration_abstains() -> None:
    assert route_after_critique({"critic_accepted": False, "regeneration_count": 1}) == "abstain"
