"""Tests for the Streamlit Chat renderer rerun boundary."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import pytest

from src.rag import (
    AnswerCitation,
    AnswerConfigurationError,
    AnswerDiagnostics,
    AnswerReasonCode,
    AnswerResult,
    AnswerStatus,
)
from src.dashboard.chat import render_chat_tab


@dataclass
class FakeProvider:
    provider_name: str = "fake-provider"


class FakeContext(AbstractContextManager["FakeContext"]):
    def __init__(self, fake_st: "FakeStreamlit", kind: str, label: str) -> None:
        self.fake_st = fake_st
        self.kind = kind
        self.label = label

    def __enter__(self) -> "FakeContext":
        self.fake_st.context_stack.append((self.kind, self.label))
        self.fake_st.context_entries.append((self.kind, self.label))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.fake_st.context_stack.pop()


class FakeStreamlit:
    def __init__(self, prompts: list[str | None] | None = None) -> None:
        self.session_state: dict[str, Any] = {}
        self.prompts = list(prompts or [])
        self.context_stack: list[tuple[str, str]] = []
        self.context_entries: list[tuple[str, str]] = []
        self.markdown_messages: list[str] = []
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.error_messages: list[str] = []
        self.caption_messages: list[str] = []
        self.chat_inputs: list[str] = []
        self.expanders: list[tuple[str, bool]] = []

    def chat_message(self, role: str) -> FakeContext:
        return FakeContext(self, "chat_message", role)

    def expander(self, label: str, *, expanded: bool = False) -> FakeContext:
        self.expanders.append((label, expanded))
        return FakeContext(self, "expander", label)

    def chat_input(self, placeholder: str) -> str | None:
        self.chat_inputs.append(placeholder)
        if not self.prompts:
            return None
        return self.prompts.pop(0)

    def markdown(self, message: str) -> None:
        self.markdown_messages.append(message)

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def caption(self, message: str) -> None:
        self.caption_messages.append(message)

    def all_rendered_text(self) -> str:
        parts = [
            *self.markdown_messages,
            *self.info_messages,
            *self.warning_messages,
            *self.error_messages,
            *self.caption_messages,
        ]
        return "\n".join(parts)


def _diagnostics(
    *,
    status: AnswerStatus,
    reason_code: AnswerReasonCode,
    run_id: str | None = "run-chat-001",
    provider_name: str | None = "fake-provider",
    trace_id: str | None = "trace-chat-001",
    top_score: float = 0.87,
    citation_count: int = 1,
    evidence_reason: str = "strong_evidence",
    error_class: str | None = None,
) -> AnswerDiagnostics:
    return AnswerDiagnostics(
        status=status,
        reason_code=reason_code,
        run_id=run_id,
        provider_name=provider_name,
        trace_id=trace_id,
        top_score=top_score,
        citation_count=citation_count,
        evidence_reason=evidence_reason,
        error_class=error_class,
    )


def _answered_result() -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.ANSWERED,
        answer_text="Acme Pharma has supplier compliance approval evidence in the cited document.",
        citations=(
            AnswerCitation(
                doc_id="doc-acme",
                filename="acme-sdf.pdf",
                page_num=0,
                display_page_num=1,
                snippet="Supplier Declaration Form for Acme Pharma with Pfizer compliance approval.",
                score=0.87321,
            ),
        ),
        diagnostics=_diagnostics(status=AnswerStatus.ANSWERED, reason_code=AnswerReasonCode.ANSWERED),
    )


def _abstained_result() -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.ABSTAINED,
        answer_text="I don't have enough grounded evidence in the indexed corpus to answer that safely.",
        citations=(),
        diagnostics=_diagnostics(
            status=AnswerStatus.ABSTAINED,
            reason_code=AnswerReasonCode.NO_MATCH,
            trace_id=None,
            top_score=0.0,
            citation_count=0,
            evidence_reason="no_match",
        ),
    )


def _provider_error_result(secret: str) -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.PROVIDER_ERROR,
        answer_text="I found relevant evidence, but answer generation failed safely. Please retry or inspect diagnostics.",
        citations=(),
        diagnostics=_diagnostics(
            status=AnswerStatus.PROVIDER_ERROR,
            reason_code=AnswerReasonCode.PROVIDER_EXCEPTION,
            trace_id=None,
            citation_count=0,
            error_class="RuntimeError",
            evidence_reason="strong_evidence",
        ),
    )


def test_answered_question_persists_turns_and_renders_service_owned_citation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = FakeStreamlit(prompts=["Does Acme have Pfizer supplier approval?"])
    calls: list[tuple[str, str, Any]] = []

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        calls.append((db_path, question, provider))
        return _answered_result()

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab("chat.db", provider_factory=FakeProvider, answer_fn=answer_fn)

    rendered = fake_st.all_rendered_text()
    assert len(fake_st.session_state["pfizer_chat_messages"]) == 2
    assert calls == [("chat.db", "Does Acme have Pfizer supplier approval?", calls[0][2])]
    assert isinstance(calls[0][2], FakeProvider)
    assert "Does Acme have Pfizer supplier approval?" in rendered
    assert "Acme Pharma has supplier compliance approval" in rendered
    assert "acme-sdf.pdf" in rendered
    assert "Page 1" in rendered
    assert "Supplier Declaration Form for Acme Pharma" in rendered
    assert "score 0.873" in rendered
    assert "**Answer status:** answered" in rendered
    assert "**Reason code:** answered" in rendered
    assert "**Run ID:** run-chat-001" in rendered
    assert "**Provider:** fake-provider" in rendered
    assert "**Trace ID:** trace-chat-001" in rendered
    assert "**Top score:** 0.87" in rendered
    assert "**Citation count:** 1" in rendered
    assert "**Evidence reason:** strong_evidence" in rendered


def test_unrelated_question_abstains_with_no_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = FakeStreamlit(prompts=["Who won the astronomy prize?"])
    calls: list[str] = []

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        calls.append(question)
        return _abstained_result()

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab("chat.db", provider_factory=FakeProvider, answer_fn=answer_fn)

    rendered = fake_st.all_rendered_text()
    assert calls == ["Who won the astronomy prize?"]
    assert "I don't have enough grounded evidence" in rendered
    assert "No indexed page matched the question strongly enough" in rendered
    assert "**Reason code:** no_match" in rendered
    assert "**Citation count:** 0" in rendered
    assert "**Citations**" not in rendered
    assert "Page 1" not in rendered
    assert "acme-sdf.pdf" not in rendered


def test_provider_setup_error_is_safe_and_does_not_leak_raw_details(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "GEMINI_API_KEY=super-secret RAW_PROVIDER_PAYLOAD full_page_tail fullhash_abcdef1234567890"
    fake_st = FakeStreamlit(prompts=["Does Acme have approval?"])

    def provider_factory() -> FakeProvider:
        raise AnswerConfigurationError(secret)

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:  # pragma: no cover - must not run
        raise AssertionError("answer_fn should not be called when provider setup fails")

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab("chat.db", provider_factory=provider_factory, answer_fn=answer_fn)

    rendered = fake_st.all_rendered_text()
    assert "Chat answer provider is not ready" in rendered
    assert "Answer generation failed safely" in rendered
    assert "Configure the answer provider" in rendered
    assert "**Answer status:** provider_error" in rendered
    assert "**Reason code:** provider_configuration_error" in rendered
    assert "**Provider:** gemini" in rendered
    assert "**Safe error class:** AnswerConfigurationError" in rendered
    assert "GEMINI_API_KEY" not in rendered
    assert "super-secret" not in rendered
    assert "RAW_PROVIDER_PAYLOAD" not in rendered
    assert "full_page_tail" not in rendered
    assert "fullhash_abcdef1234567890" not in rendered


def test_provider_error_result_is_bounded_and_rerun_without_prompt_does_not_call_answer_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "RAW_EXCEPTION_AND_PROVIDER_PAYLOAD_SHOULD_NOT_RENDER"
    fake_st = FakeStreamlit(prompts=["Does Acme have approval?", None])
    calls: list[str] = []

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        calls.append(question)
        return _provider_error_result(secret)

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab("chat.db", provider_factory=FakeProvider, answer_fn=answer_fn)
    first_rendered = fake_st.all_rendered_text()
    render_chat_tab("chat.db", provider_factory=FakeProvider, answer_fn=answer_fn)
    second_rendered = fake_st.all_rendered_text()

    assert calls == ["Does Acme have approval?"]
    assert len(fake_st.session_state["pfizer_chat_messages"]) == 2
    assert fake_st.context_entries.count(("chat_message", "user")) == 2
    assert fake_st.context_entries.count(("chat_message", "assistant")) == 2
    assert "I found relevant evidence, but answer generation failed safely" in first_rendered
    assert "**Safe error class:** RuntimeError" in second_rendered
    assert secret not in second_rendered
    assert "raw provider" not in second_rendered.lower()
    assert "full page text" not in second_rendered.lower()
