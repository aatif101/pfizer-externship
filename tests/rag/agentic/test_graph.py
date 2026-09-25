"""Offline integration tests for the agentic LangGraph RAG graph (RAG-03).

All collaborators are fakes from conftest.py: no SQLite index, no network, no
LLM SDK. Assertions cover routing, loop bounds, and contract shape only.
"""
from __future__ import annotations

from src.rag.agentic import answer_question_agentic
from src.rag.models import AnswerReasonCode, AnswerResult, AnswerStatus

from tests.rag.agentic.conftest import (
    FakeAnswerProvider,
    FakeCritic,
    FakeRetrieve,
    make_hit,
    strong_result,
    verdict,
    weak_result,
)


def _pairs(result: AnswerResult) -> list[tuple[str, int]]:
    return [(citation.doc_id, citation.page_num) for citation in result.citations]


def test_answered_happy_path(db_path: str) -> None:
    hits = (make_hit("doc-a", 0, 0.9, "Expiry Date: 2027-01-31"), make_hit("doc-b", 2, 0.7, "Lot 42"))
    retrieve = FakeRetrieve(results=[strong_result(hits)])
    provider = FakeAnswerProvider(answers=["Answer text"])
    critic = FakeCritic(verdicts=[verdict("supported", 0.95)])

    result = answer_question_agentic(
        db_path, "When does lot 42 expire?", provider=provider, critic=critic, retrieve_fn=retrieve
    )

    assert result.status is AnswerStatus.ANSWERED
    assert result.answer_text == "Answer text"
    assert _pairs(result) == [("doc-a", 0), ("doc-b", 2)]
    diagnostics = result.diagnostics
    assert diagnostics.reason_code is AnswerReasonCode.ANSWERED
    assert diagnostics.pipeline == "agentic"
    assert diagnostics.retrieval_rounds == 1
    assert diagnostics.regeneration_count == 0
    assert diagnostics.sub_query_count == 1
    assert diagnostics.critic_verdict == "supported"
    assert diagnostics.critic_score == 0.95
    assert diagnostics.citation_count == 2
    assert len(provider.calls) == 1
    assert provider.calls[0].revision_hint is None
    assert len(critic.calls) == 1


def test_weak_evidence_abstains_without_provider_call(db_path: str) -> None:
    retrieve = FakeRetrieve(results=[weak_result()])
    provider = FakeAnswerProvider()
    critic = FakeCritic()

    result = answer_question_agentic(db_path, "What is the CAS number?", provider=provider, critic=critic, retrieve_fn=retrieve)

    assert result.status is AnswerStatus.ABSTAINED
    assert result.citations == ()
    assert provider.calls == []
    assert critic.calls == []
    assert result.diagnostics.pipeline == "agentic"


def test_provider_none_is_configuration_error(db_path: str) -> None:
    retrieve = FakeRetrieve(results=[strong_result()])
    critic = FakeCritic()

    result = answer_question_agentic(db_path, "When does it expire?", provider=None, critic=critic, retrieve_fn=retrieve)

    assert result.status is AnswerStatus.PROVIDER_ERROR
    assert result.diagnostics.reason_code is AnswerReasonCode.PROVIDER_CONFIGURATION_ERROR
    assert result.citations == ()
    assert critic.calls == []


def test_empty_question_abstains_without_retrieval(db_path: str) -> None:
    retrieve = FakeRetrieve(results=[strong_result()])
    provider = FakeAnswerProvider()

    result = answer_question_agentic(db_path, "   ", provider=provider, critic=FakeCritic(), retrieve_fn=retrieve)

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.EMPTY_QUESTION
    assert retrieve.calls == []
    assert provider.calls == []
