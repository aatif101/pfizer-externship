"""Package-level contract tests for the public src.rag API."""
from __future__ import annotations

import importlib
import sqlite3
from dataclasses import dataclass, field
from typing import Any

import pytest

from src.db.queries import insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.retrieval.indexer import build_retrieval_index


EXPECTED_PUBLIC_EXPORTS = {
    "AnswerCitation",
    "AnswerConfigurationError",
    "AnswerDiagnostics",
    "AnswerProvider",
    "AnswerProviderError",
    "AnswerProviderRequest",
    "AnswerProviderResult",
    "AnswerReasonCode",
    "AnswerResult",
    "AnswerStatus",
    "AnswerValidationError",
    "GeminiAnswerProvider",
    "GeminiAnswerProviderDiagnostics",
    "answer_question",
    "build_answer_provider",
}

FORBIDDEN_INTERNAL_EXPORTS = {
    "DEFAULT_GEMINI_ANSWER_MODEL",
    "_build_contents",
    "_bounded_snippet",
    "_response_text",
    "_response_trace_id",
    "_strip_simple_fences",
    "_is_retryable_provider_exception",
    "_citations_from_hits",
    "_provider_error_result",
    "_abstained_result",
    "_answer_reason_for_weak_evidence",
    "_provider_exception_reason",
    "_provider_name",
}


@dataclass
class ContractProvider:
    provider_name: str = "contract-fake"
    calls: list[Any] = field(default_factory=list)
    exception: BaseException | None = None
    answer_text: str = "Contract fake answer grounded in the cited supplier page."

    def answer(self, request: Any) -> Any:
        from src.rag import AnswerProviderResult

        self.calls.append(request)
        if self.exception is not None:
            raise self.exception
        return AnswerProviderResult(
            answer_text=self.answer_text,
            trace_id="contract-trace-001",
            provider_name=self.provider_name,
        )


def _seed_doc(db_path: str, *, doc_id: str, filename: str, pages: tuple[str, ...]) -> None:
    insert_document(db_path, doc_id, filename, f"/tmp/{filename}", len(pages), docling_json=None)
    mark_document_ingested(db_path, doc_id)
    for page_num, text in enumerate(pages):
        insert_page(db_path, doc_id, page_num, text, image_blob=None)


def test_rag_package_exports_stable_public_contract() -> None:
    import src.rag as rag
    from src.rag import (  # noqa: PLC0415 - contract import under test
        AnswerCitation,
        AnswerConfigurationError,
        AnswerDiagnostics,
        AnswerProvider,
        AnswerProviderError,
        AnswerProviderRequest,
        AnswerProviderResult,
        AnswerReasonCode,
        AnswerResult,
        AnswerStatus,
        AnswerValidationError,
        GeminiAnswerProvider,
        GeminiAnswerProviderDiagnostics,
        answer_question,
        build_answer_provider,
    )

    assert set(rag.__all__) == EXPECTED_PUBLIC_EXPORTS
    assert AnswerCitation is rag.AnswerCitation
    assert AnswerConfigurationError is rag.AnswerConfigurationError
    assert AnswerDiagnostics is rag.AnswerDiagnostics
    assert AnswerProvider is rag.AnswerProvider
    assert AnswerProviderError is rag.AnswerProviderError
    assert AnswerProviderRequest is rag.AnswerProviderRequest
    assert AnswerProviderResult is rag.AnswerProviderResult
    assert AnswerReasonCode is rag.AnswerReasonCode
    assert AnswerResult is rag.AnswerResult
    assert AnswerStatus is rag.AnswerStatus
    assert AnswerValidationError is rag.AnswerValidationError
    assert GeminiAnswerProvider is rag.GeminiAnswerProvider
    assert GeminiAnswerProviderDiagnostics is rag.GeminiAnswerProviderDiagnostics
    assert answer_question is rag.answer_question
    assert build_answer_provider is rag.build_answer_provider


def test_rag_package_does_not_export_prompt_helpers_or_private_parsers() -> None:
    import src.rag as rag

    exported = set(rag.__all__)

    assert exported.isdisjoint(FORBIDDEN_INTERNAL_EXPORTS)
    for name in FORBIDDEN_INTERNAL_EXPORTS:
        assert not hasattr(rag, name)


def test_importing_rag_modules_without_credentials_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    rag = importlib.import_module("src.rag")
    gemini = importlib.import_module("src.rag.gemini")
    providers = importlib.import_module("src.rag.providers")

    assert rag.GeminiAnswerProvider.provider_name == "gemini"
    assert gemini.GeminiAnswerProvider.provider_name == "gemini"
    assert providers.build_answer_provider(None) is None


def test_answer_result_diagnostics_are_bounded_for_weak_evidence(tmp_db_path: str) -> None:
    import src.rag as rag

    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, doc_id="doc-zeta", filename="zeta-sdf.pdf", pages=("Zeta supplier compliance page",))
    build_retrieval_index(tmp_db_path)
    provider = ContractProvider()

    result = rag.answer_question(tmp_db_path, "astronomy telescope nebula", provider=provider, top_k=1)

    assert result.status is rag.AnswerStatus.ABSTAINED
    assert result.citations == ()
    assert provider.calls == []
    assert result.diagnostics.status is rag.AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is rag.AnswerReasonCode.NO_MATCH
    assert result.diagnostics.provider_name == "contract-fake"
    assert result.diagnostics.trace_id is None
    assert result.diagnostics.citation_count == 0
    assert result.diagnostics.evidence_reason == "no_match"
    assert result.diagnostics.error_class is None


def test_answer_result_diagnostics_are_bounded_for_provider_error(tmp_db_path: str) -> None:
    import src.rag as rag

    init_db(tmp_db_path)
    secret = "RAW_PROVIDER_RESPONSE_AND_API_KEY_SHOULD_NOT_APPEAR"
    _seed_doc(
        tmp_db_path,
        doc_id="doc-acme",
        filename="acme-sdf.pdf",
        pages=(
            "Acme supplier compliance approval evidence is present for Pfizer review. "
            + ("full page filler " * 60)
            + secret,
        ),
    )
    built = build_retrieval_index(tmp_db_path)
    provider = ContractProvider(exception=RuntimeError(secret))

    result = rag.answer_question(tmp_db_path, "Acme supplier compliance approval", provider=provider, top_k=1)

    assert result.status is rag.AnswerStatus.PROVIDER_ERROR
    assert result.answer_text == "I found relevant evidence, but answer generation failed safely. Please retry or inspect diagnostics."
    assert result.citations == ()
    assert len(provider.calls) == 1
    assert result.diagnostics.status is rag.AnswerStatus.PROVIDER_ERROR
    assert result.diagnostics.reason_code is rag.AnswerReasonCode.PROVIDER_EXCEPTION
    assert result.diagnostics.run_id == built.run.run_id
    assert result.diagnostics.provider_name == "contract-fake"
    assert result.diagnostics.trace_id is None
    assert result.diagnostics.top_score > 0
    assert result.diagnostics.citation_count == 0
    assert result.diagnostics.evidence_reason == "strong_evidence"
    assert result.diagnostics.error_class == "RuntimeError"
    assert secret not in repr(result)
    assert built.run.content_hash not in repr(result)


def test_rag_public_api_handles_retrieval_errors_without_raw_error_leak(monkeypatch: pytest.MonkeyPatch, tmp_db_path: str) -> None:
    from src.rag import service
    import src.rag as rag

    secret = "RAW_SQLITE_EXCEPTION_SHOULD_NOT_APPEAR"

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise sqlite3.DatabaseError(secret)

    monkeypatch.setattr(service, "retrieve_evidence", _boom)
    provider = ContractProvider()

    result = rag.answer_question(tmp_db_path, "supplier compliance", provider=provider, top_k=1)

    assert result.status is rag.AnswerStatus.ABSTAINED
    assert result.citations == ()
    assert provider.calls == []
    assert result.diagnostics.reason_code is rag.AnswerReasonCode.RETRIEVAL_ERROR
    assert result.diagnostics.error_class == "DatabaseError"
    assert secret not in repr(result)
