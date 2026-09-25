"""Pure conditional-edge routers for the agentic RAG graph.

No I/O and no langgraph import: each router reads state and returns the name
of the next node. Loop bounds are enforced here from state counters.
"""
from __future__ import annotations

from typing import Any, Mapping

from src.rag.agentic.state import MAX_REGENERATIONS, MAX_RETRIEVAL_ROUNDS


def route_after_evaluate(state: Mapping[str, Any]) -> str:
    """Draft when every sub-query is strong; otherwise rewrite until rounds run out."""

    if state.get("error_class"):
        return "abstain"
    per_query_strong = state.get("per_query_strong") or {}
    if per_query_strong and all(per_query_strong.values()):
        return "draft"
    if int(state.get("retrieval_round", 0)) < MAX_RETRIEVAL_ROUNDS:
        return "rewrite"
    return "abstain"


def route_after_rewrite(state: Mapping[str, Any]) -> str:
    """Retrieve again unless the rewriter produced no new query text."""

    if state.get("rewrite_exhausted"):
        return "abstain"
    return "retrieve"


def route_after_critique(state: Mapping[str, Any]) -> str:
    """Finalize only accepted drafts; regenerate at most once; otherwise abstain."""

    if state.get("error_class") or state.get("outcome") == "provider_error":
        return "abstain"
    if state.get("critic_accepted"):
        return "finalize"
    if int(state.get("regeneration_count", 0)) < MAX_REGENERATIONS:
        return "draft"
    return "abstain"


__all__ = ["route_after_critique", "route_after_evaluate", "route_after_rewrite"]
