"""State, bounds, and dependencies for the agentic RAG graph.

Pure data only: no langgraph import, no I/O. Loop bounds live here as
module constants so routing and tests share a single source of truth.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, Callable

from typing_extensions import TypedDict

from src.rag.critic import CriticProvider
from src.rag.providers import AnswerProvider
from src.retrieval.models import EvidenceGateResult

MAX_RETRIEVAL_ROUNDS = 3  # 1 initial retrieval + 2 retries
MAX_REGENERATIONS = 1  # at most one critic-driven redraft
GRAPH_RECURSION_LIMIT = 30  # backstop on super-steps; worst legal path is ~14
MAX_SUB_QUERIES = 3
DEFAULT_CRITIC_MIN_FAITHFULNESS = 0.8


class AgenticState(TypedDict, total=False):
    """Graph state. Every node returns a partial dict of these keys."""

    question: str
    sub_queries: list[str]
    # original sub-query -> current query text, only for sub-queries not yet strong
    active_queries: dict[str, str]
    tried_queries: list[str]
    # original sub-query -> hits from its strong round
    strong_hits: dict[str, tuple]
    per_query_strong: dict[str, bool]
    retrieval_round: int
    rewrite_exhausted: bool
    evidence: tuple  # merged, deduplicated RetrievalHit tuple (bounded top_k)
    run_id: str | None
    top_score: float
    evidence_reason: str
    draft: str | None
    provider_name: str | None
    trace_id: str | None  # provider trace id of the latest draft
    citations: tuple  # AnswerCitation tuple built by finalize from retrieval hits only
    critic_feedback: str | None  # in-memory only; never traced or persisted
    critic_verdict: str | None
    critic_score: float | None
    critic_accepted: bool
    regeneration_count: int
    outcome: str
    reason_code: str
    error_class: str | None
    steps: Annotated[list[str], operator.add]


@dataclass(frozen=True)
class AgenticDeps:
    """Injected collaborators for one graph invocation."""

    db_path: str
    answer_provider: AnswerProvider | None
    critic: CriticProvider | None
    retrieve_fn: Callable[..., EvidenceGateResult] | None = None  # None -> retrieve_evidence
    decomposer: Callable[[str], str] | None = None  # raw-text LLM fn (wired in 06-04, consumed in 06-05)
    rewriter: Callable[[str], str] | None = None  # raw-text LLM fn
    top_k: int = 5
    critic_min_faithfulness: float = DEFAULT_CRITIC_MIN_FAITHFULNESS
    critic_error_class: str | None = None  # set by 06-04 when critic resolution failed


__all__ = [
    "DEFAULT_CRITIC_MIN_FAITHFULNESS",
    "GRAPH_RECURSION_LIMIT",
    "MAX_REGENERATIONS",
    "MAX_RETRIEVAL_ROUNDS",
    "MAX_SUB_QUERIES",
    "AgenticDeps",
    "AgenticState",
]
