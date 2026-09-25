"""Decomposition and query-rewrite tests for the agentic RAG graph (RAG-03).

Pure-module tests need no langgraph. Graph-level tests reuse the offline fakes
from conftest.py: no SQLite index, no network, no LLM SDK.
"""
from __future__ import annotations

import pytest

from src.rag.agentic.decompose import (
    build_decompose_prompt,
    decompose_question,
    heuristic_split,
    is_compound,
    parse_llm_subqueries,
)
from src.rag.agentic.rewrite import (
    DOMAIN_SYNONYMS,
    build_rewrite_prompt,
    expand_with_synonyms,
    parse_llm_rewrite,
    rewrite_query,
)
from src.rag.agentic.state import MAX_SUB_QUERIES

SINGLE = "What is the expiry date of the Sigma CoA?"
TWO_FIELD = "What is the expiry date and the manufacturing date of the Sigma CoA?"


class _Spy:
    def __init__(self, output: str = "") -> None:
        self.output = output
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.output


# --------------------------------------------------------------------------- decompose


def test_is_compound_single_intent_false() -> None:
    assert is_compound(SINGLE) is False
    assert is_compound("When does lot 42 expire?") is False
    assert is_compound("What is the CAS number?") is False


def test_is_compound_two_fields_true() -> None:
    assert is_compound(TWO_FIELD) is True


def test_is_compound_comparison_true() -> None:
    assert is_compound("Compare vendor A vs vendor B") is True
    assert is_compound("Sigma versus Merck expiry") is True


def test_is_compound_multiple_questions_true() -> None:
    assert is_compound("Who is the vendor? When does it expire?") is True


def test_heuristic_split_two_fields_keeps_subject() -> None:
    parts = heuristic_split(TWO_FIELD)
    assert len(parts) == 2
    for part in parts:
        assert "Sigma CoA" in part
    assert any("expiry" in part.lower() for part in parts)
    assert any("manufactur" in part.lower() for part in parts)


def test_heuristic_split_question_marks() -> None:
    parts = heuristic_split("Who is the vendor? When does it expire?")
    assert parts == ["Who is the vendor?", "When does it expire?"]


def test_heuristic_split_comparison() -> None:
    parts = heuristic_split("Compare vendor A vs vendor B")
    assert len(parts) == 2
    assert "vendor A" in parts[0]
    assert "vendor B" in parts[1]


def test_heuristic_split_capped_and_never_empty() -> None:
    parts = heuristic_split("A? B? C? D? E?")
    assert 1 <= len(parts) <= MAX_SUB_QUERIES
    assert heuristic_split("plain question") == ["plain question"]
    assert len(heuristic_split("   ")) == 1


def test_build_decompose_prompt_mentions_json_array() -> None:
    prompt = build_decompose_prompt(TWO_FIELD)
    assert TWO_FIELD in prompt
    assert "JSON array" in prompt
    assert "3" in prompt


def test_parse_llm_subqueries_fenced_json() -> None:
    parsed = parse_llm_subqueries('```json\n["expiry date Sigma CoA", "manufacturing date Sigma CoA"]\n```')
    assert parsed == ["expiry date Sigma CoA", "manufacturing date Sigma CoA"]


@pytest.mark.parametrize(
    "text",
    ["nonsense", '{"a": "b"}', "[]", '["   ", ""]', '[1, 2]', '["ok", ' + '"' + "x" * 201 + '"]', ""],
)
def test_parse_llm_subqueries_rejects_malformed(text: str) -> None:
    assert parse_llm_subqueries(text) is None


def test_parse_llm_subqueries_caps_and_drops_blanks() -> None:
    assert parse_llm_subqueries('["a1", "b2", "c3", "d4", "e5"]') == ["a1", "b2", "c3"]
    assert parse_llm_subqueries('["a1", "  ", "b2"]') == ["a1", "b2"]


def test_decompose_single_never_calls_llm() -> None:
    spy = _Spy('["x", "y"]')
    assert decompose_question(SINGLE, llm=spy) == ([SINGLE], "single")
    assert spy.calls == []


def test_decompose_compound_llm_garbage_falls_back() -> None:
    subs, method = decompose_question(TWO_FIELD, llm=lambda prompt: "garbage")
    assert method == "llm_fallback"
    assert subs == heuristic_split(TWO_FIELD)


def test_decompose_compound_llm_exception_falls_back() -> None:
    def boom(prompt: str) -> str:
        raise RuntimeError("quota")

    subs, method = decompose_question(TWO_FIELD, llm=boom)
    assert method == "llm_fallback"
    assert subs == heuristic_split(TWO_FIELD)


def test_decompose_compound_without_llm_is_heuristic() -> None:
    assert decompose_question(TWO_FIELD, llm=None) == (heuristic_split(TWO_FIELD), "heuristic")


def test_decompose_compound_llm_success() -> None:
    spy = _Spy('["expiry date Sigma CoA", "manufacturing date Sigma CoA"]')
    subs, method = decompose_question(TWO_FIELD, llm=spy)
    assert method == "llm"
    assert subs == ["expiry date Sigma CoA", "manufacturing date Sigma CoA"]
    assert len(spy.calls) == 1


# --------------------------------------------------------------------------- rewrite


def test_domain_synonyms_has_required_keys() -> None:
    for key in ("expiry", "manufacturing", "coa", "coq", "revision", "vendor", "effective"):
        assert key in DOMAIN_SYNONYMS


def test_expand_with_synonyms_expiry() -> None:
    expanded = expand_with_synonyms("expiry date of lot 123")
    assert expanded is not None
    assert "expiration" in expanded
    assert "valid until" in expanded


def test_expand_with_synonyms_coa() -> None:
    expanded = expand_with_synonyms("CoA for vendor X")
    assert expanded is not None
    assert "certificate of analysis" in expanded


def test_expand_with_synonyms_no_progress() -> None:
    expanded = expand_with_synonyms("expiry date of lot 123")
    assert expanded is not None
    assert expand_with_synonyms(expanded) is None
    assert expand_with_synonyms("hello world") is None


def test_build_rewrite_prompt_contains_query() -> None:
    prompt = build_rewrite_prompt("CAS number")
    assert "CAS number" in prompt
    assert "keyword" in prompt.lower()


def test_parse_llm_rewrite() -> None:
    assert parse_llm_rewrite('"expiration date Sigma"') == "expiration date Sigma"
    assert parse_llm_rewrite("```\nexpiration date Sigma\nextra\n```") == "expiration date Sigma"
    assert parse_llm_rewrite("\n\n  ab  \n") is None
    assert parse_llm_rewrite("x" * 201) is None
    assert parse_llm_rewrite("") is None


def test_rewrite_query_synonyms_first() -> None:
    query = "expiry date Sigma"
    new, method = rewrite_query(query, tried=[query], llm=None)
    assert method == "synonyms"
    assert new == expand_with_synonyms(query)


def test_rewrite_query_synonym_already_tried_exhausted() -> None:
    query = "expiry date Sigma"
    expanded = expand_with_synonyms(query)
    assert expanded is not None
    assert rewrite_query(query, tried=[query, "  " + expanded.upper() + " "], llm=None) == (None, "exhausted")


def test_rewrite_query_llm_new_line() -> None:
    query = "CAS number"
    assert rewrite_query(query, tried=[query], llm=lambda prompt: "chemical abstracts service registry") == (
        "chemical abstracts service registry",
        "llm",
    )


def test_rewrite_query_llm_repeat_exhausted() -> None:
    query = "CAS number"
    assert rewrite_query(query, tried=[query], llm=lambda prompt: "cas   NUMBER") == (None, "exhausted")


def test_rewrite_query_llm_echo_is_no_progress() -> None:
    query = "CAS number"
    assert rewrite_query(query, tried=[query], llm=lambda prompt: prompt) == (None, "exhausted")


def test_rewrite_query_llm_raises_exhausted() -> None:
    def boom(prompt: str) -> str:
        raise RuntimeError("quota")

    assert rewrite_query("CAS number", tried=["CAS number"], llm=boom) == (None, "exhausted")


# --------------------------------------------------------------------------- graph level

from dataclasses import dataclass, field  # noqa: E402
from typing import Any, Callable  # noqa: E402

from src.rag.agentic import answer_question_agentic  # noqa: E402
from src.rag.agentic import nodes as agentic_nodes  # noqa: E402
from src.rag.models import AnswerReasonCode, AnswerStatus  # noqa: E402
from src.retrieval.models import EvidenceGateResult  # noqa: E402

from tests.rag.agentic.conftest import (  # noqa: E402
    FakeAnswerProvider,
    FakeCritic,
    make_hit,
    strong_result,
    weak_result,
)

EXPIRY_HITS = (make_hit("doc-a", 0, 0.9, "Expiry Date: 2027-01-31"), make_hit("doc-b", 1, 0.6, "Valid until 2027"))
MFG_HITS = (make_hit("doc-a", 0, 0.8, "Mfg Date: 2024-01-31"), make_hit("doc-c", 3, 0.7, "Manufactured 2024"))


@dataclass
class _RoutedRetrieve:
    """retrieve_fn fake whose result depends on the query text."""

    route: Callable[[str], EvidenceGateResult]
    calls: list[str] = field(default_factory=list)

    def __call__(self, db_path: str, query: str, **kwargs: Any) -> EvidenceGateResult:
        self.calls.append(query)
        return self.route(query)


def _by_field(expiry_strong: bool, mfg_strong: bool) -> Callable[[str], EvidenceGateResult]:
    def route(query: str) -> EvidenceGateResult:
        lowered = query.lower()
        if "expiry" in lowered:
            return strong_result(EXPIRY_HITS) if expiry_strong else weak_result()
        if "manufactur" in lowered:
            return strong_result(MFG_HITS) if mfg_strong else weak_result()
        return weak_result()

    return route


def test_compound_question_retrieves_each_subquery(db_path: str) -> None:
    retrieve = _RoutedRetrieve(_by_field(True, True))
    provider = FakeAnswerProvider()

    result = answer_question_agentic(db_path, TWO_FIELD, provider=provider, critic=FakeCritic(), retrieve_fn=retrieve)

    assert result.status is AnswerStatus.ANSWERED
    assert len(retrieve.calls) == 2
    assert result.diagnostics.sub_query_count == 2
    assert result.diagnostics.retrieval_rounds == 1
    pairs = [(citation.doc_id, citation.page_num) for citation in result.citations]
    # Merged across sub-queries, deduped by (doc_id, page_num), max score kept, score-ordered.
    assert pairs == [("doc-a", 0), ("doc-c", 3), ("doc-b", 1)]
    assert len(provider.calls) == 1


def test_compound_partial_coverage_abstains(db_path: str) -> None:
    retrieve = _RoutedRetrieve(_by_field(True, False))
    provider = FakeAnswerProvider()
    critic = FakeCritic()

    result = answer_question_agentic(db_path, TWO_FIELD, provider=provider, critic=critic, retrieve_fn=retrieve)

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_EXHAUSTED
    assert result.citations == ()
    assert provider.calls == []
    assert critic.calls == []
    expiry_calls = [query for query in retrieve.calls if "expiry" in query.lower()]
    mfg_calls = [query for query in retrieve.calls if "manufactur" in query.lower()]
    assert len(expiry_calls) == 1  # only failing sub-queries are re-retrieved
    assert len(mfg_calls) == 2  # original + one synonym rewrite, then exhausted
    assert "mfg" in mfg_calls[1]
    assert result.diagnostics.retrieval_rounds == 2


def test_synonym_rewrite_recovers(db_path: str) -> None:
    retrieve = _RoutedRetrieve(lambda query: strong_result() if "expiration" in query else weak_result())
    rewriter = _Spy("should not be used")
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, "expiry date Sigma", provider=provider, critic=FakeCritic(), retrieve_fn=retrieve, rewriter=rewriter
    )

    assert result.status is AnswerStatus.ANSWERED
    assert result.diagnostics.retrieval_rounds == 2
    assert rewriter.calls == []
    assert len(provider.calls) == 1


def test_rewrite_no_progress_abstains(db_path: str) -> None:
    question = "What is the CAS number?"
    retrieve = _RoutedRetrieve(lambda query: weak_result())
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, question, provider=provider, critic=FakeCritic(), retrieve_fn=retrieve,
        rewriter=lambda prompt: question,
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_EXHAUSTED
    assert result.diagnostics.retrieval_rounds < 3
    assert retrieve.calls == [question]
    assert provider.calls == []


class _SpanRecorder:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update_current_span(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


def test_node_spans_allowlisted(db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _SpanRecorder()
    monkeypatch.setattr(agentic_nodes, "langfuse_context", recorder)
    monkeypatch.setattr(agentic_nodes, "_LANGFUSE_AVAILABLE", True)

    answered = answer_question_agentic(
        db_path, TWO_FIELD, provider=FakeAnswerProvider(), critic=FakeCritic(),
        retrieve_fn=_RoutedRetrieve(_by_field(True, True)),
    )
    abstained = answer_question_agentic(
        db_path, TWO_FIELD, provider=FakeAnswerProvider(), critic=FakeCritic(),
        retrieve_fn=_RoutedRetrieve(_by_field(True, False)),
    )
    assert answered.status is AnswerStatus.ANSWERED
    assert abstained.status is AnswerStatus.ABSTAINED

    assert recorder.updates, "nodes must attach span metadata"
    forbidden_text = [TWO_FIELD, "Sigma", *(hit.snippet for hit in EXPIRY_HITS + MFG_HITS), "Answer text"]
    seen_keys: set[str] = set()
    for update in recorder.updates:
        assert set(update) == {"metadata"}
        metadata = update["metadata"]
        assert set(metadata) <= agentic_nodes._NODE_SPAN_ALLOWED_KEYS
        seen_keys |= set(metadata)
        for value in metadata.values():
            for text in forbidden_text:
                assert text not in str(value)
    for key in ("retrieval_round", "sub_query_count", "citation_count", "critic_verdict", "reason_code", "doc_id"):
        assert key in seen_keys
    for banned in ("question", "snippet", "evidence_text", "draft", "critic_feedback"):
        assert banned not in agentic_nodes._NODE_SPAN_ALLOWED_KEYS


def test_node_spans_disabled_seam(db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _SpanRecorder()
    monkeypatch.setattr(agentic_nodes, "langfuse_context", recorder)
    monkeypatch.setattr(agentic_nodes, "_LANGFUSE_AVAILABLE", False)

    answer_question_agentic(
        db_path, SINGLE, provider=FakeAnswerProvider(), critic=FakeCritic(),
        retrieve_fn=_RoutedRetrieve(lambda query: strong_result()),
    )

    assert recorder.updates == []
