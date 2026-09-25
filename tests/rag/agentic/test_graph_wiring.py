"""Offline wiring tests for the live agentic graph (plan 06-04).

Covers critic resolution from settings (fail closed, D-02), settings-driven
critic threshold, Langfuse CallbackHandler wiring, decomposer/rewriter seams
from the answer provider, and the agentic trace-metadata allowlist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

import src.rag.agentic.graph as graph_module
from src.config import get_settings
from src.rag.agentic import answer_question_agentic
from src.rag.models import AnswerReasonCode, AnswerStatus

from tests.rag.agentic.conftest import (
    FakeAnswerProvider,
    FakeCritic,
    FakeRetrieve,
    make_hit,
    strong_result,
    verdict,
)

_QUESTION = "QUESTION_SENTINEL when does lot 42 expire?"
_DRAFT = "DRAFT_SENTINEL lot 42 expires 2027-01-31"
_EVIDENCE = "EVIDENCE_SENTINEL Expiry Date: 2027-01-31"


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    get_settings.cache_clear()
    # Keep tracing offline regardless of any local .env.
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    yield
    get_settings.cache_clear()


class _InvokeSpy:
    """Wraps build_agentic_graph to capture deps and the invoke config."""

    def __init__(self) -> None:
        self.deps: list[Any] = []
        self.configs: list[dict[str, Any]] = []
        self._real = graph_module.build_agentic_graph

    def __call__(self, deps: Any) -> Any:
        self.deps.append(deps)
        compiled = self._real(deps)
        spy = self

        class _Wrapped:
            def invoke(self, state: Any, config: dict[str, Any]) -> Any:
                spy.configs.append(dict(config))
                safe = {k: v for k, v in config.items() if k != "callbacks"}
                return compiled.invoke(state, safe)

        return _Wrapped()


@pytest.fixture
def invoke_spy(monkeypatch: pytest.MonkeyPatch) -> _InvokeSpy:
    spy = _InvokeSpy()
    monkeypatch.setattr(graph_module, "build_agentic_graph", spy)
    return spy


@dataclass
class _ProviderWithCompleteText(FakeAnswerProvider):
    completions: list[tuple[str, str]] = field(default_factory=list)

    def complete_text(self, prompt: str, *, role: str) -> str:
        self.completions.append((prompt, role))
        return f"{role}:{prompt}"


def test_critic_resolved_from_settings_fail_closed(monkeypatch: pytest.MonkeyPatch, db_path: str) -> None:
    monkeypatch.setenv("CRITIC_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key-present-but-never-used-as-critic")
    provider = FakeAnswerProvider()

    result = answer_question_agentic(
        db_path, _QUESTION, provider=provider, retrieve_fn=FakeRetrieve(results=[strong_result()])
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.CRITIC_ERROR
    assert result.diagnostics.error_class == "CriticConfigurationError"
    assert provider.calls == []


def test_critic_resolved_from_settings_when_configured(
    monkeypatch: pytest.MonkeyPatch, db_path: str, invoke_spy: _InvokeSpy
) -> None:
    from src.rag.critic import AnthropicCritic

    monkeypatch.setenv("CRITIC_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

    answer_question_agentic(db_path, "", provider=FakeAnswerProvider(), retrieve_fn=FakeRetrieve(results=[strong_result()]))

    assert isinstance(invoke_spy.deps[0].critic, AnthropicCritic)
    assert invoke_spy.deps[0].critic_error_class is None


def test_critic_min_faithfulness_from_settings(monkeypatch: pytest.MonkeyPatch, db_path: str) -> None:
    monkeypatch.setenv("CRITIC_MIN_FAITHFULNESS", "0.95")
    provider = FakeAnswerProvider(answers=["first", "second"])
    critic = FakeCritic(verdicts=[verdict("supported", 0.9)])

    result = answer_question_agentic(
        db_path, _QUESTION, provider=provider, critic=critic, retrieve_fn=FakeRetrieve(results=[strong_result()])
    )

    assert result.status is AnswerStatus.ABSTAINED
    assert result.diagnostics.reason_code is AnswerReasonCode.CRITIC_REJECTED
    assert result.diagnostics.regeneration_count == 1
    assert len(provider.calls) == 2
    assert provider.calls[1].revision_hint


def test_explicit_threshold_overrides_settings(monkeypatch: pytest.MonkeyPatch, db_path: str) -> None:
    monkeypatch.setenv("CRITIC_MIN_FAITHFULNESS", "0.95")
    critic = FakeCritic(verdicts=[verdict("supported", 0.9)])

    result = answer_question_agentic(
        db_path,
        _QUESTION,
        provider=FakeAnswerProvider(),
        critic=critic,
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
        critic_min_faithfulness=0.85,
    )

    assert result.status is AnswerStatus.ANSWERED


def test_callback_handler_passed_when_enabled(
    monkeypatch: pytest.MonkeyPatch, db_path: str, invoke_spy: _InvokeSpy
) -> None:
    sentinel = object()
    monkeypatch.setattr(graph_module, "build_callback_handler", lambda: sentinel)

    result = answer_question_agentic(
        db_path, _QUESTION, provider=FakeAnswerProvider(), critic=FakeCritic(), retrieve_fn=FakeRetrieve(results=[strong_result()])
    )

    assert result.status is AnswerStatus.ANSWERED
    config = invoke_spy.configs[0]
    assert config["callbacks"] == [sentinel]
    assert config["recursion_limit"] == 30


def test_callback_handler_omitted_when_disabled(
    monkeypatch: pytest.MonkeyPatch, db_path: str, invoke_spy: _InvokeSpy
) -> None:
    monkeypatch.setattr(graph_module, "build_callback_handler", lambda: None)

    answer_question_agentic(
        db_path, _QUESTION, provider=FakeAnswerProvider(), critic=FakeCritic(), retrieve_fn=FakeRetrieve(results=[strong_result()])
    )

    config = invoke_spy.configs[0]
    assert "callbacks" not in config
    assert config["recursion_limit"] == 30


def test_decomposer_rewriter_wired_from_provider(db_path: str, invoke_spy: _InvokeSpy) -> None:
    provider = _ProviderWithCompleteText()

    answer_question_agentic(
        db_path, _QUESTION, provider=provider, critic=FakeCritic(), retrieve_fn=FakeRetrieve(results=[strong_result()])
    )

    deps = invoke_spy.deps[0]
    assert callable(deps.decomposer) and callable(deps.rewriter)
    assert deps.decomposer("p1") == "decompose:p1"
    assert deps.rewriter("p2") == "rewrite:p2"
    assert ("p1", "decompose") in provider.completions
    assert ("p2", "rewrite") in provider.completions


def test_decomposer_rewriter_stay_none_without_complete_text(db_path: str, invoke_spy: _InvokeSpy) -> None:
    answer_question_agentic(
        db_path, _QUESTION, provider=FakeAnswerProvider(), critic=FakeCritic(), retrieve_fn=FakeRetrieve(results=[strong_result()])
    )

    deps = invoke_spy.deps[0]
    assert deps.decomposer is None
    assert deps.rewriter is None


def test_injected_decomposer_is_not_overridden(db_path: str, invoke_spy: _InvokeSpy) -> None:
    def mine(prompt: str) -> str:
        return prompt

    answer_question_agentic(
        db_path,
        _QUESTION,
        provider=_ProviderWithCompleteText(),
        critic=FakeCritic(),
        retrieve_fn=FakeRetrieve(results=[strong_result()]),
        decomposer=mine,
    )

    assert invoke_spy.deps[0].decomposer is mine


class _FakeLangfuseContext:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update_current_trace(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


def test_agentic_trace_metadata_allowlist(monkeypatch: pytest.MonkeyPatch, db_path: str) -> None:
    fake_context = _FakeLangfuseContext()
    monkeypatch.setattr(graph_module, "_LANGFUSE_AVAILABLE", True)
    monkeypatch.setattr(graph_module, "langfuse_context", fake_context)
    hits = (make_hit("doc-a", 0, 0.9, _EVIDENCE),)

    result = answer_question_agentic(
        db_path,
        _QUESTION,
        provider=FakeAnswerProvider(answers=[_DRAFT]),
        critic=FakeCritic(verdicts=[verdict("supported", 0.95)]),
        retrieve_fn=FakeRetrieve(results=[strong_result(hits)]),
    )

    assert result.status is AnswerStatus.ANSWERED
    assert fake_context.updates, "expected an agentic trace update"
    update = fake_context.updates[-1]
    assert "rag" in update["tags"]
    assert "agentic" in update["tags"]
    metadata = update["metadata"]
    assert set(metadata) <= graph_module._AGENTIC_TRACE_ALLOWED_KEYS
    assert metadata["boundary"] == "rag.agentic"
    assert metadata["pipeline"] == "agentic"
    assert metadata["critic_verdict"] == "supported"
    recorded = repr(fake_context.updates)
    for sentinel in ("QUESTION_SENTINEL", "DRAFT_SENTINEL", "EVIDENCE_SENTINEL"):
        assert sentinel not in recorded


def test_agentic_trace_metadata_skipped_when_unavailable(monkeypatch: pytest.MonkeyPatch, db_path: str) -> None:
    fake_context = _FakeLangfuseContext()
    monkeypatch.setattr(graph_module, "_LANGFUSE_AVAILABLE", False)
    monkeypatch.setattr(graph_module, "langfuse_context", fake_context)

    answer_question_agentic(
        db_path, _QUESTION, provider=FakeAnswerProvider(), critic=FakeCritic(), retrieve_fn=FakeRetrieve(results=[strong_result()])
    )

    assert fake_context.updates == []


def test_allowlist_excludes_content_keys() -> None:
    for key in ("question", "draft", "evidence_text", "snippet", "critic_feedback", "unsupported_claims"):
        assert key not in graph_module._AGENTIC_TRACE_ALLOWED_KEYS
