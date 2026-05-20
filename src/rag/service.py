"""Grounded answer service built on the deterministic retrieval evidence gate.

The service owns the no-hallucination boundary: retrieval evidence is checked
before any provider call, citations are derived only from retrieval hits, and
failure diagnostics are bounded to safe status metadata.
"""
from __future__ import annotations

from uuid import uuid4

from src.rag.models import (
    AnswerCitation,
    AnswerDiagnostics,
    AnswerReasonCode,
    AnswerResult,
    AnswerStatus,
)
from src.rag.providers import (
    AnswerConfigurationError,
    AnswerProvider,
    AnswerProviderRequest,
    AnswerProviderResult,
    AnswerValidationError,
)
from src.retrieval import RetrievalEvidenceReason, RetrievalHit, retrieve_evidence

_DEFAULT_TOP_K = 5
_PROVIDERLESS_NAME = "unconfigured"

_RETRIEVAL_TO_ANSWER_REASON: dict[RetrievalEvidenceReason, AnswerReasonCode] = {
    RetrievalEvidenceReason.EMPTY_QUESTION: AnswerReasonCode.EMPTY_QUESTION,
    RetrievalEvidenceReason.INDEX_MISSING: AnswerReasonCode.INDEX_MISSING,
    RetrievalEvidenceReason.INDEX_EMPTY: AnswerReasonCode.INDEX_EMPTY,
    RetrievalEvidenceReason.INDEX_STALE: AnswerReasonCode.INDEX_STALE,
    RetrievalEvidenceReason.NO_MATCH: AnswerReasonCode.NO_MATCH,
    RetrievalEvidenceReason.BELOW_THRESHOLD: AnswerReasonCode.BELOW_THRESHOLD,
    RetrievalEvidenceReason.RETRIEVAL_ERROR: AnswerReasonCode.RETRIEVAL_ERROR,
}

_PROVIDER_ERROR_REASON_BY_EXCEPTION: tuple[tuple[type[BaseException], AnswerReasonCode], ...] = (
    (AnswerConfigurationError, AnswerReasonCode.PROVIDER_CONFIGURATION_ERROR),
    (AnswerValidationError, AnswerReasonCode.PROVIDER_MALFORMED_RESULT),
)


def answer_question(
    db_path: str,
    question: str,
    *,
    provider: AnswerProvider | None,
    top_k: int = _DEFAULT_TOP_K,
    candidate_limit: int = 50,
    min_top_score: float = 0.45,
    min_query_term_coverage: float = 0.50,
    min_hit_count: int = 1,
) -> AnswerResult:
    """Return a cited answer or safe abstention/provider error.

    Retrieval is authoritative and always runs first. Providers receive only the
    bounded ``RetrievalHit`` snippets exposed by S02 and are never called for
    weak evidence. Public diagnostics intentionally omit raw provider responses,
    full page text, image blobs, secrets, and full corpus hashes.
    """

    bounded_top_k = max(1, int(top_k))
    try:
        evidence = retrieve_evidence(
            db_path,
            question,
            top_k=bounded_top_k,
            candidate_limit=candidate_limit,
            min_top_score=min_top_score,
            min_query_term_coverage=min_query_term_coverage,
            min_hit_count=min_hit_count,
        )
    except Exception as exc:  # noqa: BLE001 - service boundary must not crash callers on retrieval failures.
        return _abstained_result(
            reason_code=AnswerReasonCode.RETRIEVAL_ERROR,
            run_id=None,
            provider_name=_provider_name(provider),
            top_score=0.0,
            evidence_reason=RetrievalEvidenceReason.RETRIEVAL_ERROR.value,
            error_class=exc.__class__.__name__,
        )

    provider_name = _provider_name(provider)
    if not evidence.is_strong:
        return _abstained_result(
            reason_code=_answer_reason_for_weak_evidence(evidence.reason_code),
            run_id=evidence.run_id,
            provider_name=provider_name,
            top_score=evidence.top_score,
            evidence_reason=evidence.reason_code.value,
        )

    if provider is None:
        return _provider_error_result(
            reason_code=AnswerReasonCode.PROVIDER_CONFIGURATION_ERROR,
            run_id=evidence.run_id,
            provider_name=provider_name,
            trace_id=None,
            top_score=evidence.top_score,
            citation_count=0,
            evidence_reason=evidence.reason_code.value,
            error_class=AnswerConfigurationError.__name__,
        )

    run_id = evidence.run_id or f"answer-{uuid4()}"
    request = AnswerProviderRequest(question=question, run_id=run_id, evidence=evidence.hits)
    try:
        provider_result = provider.answer(request)
    except Exception as exc:  # noqa: BLE001 - sanitize typed and arbitrary provider failures.
        return _provider_error_result(
            reason_code=_provider_exception_reason(exc),
            run_id=evidence.run_id,
            provider_name=provider_name,
            trace_id=None,
            top_score=evidence.top_score,
            citation_count=0,
            evidence_reason=evidence.reason_code.value,
            error_class=exc.__class__.__name__,
        )

    if not isinstance(provider_result, AnswerProviderResult) or not isinstance(provider_result.answer_text, str):
        return _provider_error_result(
            reason_code=AnswerReasonCode.PROVIDER_MALFORMED_RESULT,
            run_id=evidence.run_id,
            provider_name=provider_name,
            trace_id=None,
            top_score=evidence.top_score,
            citation_count=0,
            evidence_reason=evidence.reason_code.value,
            error_class=AnswerValidationError.__name__,
        )

    answer_text = provider_result.answer_text.strip()
    if not answer_text:
        return _provider_error_result(
            reason_code=AnswerReasonCode.PROVIDER_BLANK_ANSWER,
            run_id=evidence.run_id,
            provider_name=provider_result.provider_name or provider_name,
            trace_id=provider_result.trace_id,
            top_score=evidence.top_score,
            citation_count=0,
            evidence_reason=evidence.reason_code.value,
            error_class=AnswerValidationError.__name__,
        )

    citations = _citations_from_hits(evidence.hits[:bounded_top_k])
    return AnswerResult(
        status=AnswerStatus.ANSWERED,
        answer_text=answer_text,
        citations=citations,
        diagnostics=AnswerDiagnostics(
            status=AnswerStatus.ANSWERED,
            reason_code=AnswerReasonCode.ANSWERED,
            run_id=evidence.run_id,
            provider_name=provider_result.provider_name or provider_name,
            trace_id=provider_result.trace_id,
            top_score=evidence.top_score,
            citation_count=len(citations),
            evidence_reason=evidence.reason_code.value,
            error_class=None,
        ),
    )


def _citations_from_hits(hits: tuple[RetrievalHit, ...]) -> tuple[AnswerCitation, ...]:
    return tuple(
        AnswerCitation(
            doc_id=hit.doc_id,
            filename=hit.filename,
            page_num=hit.page_num,
            display_page_num=hit.display_page_num,
            snippet=hit.snippet,
            score=hit.score,
        )
        for hit in hits
    )


def _abstained_result(
    *,
    reason_code: AnswerReasonCode,
    run_id: str | None,
    provider_name: str | None,
    top_score: float,
    evidence_reason: str,
    error_class: str | None = None,
) -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.ABSTAINED,
        answer_text="I don't have enough grounded evidence in the indexed corpus to answer that safely.",
        citations=(),
        diagnostics=AnswerDiagnostics(
            status=AnswerStatus.ABSTAINED,
            reason_code=reason_code,
            run_id=run_id,
            provider_name=provider_name,
            trace_id=None,
            top_score=top_score,
            citation_count=0,
            evidence_reason=evidence_reason,
            error_class=error_class,
        ),
    )


def _provider_error_result(
    *,
    reason_code: AnswerReasonCode,
    run_id: str | None,
    provider_name: str | None,
    trace_id: str | None,
    top_score: float,
    citation_count: int,
    evidence_reason: str,
    error_class: str,
) -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.PROVIDER_ERROR,
        answer_text="I found relevant evidence, but answer generation failed safely. Please retry or inspect diagnostics.",
        citations=(),
        diagnostics=AnswerDiagnostics(
            status=AnswerStatus.PROVIDER_ERROR,
            reason_code=reason_code,
            run_id=run_id,
            provider_name=provider_name,
            trace_id=trace_id,
            top_score=top_score,
            citation_count=citation_count,
            evidence_reason=evidence_reason,
            error_class=error_class,
        ),
    )


def _answer_reason_for_weak_evidence(reason: RetrievalEvidenceReason) -> AnswerReasonCode:
    return _RETRIEVAL_TO_ANSWER_REASON.get(reason, AnswerReasonCode.RETRIEVAL_ERROR)


def _provider_exception_reason(exc: BaseException) -> AnswerReasonCode:
    for exc_type, reason_code in _PROVIDER_ERROR_REASON_BY_EXCEPTION:
        if isinstance(exc, exc_type):
            return reason_code
    return AnswerReasonCode.PROVIDER_EXCEPTION


def _provider_name(provider: AnswerProvider | None) -> str | None:
    if provider is None:
        return _PROVIDERLESS_NAME
    name = getattr(provider, "provider_name", None)
    return name if isinstance(name, str) and name.strip() else provider.__class__.__name__


__all__ = ["answer_question"]
