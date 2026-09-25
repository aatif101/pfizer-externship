"""Streamlit Chat renderer for the public grounded RAG service.

The dashboard layer is intentionally thin: it owns Streamlit rerun/session-state
behavior and display-safe rendering only. Retrieval, citation ownership, provider
validation, and raw-error redaction stay behind the public ``src.rag`` contract.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import uuid4

import streamlit as st

from src.config import get_settings
from src.dashboard.ui import render_tab_header
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
from src.tracing import PHASE_TAGS, flush_traces, trace_session


_CHAT_MESSAGES_KEY = "pfizer_chat_messages"
_CHAT_DIAGNOSTICS_KEY = "pfizer_chat_last_diagnostics"
_CHAT_AGENTIC_TOGGLE_KEY = "pfizer_chat_agentic"
_CHAT_SESSION_ID_KEY = "pfizer_chat_session_id"
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
    AnswerReasonCode.RETRIEVAL_EXHAUSTED: (
        "The agent re-searched the corpus (up to 2 retries) but could not find strong evidence for every part "
        "of the question, so it abstained. Try naming the supplier, document, or field."
    ),
    AnswerReasonCode.CRITIC_REJECTED: (
        "A draft answer was produced but the faithfulness critic could not verify it against the cited evidence "
        "(after one regeneration), so the system abstained rather than risk a hallucination."
    ),
    AnswerReasonCode.CRITIC_ERROR: (
        "The faithfulness critic is unavailable, so answers cannot be verified and the system abstained. "
        "Set ANTHROPIC_API_KEY, or opt in to the Gemini critic with CRITIC_PROVIDER=gemini."
    ),
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

    render_tab_header(
        "Chat",
        "Ask grounded questions over the indexed supplier corpus. Answers cite source pages.",
    )
    st.caption("Tips: mention a vendor, document type, or field name to improve retrieval.")

    # D-03: agentic is the Chat default (Settings.rag_pipeline); the toggle switches this
    # browser session back to the Phase 1 linear baseline. An injected answer_fn still wins.
    agentic_enabled = st.toggle(
        "Agentic pipeline (decompose, re-retrieve, self-critique)",
        value=_settings_default_is_agentic(),
        key=_CHAT_AGENTIC_TOGGLE_KEY,
        help="Off = Phase 1 linear baseline",
    )
    pipeline = "agentic" if agentic_enabled else "linear"
    active_answer_fn = answer_fn or _default_answer_fn(pipeline)

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
        pipeline=pipeline,
        session_id=st.session_state.get(_CHAT_SESSION_ID_KEY),
    )
    assistant_message = _assistant_message_from_result(result)
    st.session_state[_CHAT_MESSAGES_KEY].append(assistant_message)
    st.session_state[_CHAT_DIAGNOSTICS_KEY] = _diagnostics_payload(result.diagnostics)
    _render_message(assistant_message)


def _initialize_chat_state() -> None:
    st.session_state.setdefault(_CHAT_MESSAGES_KEY, [])
    st.session_state.setdefault(_CHAT_DIAGNOSTICS_KEY, None)
    # Random per-browser-session id for Langfuse session grouping (T-06-36): not a user identifier.
    if not st.session_state.get(_CHAT_SESSION_ID_KEY):
        st.session_state[_CHAT_SESSION_ID_KEY] = str(uuid4())


def _settings_default_is_agentic() -> bool:
    try:
        return str(get_settings().rag_pipeline).strip().lower() == "agentic"
    except Exception:  # noqa: BLE001 - a settings failure must not break the Chat tab render.
        return True


def _default_answer_fn(pipeline: str) -> AnswerFn:
    """Return the service answer function for ``pipeline``.

    The agentic graph is imported lazily so the linear path never loads langgraph.
    """
    if pipeline == "agentic":
        from src.rag.agentic import answer_question_agentic

        return answer_question_agentic
    return default_answer_question


def _resolve_db_path(db_path: str | None) -> str:
    if db_path:
        return db_path

    return get_settings().db_path


def _answer_prompt(
    *,
    db_path: str,
    prompt: str,
    provider_factory: ProviderFactory | None,
    answer_fn: AnswerFn,
    pipeline: str = "linear",
    session_id: str | None = None,
) -> AnswerResult:
    try:
        provider = _build_provider(provider_factory)
    except AnswerConfigurationError:
        return _provider_configuration_result()
    except Exception as exc:  # noqa: BLE001 - UI boundary must turn setup failures into safe messages.
        return _provider_configuration_result(error_class=exc.__class__.__name__)

    try:
        with trace_session(phase=PHASE_TAGS.get(pipeline, "phase1"), session_id=session_id, tags=("chat",)):
            return answer_fn(db_path, prompt, provider=provider)
    except AnswerConfigurationError:
        return _provider_configuration_result()
    except Exception as exc:  # noqa: BLE001 - malformed injected/live boundaries must not traceback in Streamlit.
        return _provider_configuration_result(
            reason_code=AnswerReasonCode.PROVIDER_EXCEPTION,
            error_class=exc.__class__.__name__,
        )
    finally:
        flush_traces()


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
        # Agentic diagnostics: bounded numeric/enum values only. Critic feedback and
        # unsupported claims are never rendered (T-06-35).
        "pipeline": _safe_optional_text(getattr(diagnostics, "pipeline", None)),
        "retrieval_rounds": _safe_int(getattr(diagnostics, "retrieval_rounds", 0)),
        "regeneration_count": _safe_int(getattr(diagnostics, "regeneration_count", 0)),
        "sub_query_count": _safe_int(getattr(diagnostics, "sub_query_count", 0)),
        "critic_verdict": _safe_optional_text(getattr(diagnostics, "critic_verdict", None)),
        "critic_score": _safe_score(getattr(diagnostics, "critic_score", None)),
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


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
            ("Pipeline", "pipeline"),
            ("Retrieval rounds", "retrieval_rounds"),
            ("Regenerations", "regeneration_count"),
            ("Sub-queries", "sub_query_count"),
            ("Critic verdict", "critic_verdict"),
            ("Critic score", "critic_score"),
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
