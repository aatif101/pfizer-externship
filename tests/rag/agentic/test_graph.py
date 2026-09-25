"""Offline integration tests for the agentic LangGraph RAG graph (RAG-03).

All collaborators are fakes from conftest.py: no SQLite index, no network, no
LLM SDK. Assertions cover routing, loop bounds, and contract shape only.
"""
from __future__ import annotations

import functools
import importlib
import itertools

import pytest

from src.rag.agentic import answer_question_agentic
from src.rag.critic import CriticValidationError
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


def _fresh_rewriter():
    counter = itertools.count(1)
    return lambda query: f"{query} variant {next(counter)}"


def test_retrieval_retries_capped_abstain(db_path: str) -> None:
    retrieve = FakeRetrieve(results=[weak_result()])
    provider = FakeAnswerProvider()
    critic = FakeCritic()

    result = answer_question_agentic(
        db_path, "What is the CAS number?", provider=provider, critic=critic,
        retrieve_fn=retrieve, rewriter=_fresh_rewriter(),
    )

    assert len(retrieve.calls) == 3
    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_EXHAUSTED
    assert result.diagnostics.retrieval_rounds == 3
    assert provider.calls == []
    assert critic.calls == []
    # Retries use the rewritten query text, never the same text twice.
    assert len({question for question, _ in retrieve.calls}) == 3


def test_rewriter_repeating_query_stops_early(db_path: str) -> None:
    retrieve = FakeRetrieve(results=[weak_result()])
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, "What is the CAS number?", provider=provider, critic=FakeCritic(),
        retrieve_fn=retrieve, rewriter=lambda query: query,
    )

    assert len(retrieve.calls) == 1
    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_EXHAUSTED
    assert provider.calls == []


def test_reretrieve_recovers(db_path: str) -> None:
    retrieve = FakeRetrieve(results=[weak_result(), strong_result()])
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=FakeCritic(),
        retrieve_fn=retrieve, rewriter=_fresh_rewriter(),
    )

    assert result.status is AnswerStatus.ANSWERED
    assert result.diagnostics.retrieval_rounds == 2
    assert len(provider.calls) == 1


def test_gate_thresholds_never_relaxed(db_path: str) -> None:
    retrieve = FakeRetrieve(results=[weak_result(), weak_result(), strong_result()])

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=FakeAnswerProvider(), critic=FakeCritic(),
        retrieve_fn=retrieve, rewriter=_fresh_rewriter(),
    )

    assert result.status is AnswerStatus.ANSWERED
    assert len(retrieve.calls) == 3
    for _question, kwargs in retrieve.calls:
        assert kwargs == {"top_k": 5}


def test_regeneration_capped_then_abstain(db_path: str) -> None:
    provider = FakeAnswerProvider(answers=["First draft", "Second draft"])
    critic = FakeCritic(
        verdicts=[
            verdict("unsupported", 0.2, ["Lot 42 expires in 2030"]),
            verdict("unsupported", 0.3, ["Still unsupported"]),
        ]
    )

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=critic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
    )

    assert len(provider.calls) == 2
    assert len(critic.calls) == 2
    assert result.status is AnswerStatus.ABSTAINED
    assert result.citations == ()
    assert result.diagnostics.reason_code is AnswerReasonCode.CRITIC_REJECTED
    assert result.diagnostics.regeneration_count == 1
    assert result.diagnostics.critic_verdict == "unsupported"
    assert provider.calls[0].revision_hint is None
    assert provider.calls[1].revision_hint
    assert "Lot 42 expires in 2030" in provider.calls[1].revision_hint


def test_regenerate_then_accept(db_path: str) -> None:
    provider = FakeAnswerProvider(answers=["First draft", "Second draft"])
    critic = FakeCritic(verdicts=[verdict("unsupported", 0.2), verdict("supported", 0.9)])

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=critic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
    )

    assert result.status is AnswerStatus.ANSWERED
    assert result.answer_text == "Second draft"
    assert result.diagnostics.regeneration_count == 1
    assert result.diagnostics.critic_score == 0.9
    # Empty unsupported_claims still yields a non-empty generic hint.
    assert provider.calls[1].revision_hint


def test_below_threshold_supported_is_rejected(db_path: str) -> None:
    provider = FakeAnswerProvider()
    critic = FakeCritic(verdicts=[verdict("supported", 0.5)])

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=critic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.CRITIC_REJECTED
    assert len(provider.calls) == 2  # rejection -> one regeneration, not an error
    assert result.diagnostics.error_class is None


def test_critic_min_faithfulness_override(db_path: str) -> None:
    result = answer_question_agentic(
        db_path, "When does it expire?", provider=FakeAnswerProvider(),
        critic=FakeCritic(verdicts=[verdict("supported", 0.5)]),
        retrieve_fn=FakeRetrieve(results=[strong_result()]), critic_min_faithfulness=0.4,
    )

    assert result.status is AnswerStatus.ANSWERED


@pytest.mark.parametrize(
    "critic_factory",
    [
        pytest.param(lambda: FakeCritic(verdicts=[RuntimeError("boom")]), id="critic-raises-runtime-error"),
        pytest.param(
            lambda: FakeCritic(verdicts=[CriticValidationError("critic verdict failed validation")]),
            id="critic-raises-validation-error",
        ),
        pytest.param(lambda: None, id="critic-missing"),
    ],
)
def test_critic_failure_fails_closed(db_path: str, critic_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import get_settings

    # 06-04: critic=None is resolved from settings; with no Anthropic key it
    # fails closed as CriticConfigurationError (D-02, no Gemini fallback).
    monkeypatch.setenv("CRITIC_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    critic = critic_factory()
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=critic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.CRITIC_ERROR
    assert result.citations == ()
    assert result.diagnostics.error_class
    if critic is None:
        assert provider.calls == []
        assert result.diagnostics.error_class == "CriticConfigurationError"
    else:
        assert len(critic.calls) == 1
    get_settings.cache_clear()


def test_malformed_critic_verdict_fails_closed(db_path: str) -> None:
    critic = FakeCritic(verdicts=[{"verdict": "supported", "faithfulness": 1.0}])  # type: ignore[list-item]

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=FakeAnswerProvider(), critic=critic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.CRITIC_ERROR
    assert result.diagnostics.error_class == "CriticValidationError"


def test_provider_exception_is_provider_error_without_critic_call(db_path: str) -> None:
    provider = FakeAnswerProvider(exception=RuntimeError("quota"))
    critic = FakeCritic()

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=critic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
    )

    assert result.status is AnswerStatus.PROVIDER_ERROR
    assert result.diagnostics.reason_code is AnswerReasonCode.PROVIDER_EXCEPTION
    assert result.citations == ()
    assert critic.calls == []


def test_citations_service_owned(db_path: str) -> None:
    hits = (make_hit("fake", 3, 0.9, "Expiry Date: 2027-01-31"),)
    provider = FakeAnswerProvider(answers=["Expires 2027-01-31 [Source: fake.pdf p.99]"])

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=FakeCritic(),
        retrieve_fn=FakeRetrieve(results=[strong_result(hits)]),
    )

    assert result.status is AnswerStatus.ANSWERED
    assert _pairs(result) == [("fake", 3)]
    assert all(citation.page_num != 99 and citation.display_page_num != 99 for citation in result.citations)


def test_retrieval_exception_abstains(db_path: str) -> None:
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, "When does it expire?", provider=provider, critic=FakeCritic(),
        retrieve_fn=FakeRetrieve(results=[OSError("db locked")]),
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_ERROR
    assert result.diagnostics.error_class == "OSError"
    assert provider.calls == []


def test_recursion_backstop(db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_module = importlib.import_module("src.rag.agentic.graph")
    monkeypatch.setattr(graph_module, "GRAPH_RECURSION_LIMIT", 3)
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, "What is the CAS number?", provider=provider, critic=FakeCritic(),
        retrieve_fn=FakeRetrieve(results=[weak_result()]), rewriter=_fresh_rewriter(),
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.error_class == "GraphRecursionError"
    assert result.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_EXHAUSTED
    assert result.diagnostics.pipeline == "agentic"
    assert provider.calls == []


def test_eval_answer_fn_compat(db_path: str) -> None:
    answer_fn = functools.partial(
        answer_question_agentic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
        critic=FakeCritic(),
    )
    provider = FakeAnswerProvider()

    result = answer_fn(db_path, "q", provider=provider)

    assert isinstance(result, AnswerResult)
    assert result.is_answered


def test_abstain_on_weak_evidence_and_critic_reject(db_path: str) -> None:
    weak = answer_question_agentic(
        db_path, "What is the CAS number?", provider=FakeAnswerProvider(), critic=FakeCritic(),
        retrieve_fn=FakeRetrieve(results=[weak_result()]),
    )
    rejected = answer_question_agentic(
        db_path, "When does it expire?", provider=FakeAnswerProvider(),
        critic=FakeCritic(verdicts=[verdict("unsupported", 0.1)]),
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
    )

    for result in (weak, rejected):
        assert result.status is AnswerStatus.ABSTAINED
        assert result.citations == ()
        assert result.answer_text == "I don't have enough grounded evidence in the indexed corpus to answer that safely."
    assert weak.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_EXHAUSTED
    assert rejected.diagnostics.reason_code is AnswerReasonCode.CRITIC_REJECTED
