"""Offline fakes for the agentic RAG graph tests.

Everything here is in-memory: no SQLite index, no network, no LLM SDK. Fakes
record their calls so tests can assert routing, loop bounds, and contract
shape. Scripted scores are routing inputs only and are never reported as
metrics (Phase 5 metric-integrity rule).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.rag.critic import CriticRequest, CriticVerdict
from src.rag.providers import AnswerProviderRequest, AnswerProviderResult
from src.retrieval.models import (
    EvidenceGateResult,
    RetrievalEvidenceReason,
    RetrievalHit,
    RetrievalScoreComponents,
)


def make_hit(doc_id: str, page_num: int, score: float, snippet: str = "...") -> RetrievalHit:
    """Build a citation-ready retrieval hit with default score components."""

    return RetrievalHit(
        doc_id=doc_id,
        filename=f"{doc_id}.pdf",
        page_num=page_num,
        display_page_num=page_num + 1,
        score=score,
        score_components=RetrievalScoreComponents(),
        snippet=snippet,
        evidence_text=snippet,
    )


def strong_result(
    hits: tuple[RetrievalHit, ...] | None = None,
    *,
    run_id: str | None = "run-fake-001",
) -> EvidenceGateResult:
    """Scripted strong gate result (is_strong=True, STRONG_EVIDENCE)."""

    resolved = hits if hits is not None else (make_hit("doc-a", 0, 0.9, "Expiry Date: 2027-01-31"),)
    return EvidenceGateResult(
        is_strong=True,
        reason_code=RetrievalEvidenceReason.STRONG_EVIDENCE,
        hits=resolved,
        top_score=max((hit.score for hit in resolved), default=0.0),
        query_terms=("expiry",),
        run_id=run_id,
    )


def weak_result(*, run_id: str | None = "run-fake-001", top_score: float = 0.1) -> EvidenceGateResult:
    """Scripted weak gate result (is_strong=False, BELOW_THRESHOLD)."""

    return EvidenceGateResult(
        is_strong=False,
        reason_code=RetrievalEvidenceReason.BELOW_THRESHOLD,
        hits=(),
        top_score=top_score,
        query_terms=("expiry",),
        run_id=run_id,
    )


@dataclass
class FakeRetrieve:
    """Callable retrieve_fn fake returning scripted gate results in order.

    When the script runs out, the last result repeats.
    """

    results: list[EvidenceGateResult | BaseException] = field(default_factory=list)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def __call__(self, db_path: str, question: str, **kwargs: Any) -> EvidenceGateResult:
        self.calls.append((question, dict(kwargs)))
        if not self.results:
            raise AssertionError("FakeRetrieve has no scripted results")
        index = min(len(self.calls) - 1, len(self.results) - 1)
        item = self.results[index]
        if isinstance(item, BaseException):
            raise item
        return item


@dataclass
class FakeAnswerProvider:
    """Scripted answer provider; repeats the last answer when exhausted."""

    answers: list[str] = field(default_factory=lambda: ["Answer text"])
    provider_name: str = "fake"
    trace_id: str | None = "trace-fake-001"
    calls: list[AnswerProviderRequest] = field(default_factory=list)
    exception: BaseException | None = None
    malformed_result: Any | None = None

    def answer(self, request: AnswerProviderRequest) -> AnswerProviderResult:
        self.calls.append(request)
        if self.exception is not None:
            raise self.exception
        if self.malformed_result is not None:
            return self.malformed_result  # type: ignore[return-value]
        index = min(len(self.calls) - 1, len(self.answers) - 1)
        return AnswerProviderResult(
            answer_text=self.answers[index],
            trace_id=self.trace_id,
            provider_name=self.provider_name,
        )


def verdict(value: str = "supported", faithfulness: float = 0.95, claims: list[str] | None = None) -> CriticVerdict:
    """Build a CriticVerdict for scripting FakeCritic."""

    return CriticVerdict(verdict=value, faithfulness=faithfulness, unsupported_claims=claims or [])


@dataclass
class FakeCritic:
    """Scripted critic: each item is a CriticVerdict or an exception to raise."""

    verdicts: list[CriticVerdict | BaseException] = field(default_factory=lambda: [verdict()])
    provider_name: str = "fake-critic"
    calls: list[CriticRequest] = field(default_factory=list)

    def critique(self, request: CriticRequest) -> CriticVerdict:
        self.calls.append(request)
        index = min(len(self.calls) - 1, len(self.verdicts) - 1)
        item = self.verdicts[index]
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def db_path(tmp_path: Any) -> str:
    """A path that is never opened: retrieve_fn is always faked in these tests."""

    return str(tmp_path / "unused_compliance.db")
