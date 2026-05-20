"""Tests for the grounded answer service boundary."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from src.db.queries import insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.rag import (
    AnswerProviderRequest,
    AnswerProviderResult,
    AnswerReasonCode,
    AnswerStatus,
    answer_question,
)
from src.retrieval.indexer import build_retrieval_index


def _seed_doc(db_path: str, *, doc_id: str, filename: str, pages: tuple[str, ...]) -> None:
    insert_document(db_path, doc_id, filename, f"/tmp/{filename}", len(pages), docling_json=None)
    mark_document_ingested(db_path, doc_id)
    for page_num, text in enumerate(pages):
        insert_page(db_path, doc_id, page_num, text, image_blob=None)


@dataclass
class FakeAnswerProvider:
    answer_text: str = "Acme Pharma has Pfizer supplier compliance approval evidence in the cited page."
    provider_name: str = "fake-provider"
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
        return AnswerProviderResult(
            answer_text=self.answer_text,
            trace_id=self.trace_id,
            provider_name=self.provider_name,
        )


def test_answer_question_returns_provider_answer_with_service_owned_citations(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-acme",
        filename="acme-sdf.pdf",
        pages=(
            "Supplier Declaration Form. Vendor Name: Acme Pharma Ltd. Quality Unit Approval: Pfizer supplier compliance documentation controls apply. Expiry Date: 2027-01-31.",
        ),
    )
    built = build_retrieval_index(tmp_db_path)
    provider = FakeAnswerProvider()

    result = answer_question(tmp_db_path, "Acme supplier compliance approval", provider=provider, top_k=1)

    assert result.status is AnswerStatus.ANSWERED
    assert result.is_answered is True
    assert result.answer_text == provider.answer_text
    assert len(provider.calls) == 1
    assert provider.calls[0].question == "Acme supplier compliance approval"
    assert provider.calls[0].run_id == built.run.run_id
    assert len(provider.calls[0].evidence) == 1
    assert not hasattr(provider.calls[0].evidence[0], "page_text")
    assert len(result.citations) == 1
    citation = result.citations[0]
    assert citation.doc_id == "doc-acme"
    assert citation.filename == "acme-sdf.pdf"
    assert citation.page_num == 0
    assert citation.display_page_num == 1
    assert "Acme Pharma Ltd." in citation.snippet
    assert citation.snippet == provider.calls[0].evidence[0].snippet
    assert result.diagnostics.status is AnswerStatus.ANSWERED
    assert result.diagnostics.reason_code is AnswerReasonCode.ANSWERED
    assert result.diagnostics.run_id == built.run.run_id
    assert result.diagnostics.provider_name == "fake-provider"
    assert result.diagnostics.trace_id == "trace-fake-001"
    assert result.diagnostics.citation_count == 1
    assert result.diagnostics.top_score > 0
    assert result.diagnostics.evidence_reason == "strong_evidence"


def test_answer_question_abstains_for_weak_evidence_without_provider_call(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-zeta", filename="zeta-sdf.pdf", pages=("Zeta supplier compliance page",))
    build_retrieval_index(tmp_db_path)
    provider = FakeAnswerProvider()

    result = answer_question(tmp_db_path, "astronomy telescope nebula", provider=provider, top_k=1)

    assert result.status is AnswerStatus.ABSTAINED
    assert result.citations == ()
    assert provider.calls == []
    assert result.diagnostics.reason_code is AnswerReasonCode.NO_MATCH
    assert result.diagnostics.provider_name == "fake-provider"
    assert result.diagnostics.citation_count == 0
    assert result.diagnostics.evidence_reason == "no_match"


def test_answer_question_abstains_for_blank_missing_and_stale_indexes_without_provider_call(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-stale", filename="stale.pdf", pages=("Original supplier compliance evidence",))
    build_retrieval_index(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    try:
        conn.execute("UPDATE pages SET page_text = ? WHERE doc_id = ? AND page_num = ?", ("Mutated source page text", "doc-stale", 0))
        conn.commit()
    finally:
        conn.close()
    stale_provider = FakeAnswerProvider()

    stale = answer_question(tmp_db_path, "Original supplier compliance", provider=stale_provider, top_k=1)

    assert stale.status is AnswerStatus.ABSTAINED
    assert stale.diagnostics.reason_code is AnswerReasonCode.INDEX_STALE
    assert stale_provider.calls == []

    missing_provider = FakeAnswerProvider()
    missing_db = tmp_db_path + ".missing.sqlite"
    init_db(missing_db)
    _seed_doc(missing_db, doc_id="doc-missing", filename="missing.pdf", pages=("Supplier compliance text",))

    missing = answer_question(missing_db, "supplier compliance", provider=missing_provider, top_k=1)

    assert missing.status is AnswerStatus.ABSTAINED
    assert missing.diagnostics.reason_code is AnswerReasonCode.INDEX_MISSING
    assert missing_provider.calls == []

    blank_provider = FakeAnswerProvider()
    blank = answer_question(tmp_db_path, "the and of to in", provider=blank_provider, top_k=1)

    assert blank.status is AnswerStatus.ABSTAINED
    assert blank.diagnostics.reason_code is AnswerReasonCode.EMPTY_QUESTION
    assert blank_provider.calls == []


def test_answer_question_maps_provider_exception_to_safe_provider_error(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-acme",
        filename="acme-sdf.pdf",
        pages=("Acme supplier compliance approval evidence is present for Pfizer review.",),
    )
    built = build_retrieval_index(tmp_db_path)
    secret = "SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR"
    provider = FakeAnswerProvider(exception=RuntimeError(secret))

    result = answer_question(tmp_db_path, "Acme supplier compliance approval", provider=provider, top_k=1)

    assert result.status is AnswerStatus.PROVIDER_ERROR
    assert result.citations == ()
    assert len(provider.calls) == 1
    assert result.diagnostics.reason_code is AnswerReasonCode.PROVIDER_EXCEPTION
    assert result.diagnostics.run_id == built.run.run_id
    assert result.diagnostics.error_class == "RuntimeError"
    assert secret not in repr(result)
    assert secret not in repr(result.diagnostics)


def test_answer_question_maps_blank_and_malformed_provider_results_to_safe_errors(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(
        tmp_db_path,
        doc_id="doc-acme",
        filename="acme-sdf.pdf",
        pages=("Acme supplier compliance approval evidence is present for Pfizer review.",),
    )
    build_retrieval_index(tmp_db_path)

    blank_provider = FakeAnswerProvider(answer_text="   ")
    blank = answer_question(tmp_db_path, "Acme supplier compliance approval", provider=blank_provider, top_k=1)

    assert blank.status is AnswerStatus.PROVIDER_ERROR
    assert blank.diagnostics.reason_code is AnswerReasonCode.PROVIDER_BLANK_ANSWER
    assert blank.diagnostics.error_class == "AnswerValidationError"
    assert blank.citations == ()

    malformed_provider = FakeAnswerProvider(malformed_result={"answer_text": "not a dataclass"})
    malformed = answer_question(tmp_db_path, "Acme supplier compliance approval", provider=malformed_provider, top_k=1)

    assert malformed.status is AnswerStatus.PROVIDER_ERROR
    assert malformed.diagnostics.reason_code is AnswerReasonCode.PROVIDER_MALFORMED_RESULT
    assert malformed.diagnostics.error_class == "AnswerValidationError"
    assert malformed.citations == ()


def test_answer_question_bounds_citations_to_top_k_and_owns_order(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    page_text = "Matched supplier compliance approval evidence appears here."
    _seed_doc(tmp_db_path, doc_id="doc-b", filename="b-sdf.pdf", pages=(page_text,))
    _seed_doc(tmp_db_path, doc_id="doc-a", filename="a-sdf.pdf", pages=(page_text, page_text))
    build_retrieval_index(tmp_db_path)
    provider = FakeAnswerProvider()

    result = answer_question(tmp_db_path, "supplier compliance approval", provider=provider, top_k=2)

    assert result.status is AnswerStatus.ANSWERED
    assert len(result.citations) == 2
    assert [(citation.filename, citation.doc_id, citation.page_num) for citation in result.citations] == [
        ("a-sdf.pdf", "doc-a", 0),
        ("a-sdf.pdf", "doc-a", 1),
    ]
    assert len(provider.calls[0].evidence) == 2
    assert result.diagnostics.citation_count == 2


def test_answer_question_redacts_full_page_tail_and_full_hash_from_public_repr(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    secret_tail = " API_KEY_SHOULD_NOT_APPEAR_IN_ANSWER_REPR"
    long_text = "Sigma supplier compliance approval evidence is near the beginning. " + ("middle filler " * 80) + secret_tail
    _seed_doc(tmp_db_path, doc_id="doc-sigma", filename="sigma-sdf.pdf", pages=(long_text,))
    built = build_retrieval_index(tmp_db_path)
    provider = FakeAnswerProvider(answer_text="Sigma has supplier compliance approval evidence on the cited page.")

    result = answer_question(tmp_db_path, "Sigma supplier compliance approval", provider=provider, top_k=1)
    result_repr = repr(result)

    assert result.status is AnswerStatus.ANSWERED
    assert secret_tail not in result_repr
    assert long_text not in result_repr
    assert built.run.content_hash not in result_repr
    assert len(result.citations[0].snippet) <= 222


def test_answer_question_turns_retrieval_exceptions_into_abstention(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.rag import service

    secret = "RAW_SQLITE_SECRET_SHOULD_NOT_APPEAR"

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise sqlite3.DatabaseError(secret)

    monkeypatch.setattr(service, "retrieve_evidence", _boom)
    provider = FakeAnswerProvider()

    result = service.answer_question(tmp_db_path, "supplier compliance", provider=provider, top_k=1)

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.RETRIEVAL_ERROR
    assert result.diagnostics.error_class == "DatabaseError"
    assert provider.calls == []
    assert secret not in repr(result)
