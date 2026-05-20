"""Streamlit Chat renderer for the public grounded RAG service.

The dashboard layer is intentionally thin: it owns Streamlit rerun/session-state
behavior and display-safe rendering only. Retrieval, citation ownership, provider
validation, and raw-error redaction stay behind the public ``src.rag`` contract.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import Any

import streamlit as st

from src.rag import (
    AnswerCitation,
    AnswerConfigurationError,
    AnswerDiagnostics,
    AnswerReasonCode,
    AnswerResult,
    AnswerStatus,
    build_answer_provider,
)
from src.rag import answer_question as default_answer_question


_CHAT_MESSAGES_KEY = "pfizer_chat_messages"
_CHAT_DIAGNOSTICS_KEY = "pfizer_chat_last_diagnostics"
_DEFAULT_PROVIDER_NAME = "gemini"
_MAX_RENDERED_TEXT_CHARS = 600
_MAX_CITATION_SNIPPET_CHARS = 280
_MAX_DIAGNOSTIC_VALUE_CHARS = 96

AnswerFn = Callable[..., AnswerResult]
ProviderFactory = Callable[[], Any]


_REASON_HINTS: dict[AnswerReasonCode, str] = {
    AnswerReasonCode.EMPTY_QUESTION: "Enter a specific supplier-document question to search the indexed corpus.",
    AnswerReasonCode.INDEX_MISSING: "Build the retrieval index before asking document-grounded questions.",
    AnswerReasonCode.INDEX_EMPTY: "Ingest and index supplier documents before using Chat.",
    AnswerReasonCode.INDEX_STALE: "The retrieval index appears stale; rebuild it from the current document corpus.",
    AnswerReasonCode.NO_MATCH: "No indexed page matched the question strongly enough. Try a supplier, document, or field name from the corpus.",
    AnswerReasonCode.BELOW_THRESHOLD: "The best evidence was below the answer threshold, so the system abstained safely.",
    AnswerReasonCode.RETRIEVAL_ERROR: "Retrieval failed safely. Check the local database/index state and retry.",
    AnswerReasonCode.PROVIDER_CONFIGURATION_ERROR: "Configure the answer provider, then retry this grounded question.",
    AnswerReasonCode.PROVIDER_EXCEPTION: "The answer provider failed safely. Retry after checking provider availability.",
    AnswerReasonCode.PROVIDER_BLANK_ANSWER: "The provider returned no usable answer. Retry or inspect diagnostics.",
    AnswerReasonCode.PROVIDER_MALFORMED_RESULT: "The provider returned an invalid response shape. Retry or inspect diagnostics.",
}


def render_chat_tab(
    db_path: str | None = None,
    provider_factory: ProviderFactory | None = None,
    answer_fn: AnswerFn | None = None,
) -> None:
    """Render the document-grounded Chat tab.

    A new provider is built only after ``st.chat_input`` returns a fresh prompt.
    Prior session-local turns are replayed on every Streamlit rerun without
    calling retrieval or provider code again.
    """

    _initialize_chat_state()
    resolved_db_path = _resolve_db_path(db_path)
    active_answer_fn = answer_fn or default_answer_question

    st.caption("Ask a question about indexed supplier documents. Answers are grounded in cited source pages.")
    for message in st.session_state[_CHAT_MESSAGES_KEY]:
        _render_message(message)

    prompt = st.chat_input("Ask about supplier documents")
    if prompt is None:
        return

    user_text = str(prompt).strip()
    if not user_text:
        return

    user_message = {"role": "user", "content": user_text}
    st.session_state[_CHAT_MESSAGES_KEY].append(user_message)
    _render_message(user_message)

    result = _answer_prompt(
        db_path=resolved_db_path,
        prompt=user_text,
        provider_factory=provider_factory,
        answer_fn=active_answer_fn,
    )
    assistant_message = _assistant_message_from_result(result)
    st.session_state[_CHAT_MESSAGES_KEY].append(assistant_message)
    st.session_state[_CHAT_DIAGNOSTICS_KEY] = _diagnostics_payload(result.diagnostics)
    _render_message(assistant_message)


def _initialize_chat_state() -> None:
    st.session_state.setdefault(_CHAT_MESSAGES_KEY, [])
    st.session_state.setdefault(_CHAT_DIAGNOSTICS_KEY, None)


def _resolve_db_path(db_path: str | None) -> str:
    if db_path:
        return db_path

    from src.config import get_settings

    return get_settings().db_path


def _answer_prompt(
    *,
    db_path: str,
    prompt: str,
    provider_factory: ProviderFactory | None,
    answer_fn: AnswerFn,
) -> AnswerResult:
    try:
        provider = _build_provider(provider_factory)
    except AnswerConfigurationError:
        return _provider_configuration_result()
    except Exception as exc:  # noqa: BLE001 - UI boundary must turn setup failures into safe messages.
        return _provider_configuration_result(error_class=exc.__class__.__name__)

    try:
        return answer_fn(db_path, prompt, provider=provider)
    except AnswerConfigurationError:
        return _provider_configuration_result()
    except Exception as exc:  # noqa: BLE001 - malformed injected/live boundaries must not traceback in Streamlit.
        return _provider_configuration_result(
            reason_code=AnswerReasonCode.PROVIDER_EXCEPTION,
            error_class=exc.__class__.__name__,
        )


def _build_provider(provider_factory: ProviderFactory | None) -> Any:
    if provider_factory is not None:
        return provider_factory()
    return build_answer_provider(_DEFAULT_PROVIDER_NAME)


def _provider_configuration_result(
    *,
    reason_code: AnswerReasonCode = AnswerReasonCode.PROVIDER_CONFIGURATION_ERROR,
    error_class: str = AnswerConfigurationError.__name__,
) -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.PROVIDER_ERROR,
        answer_text="I found the Chat answer provider is not ready. Configure the provider and retry.",
        citations=(),
        diagnostics=AnswerDiagnostics(
            status=AnswerStatus.PROVIDER_ERROR,
            reason_code=reason_code,
            run_id=None,
            provider_name=_DEFAULT_PROVIDER_NAME,
            trace_id=None,
            top_score=0.0,
            citation_count=0,
            evidence_reason="provider_setup_failed",
            error_class=error_class,
        ),
    )


def _assistant_message_from_result(result: AnswerResult) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": _bounded_text(result.answer_text, _MAX_RENDERED_TEXT_CHARS),
        "status": result.status.value,
        "reason_code": result.diagnostics.reason_code.value,
        "citations": [_citation_payload(citation) for citation in result.citations],
        "diagnostics": _diagnostics_payload(result.diagnostics),
    }


def _citation_payload(citation: AnswerCitation) -> dict[str, Any]:
    return {
        "filename": _bounded_text(citation.filename, _MAX_DIAGNOSTIC_VALUE_CHARS),
        "page": citation.display_page_num,
        "snippet": _bounded_text(citation.snippet, _MAX_CITATION_SNIPPET_CHARS),
        "score": round(float(citation.score), 3),
    }


def _diagnostics_payload(diagnostics: AnswerDiagnostics) -> dict[str, Any]:
    return {
        "answer_status": diagnostics.status.value,
        "reason_code": diagnostics.reason_code.value,
        "run_id": _safe_optional_text(diagnostics.run_id),
        "provider_name": _safe_optional_text(diagnostics.provider_name),
        "trace_id": _safe_optional_text(diagnostics.trace_id),
        "top_score": round(float(diagnostics.top_score), 3),
        "citation_count": int(diagnostics.citation_count),
        "evidence_reason": _safe_optional_text(diagnostics.evidence_reason) or "unknown",
        "safe_error_class": _safe_optional_text(diagnostics.error_class),
    }


def _render_message(message: dict[str, Any]) -> None:
    role = str(message.get("role") or "assistant")
    with st.chat_message(role):
        st.markdown(_bounded_text(message.get("content"), _MAX_RENDERED_TEXT_CHARS))
        if role == "assistant":
            _render_assistant_details(message)


def _render_assistant_details(message: dict[str, Any]) -> None:
    status = str(message.get("status") or "")
    reason_code = str(message.get("reason_code") or "")

    if status == AnswerStatus.ANSWERED.value:
        _render_citations(message.get("citations") or [])
    elif status == AnswerStatus.ABSTAINED.value:
        st.info(_hint_for_reason(reason_code))
    elif status == AnswerStatus.PROVIDER_ERROR.value:
        st.error("Answer generation failed safely. Only bounded setup diagnostics are displayed.")
        st.info(_hint_for_reason(reason_code))

    diagnostics = message.get("diagnostics")
    if isinstance(diagnostics, dict):
        _render_diagnostics(diagnostics)


def _render_citations(citations: list[dict[str, Any]]) -> None:
    if not citations:
        return
    st.markdown("**Citations**")
    for citation in citations:
        filename = _bounded_text(citation.get("filename"), _MAX_DIAGNOSTIC_VALUE_CHARS)
        page = citation.get("page")
        snippet = _bounded_text(citation.get("snippet"), _MAX_CITATION_SNIPPET_CHARS)
        score = citation.get("score")
        st.markdown(f"- `{filename}` — Page {page} — score {score}: {snippet}")


def _render_diagnostics(diagnostics: dict[str, Any]) -> None:
    with st.expander("Chat diagnostics", expanded=False):
        st.caption("Bounded operational metadata only; sensitive details and long document content are not rendered.")
        for label, key in (
            ("Answer status", "answer_status"),
            ("Reason code", "reason_code"),
            ("Run ID", "run_id"),
            ("Provider", "provider_name"),
            ("Trace ID", "trace_id"),
            ("Top score", "top_score"),
            ("Citation count", "citation_count"),
            ("Evidence reason", "evidence_reason"),
            ("Safe error class", "safe_error_class"),
        ):
            st.markdown(f"**{label}:** {_diagnostic_display(diagnostics.get(key))}")


def _hint_for_reason(reason_code: str) -> str:
    try:
        reason = AnswerReasonCode(reason_code)
    except ValueError:
        return "The system could not answer safely. Inspect diagnostics and retry."
    return _REASON_HINTS.get(reason, "The system could not answer safely. Inspect diagnostics and retry.")


def _safe_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _bounded_text(value, _MAX_DIAGNOSTIC_VALUE_CHARS).strip()
    return text or None


def _diagnostic_display(value: Any) -> str:
    if value is None:
        return "not available"
    return _bounded_text(value, _MAX_DIAGNOSTIC_VALUE_CHARS)


def _bounded_text(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    if is_dataclass(value):
        value = asdict(value)
    text = str(value).strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}…"


__all__ = ["render_chat_tab"]
