"""Public answer DTOs for grounded RAG responses.

The answer boundary owns citations and diagnostics. DTOs intentionally expose only
bounded retrieval snippets plus compact status metadata; raw page text, image
blobs, provider raw responses, API keys, and full corpus hashes must stay behind
retrieval/provider internals.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AnswerStatus(StrEnum):
    """High-level answer outcome visible to callers and dashboards."""

    ANSWERED = "answered"
    ABSTAINED = "abstained"
    PROVIDER_ERROR = "provider_error"


class AnswerReasonCode(StrEnum):
    """Reason-coded answer outcomes for safe failure visibility."""

    ANSWERED = "answered"
    EMPTY_QUESTION = "empty_question"
    INDEX_MISSING = "index_missing"
    INDEX_EMPTY = "index_empty"
    INDEX_STALE = "index_stale"
    NO_MATCH = "no_match"
    BELOW_THRESHOLD = "below_threshold"
    RETRIEVAL_ERROR = "retrieval_error"
    PROVIDER_EXCEPTION = "provider_exception"
    PROVIDER_BLANK_ANSWER = "provider_blank_answer"
    PROVIDER_MALFORMED_RESULT = "provider_malformed_result"
    PROVIDER_CONFIGURATION_ERROR = "provider_configuration_error"


@dataclass(frozen=True)
class AnswerCitation:
    """Service-owned citation derived exclusively from retrieval hits.

    ``snippet`` is the dashboard-rendered teaser. ``evidence_text`` is the wider
    bounded grounding text consumed in memory by the generator and the RAGAS
    judge; it is intentionally NOT rendered by the dashboard and never persisted.
    """

    doc_id: str
    filename: str
    page_num: int
    display_page_num: int
    snippet: str
    score: float
    evidence_text: str = ""


@dataclass(frozen=True)
class AnswerDiagnostics:
    """Bounded answer diagnostics safe for logs, UIs, and future agents."""

    status: AnswerStatus
    reason_code: AnswerReasonCode
    run_id: str | None
    provider_name: str | None
    trace_id: str | None
    top_score: float
    citation_count: int
    evidence_reason: str
    error_class: str | None = None


@dataclass(frozen=True)
class AnswerResult:
    """Grounded answer or safe abstention/provider-error result."""

    status: AnswerStatus
    answer_text: str
    citations: tuple[AnswerCitation, ...]
    diagnostics: AnswerDiagnostics

    @property
    def is_answered(self) -> bool:
        """Return True only when a cited answer was produced."""

        return self.status is AnswerStatus.ANSWERED


__all__ = [
    "AnswerCitation",
    "AnswerDiagnostics",
    "AnswerReasonCode",
    "AnswerResult",
    "AnswerStatus",
]
