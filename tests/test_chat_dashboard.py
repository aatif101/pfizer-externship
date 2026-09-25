"""Tests for the Streamlit Chat renderer rerun boundary."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
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
    def __init__(
        self,
        prompts: list[str | None] | None = None,
        toggle_values: list[bool] | None = None,
    ) -> None:
        self.session_state: dict[str, Any] = {}
        self.toggle_values = list(toggle_values or [])
        self.toggle_calls: list[dict[str, Any]] = []
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

    def toggle(self, label: str, *, value: bool = False, key: str | None = None, help: str | None = None) -> bool:
        self.toggle_calls.append({"label": label, "value": value, "key": key, "help": help})
        if self.toggle_values:
            return self.toggle_values.pop(0)
        return value

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
    pipeline: str = "linear",
    retrieval_rounds: int = 0,
    regeneration_count: int = 0,
    sub_query_count: int = 0,
    critic_verdict: str | None = None,
    critic_score: float | None = None,
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
        pipeline=pipeline,
        retrieval_rounds=retrieval_rounds,
        regeneration_count=regeneration_count,
        sub_query_count=sub_query_count,
        critic_verdict=critic_verdict,
        critic_score=critic_score,
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


@pytest.fixture(autouse=True)
def trace_spy(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Record trace_session / flush_traces calls; never touch real Langfuse."""
    record: dict[str, list[Any]] = {"sessions": [], "flushes": []}

    @contextmanager
    def fake_trace_session(**kwargs: Any) -> Iterator[None]:
        record["sessions"].append(kwargs)
        yield

    def fake_flush() -> bool:
        record["flushes"].append(True)
        return True

    monkeypatch.setattr("src.dashboard.chat.trace_session", fake_trace_session)
    monkeypatch.setattr("src.dashboard.chat.flush_traces", fake_flush)
    return record


@pytest.fixture
def pipeline_env(monkeypatch: pytest.MonkeyPatch):
    """Set RAG_PIPELINE and reset the cached Settings around the test."""
    from src.config import get_settings

    def _set(value: str) -> None:
        monkeypatch.setenv("RAG_PIPELINE", value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def _answer_spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    calls: dict[str, list[str]] = {"agentic": [], "linear": []}

    def agentic(db_path: str, question: str, *, provider: Any, **_kwargs: Any) -> AnswerResult:
        calls["agentic"].append(question)
        return _answered_result()

    def linear(db_path: str, question: str, *, provider: Any, **_kwargs: Any) -> AnswerResult:
        calls["linear"].append(question)
        return _answered_result()

    monkeypatch.setattr("src.rag.agentic.answer_question_agentic", agentic)
    monkeypatch.setattr("src.dashboard.chat.default_answer_question", linear)
    return calls


def test_default_pipeline_is_agentic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pipeline_env) -> None:
    pipeline_env("agentic")
    calls = _answer_spies(monkeypatch)
    fake_st = FakeStreamlit(prompts=["What is the expiry date?"], toggle_values=[True])
    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider)

    assert calls == {"agentic": ["What is the expiry date?"], "linear": []}
    assert fake_st.toggle_calls[0]["value"] is True
    assert fake_st.toggle_calls[0]["key"] == "pfizer_chat_agentic"


def test_toggle_switches_to_linear(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pipeline_env) -> None:
    pipeline_env("agentic")
    calls = _answer_spies(monkeypatch)
    fake_st = FakeStreamlit(prompts=["What is the expiry date?"], toggle_values=[False])
    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider)

    assert calls == {"agentic": [], "linear": ["What is the expiry date?"]}


def test_settings_linear_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pipeline_env) -> None:
    pipeline_env("linear")
    calls = _answer_spies(monkeypatch)
    fake_st = FakeStreamlit(prompts=["What is the expiry date?"])
    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider)

    assert fake_st.toggle_calls[0]["value"] is False
    assert calls == {"agentic": [], "linear": ["What is the expiry date?"]}


def test_injected_answer_fn_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pipeline_env) -> None:
    pipeline_env("agentic")
    calls = _answer_spies(monkeypatch)
    injected: list[str] = []

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        injected.append(question)
        return _answered_result()

    for toggle_value in (True, False):
        fake_st = FakeStreamlit(prompts=["Q?"], toggle_values=[toggle_value])
        monkeypatch.setattr("src.dashboard.chat.st", fake_st)
        render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider, answer_fn=answer_fn)

    assert injected == ["Q?", "Q?"]
    assert calls == {"agentic": [], "linear": []}


def test_submit_opens_trace_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pipeline_env, trace_spy: dict[str, list[Any]]
) -> None:
    pipeline_env("agentic")
    _answer_spies(monkeypatch)
    fake_st = FakeStreamlit(prompts=["First?", "Second?"], toggle_values=[True, False])
    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider)
    render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider)

    sessions = trace_spy["sessions"]
    assert [s["phase"] for s in sessions] == ["phase2", "phase1"]
    assert all("chat" in tuple(s["tags"]) for s in sessions)
    session_ids = {s["session_id"] for s in sessions}
    assert len(session_ids) == 1
    (session_id,) = session_ids
    assert isinstance(session_id, str) and session_id
    assert fake_st.session_state["pfizer_chat_session_id"] == session_id
    assert len(trace_spy["flushes"]) == 2


def test_submit_flushes_traces_even_when_answer_fn_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, trace_spy: dict[str, list[Any]]
) -> None:
    fake_st = FakeStreamlit(prompts=["Q?"])
    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        raise RuntimeError("SECRET_RAW_ERROR")

    render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider, answer_fn=answer_fn)

    assert len(trace_spy["flushes"]) == 1
    assert "**Safe error class:** RuntimeError" in fake_st.all_rendered_text()
    assert "SECRET_RAW_ERROR" not in fake_st.all_rendered_text()


def test_new_reason_hints() -> None:
    from src.dashboard.chat import _hint_for_reason

    generic = _hint_for_reason("definitely-not-a-reason")
    hints = {
        code: _hint_for_reason(code) for code in ("retrieval_exhausted", "critic_rejected", "critic_error")
    }
    for code, hint in hints.items():
        assert hint != generic, code
    assert len(set(hints.values())) == 3
    assert "ANTHROPIC_API_KEY" in hints["critic_error"]
    assert "CRITIC_PROVIDER=gemini" in hints["critic_error"]


def test_agentic_diagnostics_rendered_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.dashboard.chat import _diagnostics_payload

    payload = _diagnostics_payload(
        _diagnostics(
            status=AnswerStatus.ANSWERED,
            reason_code=AnswerReasonCode.ANSWERED,
            pipeline="agentic",
            retrieval_rounds=2,
            regeneration_count=1,
            sub_query_count=2,
            critic_verdict="supported",
            critic_score=0.91234,
        )
    )
    assert payload["pipeline"] == "agentic"
    assert payload["retrieval_rounds"] == 2
    assert payload["regeneration_count"] == 1
    assert payload["sub_query_count"] == 2
    assert payload["critic_verdict"] == "supported"
    assert payload["critic_score"] == 0.912

    none_payload = _diagnostics_payload(
        _diagnostics(
            status=AnswerStatus.ABSTAINED,
            reason_code=AnswerReasonCode.CRITIC_ERROR,
            pipeline="agentic",
            critic_verdict=None,
            critic_score=None,
        )
    )
    assert none_payload["critic_verdict"] is None
    assert none_payload["critic_score"] is None

    # Rendered end to end: labels present, None rendered safely.
    result = AnswerResult(
        status=AnswerStatus.ABSTAINED,
        answer_text="Abstained.",
        citations=(),
        diagnostics=_diagnostics(
            status=AnswerStatus.ABSTAINED,
            reason_code=AnswerReasonCode.CRITIC_ERROR,
            pipeline="agentic",
            retrieval_rounds=1,
            sub_query_count=2,
        ),
    )
    fake_st = FakeStreamlit(prompts=["Q?"])
    monkeypatch.setattr("src.dashboard.chat.st", fake_st)
    render_chat_tab(str(tmp_path / "chat.db"), provider_factory=FakeProvider, answer_fn=lambda *a, **k: result)
    rendered = fake_st.all_rendered_text()
    assert "**Pipeline:** agentic" in rendered
    assert "**Retrieval rounds:** 1" in rendered
    assert "**Regenerations:** 0" in rendered
    assert "**Sub-queries:** 2" in rendered
    assert "**Critic verdict:** not available" in rendered
    assert "**Critic score:** not available" in rendered
    assert "ANTHROPIC_API_KEY" in rendered


def test_answered_question_persists_turns_and_renders_service_owned_citation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = str(tmp_path / "chat.db")
    fake_st = FakeStreamlit(prompts=["Does Acme have Pfizer supplier approval?"])
    calls: list[tuple[str, str, Any]] = []

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        calls.append((db_path, question, provider))
        return _answered_result()

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(db_path, provider_factory=FakeProvider, answer_fn=answer_fn)

    rendered = fake_st.all_rendered_text()
    assert len(fake_st.session_state["pfizer_chat_messages"]) == 2
    assert calls == [(db_path, "Does Acme have Pfizer supplier approval?", calls[0][2])]
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


def test_unrelated_question_abstains_with_no_citations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = str(tmp_path / "chat.db")
    fake_st = FakeStreamlit(prompts=["Who won the astronomy prize?"])
    calls: list[str] = []

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        calls.append(question)
        return _abstained_result()

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(db_path, provider_factory=FakeProvider, answer_fn=answer_fn)

    rendered = fake_st.all_rendered_text()
    assert calls == ["Who won the astronomy prize?"]
    assert "I don't have enough grounded evidence" in rendered
    assert "No indexed page matched the question strongly enough" in rendered
    assert "**Reason code:** no_match" in rendered
    assert "**Citation count:** 0" in rendered
    assert "**Citations**" not in rendered
    assert "Page 1" not in rendered
    assert "acme-sdf.pdf" not in rendered


def test_provider_setup_error_is_safe_and_does_not_leak_raw_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = str(tmp_path / "chat.db")
    secret = "GEMINI_API_KEY=super-secret RAW_PROVIDER_PAYLOAD full_page_tail fullhash_abcdef1234567890"
    fake_st = FakeStreamlit(prompts=["Does Acme have approval?"])

    def provider_factory() -> FakeProvider:
        raise AnswerConfigurationError(secret)

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:  # pragma: no cover - must not run
        raise AssertionError("answer_fn should not be called when provider setup fails")

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(db_path, provider_factory=provider_factory, answer_fn=answer_fn)

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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = str(tmp_path / "chat.db")
    secret = "RAW_EXCEPTION_AND_PROVIDER_PAYLOAD_SHOULD_NOT_RENDER"
    fake_st = FakeStreamlit(prompts=["Does Acme have approval?", None])
    calls: list[str] = []

    def answer_fn(db_path: str, question: str, *, provider: Any) -> AnswerResult:
        calls.append(question)
        return _provider_error_result(secret)

    monkeypatch.setattr("src.dashboard.chat.st", fake_st)

    render_chat_tab(db_path, provider_factory=FakeProvider, answer_fn=answer_fn)
    first_rendered = fake_st.all_rendered_text()
    render_chat_tab(db_path, provider_factory=FakeProvider, answer_fn=answer_fn)
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
