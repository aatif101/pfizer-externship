"""Offline tests for the live faithfulness critic adapters (plan 06-04, RAG-03).

Every test injects a fake client: no network, no Anthropic/Gemini SDK call.
The builder tests prove the fail-closed D-02 contract: a missing Anthropic key
raises even when a Gemini key is available (no silent fallback).
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.config import get_settings
from src.rag.critic import (
    AnthropicCritic,
    CriticConfigurationError,
    CriticProviderError,
    CriticRequest,
    CriticValidationError,
    GeminiCritic,
    build_critic_provider,
    build_critic_prompt,
)
from src.retrieval.models import RetrievalHit, RetrievalScoreComponents

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SUPPORTED_JSON = '```json\n{"verdict":"supported","faithfulness":0.92,"unsupported_claims":[]}\n```'


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeUsage:
    input_tokens: int = 120
    output_tokens: int = 30


@dataclass
class FakeAnthropicResponse:
    content: list[Any]
    usage: Any = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeAnthropicClient:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = FakeMessages(responses)


@dataclass
class FakeGeminiResponse:
    text: str
    usage_metadata: Any = None


class FakeGeminiModels:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeGeminiClient:
    def __init__(self, responses: list[Any]) -> None:
        self.models = FakeGeminiModels(responses)


class RetryableProviderError(RuntimeError):
    status_code = 503


class NonRetryableProviderError(RuntimeError):
    status_code = 400


def _anthropic_text(text: str) -> FakeAnthropicResponse:
    return FakeAnthropicResponse(content=[FakeTextBlock(text=text)])


def _hit(index: int, text: str = "Expiry Date: 2027-01-31") -> RetrievalHit:
    return RetrievalHit(
        doc_id=f"doc-{index}",
        filename=f"doc-{index}.pdf",
        page_num=index,
        display_page_num=index + 1,
        score=0.9,
        score_components=RetrievalScoreComponents(),
        snippet="short teaser",
        evidence_text=text,
    )


def _request(hits: tuple[RetrievalHit, ...] | None = None) -> CriticRequest:
    return CriticRequest(
        question="When does lot 42 expire?",
        draft="Lot 42 expires on 2027-01-31.",
        evidence=hits if hits is not None else (_hit(0),),
        run_id="run-critic-001",
    )


# ---------------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------------


def test_offline_import_does_not_load_anthropic_sdk() -> None:
    env = {k: v for k, v in os.environ.items() if k not in {"ANTHROPIC_API_KEY", "GEMINI_API_KEY"}}
    code = "import sys; import src.rag.critic; print('anthropic' in sys.modules)"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert completed.stdout.strip().splitlines()[-1] == "False"


# ---------------------------------------------------------------------------
# AnthropicCritic
# ---------------------------------------------------------------------------


def test_anthropic_missing_key_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(CriticConfigurationError) as exc_info:
        AnthropicCritic(api_key="")

    assert exc_info.value.reason_code == "critic_error"
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_anthropic_critique_parses_verdict_and_sends_no_sampling_kwargs() -> None:
    client = FakeAnthropicClient([_anthropic_text(_SUPPORTED_JSON)])
    critic = AnthropicCritic(api_key="test-key", client=client)

    result = critic.critique(_request())

    assert result.verdict == "supported"
    assert result.faithfulness == pytest.approx(0.92)
    assert result.unsupported_claims == []
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["model"] == "claude-sonnet-4-6"
    assert call["max_tokens"] == 512
    assert isinstance(call["system"], str) and call["system"]
    assert len(call["messages"]) == 1
    assert call["messages"][0]["role"] == "user"
    for forbidden in ("temperature", "top_p", "top_k"):
        assert forbidden not in call


def test_anthropic_joins_only_text_blocks() -> None:
    blocks = [
        FakeTextBlock(text="ignored", type="thinking"),
        FakeTextBlock(text='{"verdict":"unsupported",'),
        FakeTextBlock(text='"faithfulness":0.1,"unsupported_claims":["x"]}'),
    ]
    client = FakeAnthropicClient([FakeAnthropicResponse(content=blocks)])
    critic = AnthropicCritic(api_key="test-key", client=client)

    result = critic.critique(_request())

    assert result.verdict == "unsupported"
    assert result.unsupported_claims == ["x"]


def test_anthropic_prompt_bounds_evidence_and_tags_inputs() -> None:
    long_text = "Supplier evidence. " + ("filler " * 500) + " TAIL_BEYOND_CAP"
    hits = tuple(_hit(i, long_text) for i in range(7))
    client = FakeAnthropicClient([_anthropic_text(_SUPPORTED_JSON)])
    critic = AnthropicCritic(api_key="test-key", client=client)

    critic.critique(_request(hits))

    content = client.messages.calls[0]["messages"][0]["content"]
    assert content.count("<evidence ") == 5
    assert "TAIL_BEYOND_CAP" not in content
    assert "<question>" in content and "When does lot 42 expire?" in content
    assert "<draft>" in content and "Lot 42 expires on 2027-01-31." in content
    assert 'doc_id="doc-0"' in content and 'page="1"' in content
    assert 'doc_id="doc-5"' not in content
    # Each evidence block is bounded to 2000 chars.
    for block in content.split("<evidence ")[1:]:
        body = block.split(">", 1)[1].split("</evidence>", 1)[0]
        assert len(body.strip()) <= 2000


def test_build_critic_prompt_falls_back_to_snippet() -> None:
    hit = RetrievalHit(
        doc_id="doc-x",
        filename="doc-x.pdf",
        page_num=0,
        display_page_num=1,
        score=0.8,
        score_components=RetrievalScoreComponents(),
        snippet="SNIPPET_FALLBACK_TEXT",
        evidence_text="",
    )
    prompt = build_critic_prompt(_request((hit,)))
    assert "SNIPPET_FALLBACK_TEXT" in prompt


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"verdict":"maybe","faithfulness":0.5,"unsupported_claims":[]}',
        '{"verdict":"supported","faithfulness":1.5,"unsupported_claims":[]}',
    ],
)
def test_anthropic_malformed_output_raises_validation_error(raw: str) -> None:
    client = FakeAnthropicClient([_anthropic_text(raw)])
    critic = AnthropicCritic(api_key="test-key", client=client)

    with pytest.raises(CriticValidationError) as exc_info:
        critic.critique(_request())

    assert exc_info.value.reason_code == "critic_error"


def test_anthropic_retry_then_success() -> None:
    client = FakeAnthropicClient([RetryableProviderError("503 upstream"), _anthropic_text(_SUPPORTED_JSON)])
    critic = AnthropicCritic(api_key="test-key", client=client, max_attempts=2)

    result = critic.critique(_request())

    assert result.verdict == "supported"
    assert len(client.messages.calls) == 2


def test_anthropic_nonretryable_error_is_sanitized_and_not_retried() -> None:
    raw = "RAW_PROVIDER_DETAIL secret-key-leak"
    client = FakeAnthropicClient([NonRetryableProviderError(raw)])
    critic = AnthropicCritic(api_key="sk-ant-secret", client=client, max_attempts=3)

    with pytest.raises(CriticProviderError) as exc_info:
        critic.critique(_request())

    assert len(client.messages.calls) == 1
    message = str(exc_info.value)
    assert "error_class=NonRetryableProviderError" in message
    assert "RAW_PROVIDER_DETAIL" not in message
    assert "sk-ant-secret" not in message
    assert "Expiry Date" not in message


def test_anthropic_reports_generation_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.rag.critic as critic_module

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(critic_module, "safe_update_current_generation", lambda **kw: calls.append(kw) or True)
    client = FakeAnthropicClient([_anthropic_text(_SUPPORTED_JSON)])

    AnthropicCritic(api_key="test-key", client=client).critique(_request())

    assert calls == [{"model": "claude-sonnet-4-6", "input_tokens": 120, "output_tokens": 30}]


def test_anthropic_sdk_import_failure_is_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original_import = builtins.__import__

    def blocked(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "anthropic" or name.startswith("anthropic."):
            raise ImportError("raw anthropic import failure")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    critic = AnthropicCritic(api_key="test-key", max_attempts=1)

    with pytest.raises(CriticConfigurationError) as exc_info:
        critic.critique(_request())

    assert "raw anthropic import failure" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# GeminiCritic (explicit opt-in only)
# ---------------------------------------------------------------------------


def test_gemini_critic_parses_with_temperature_zero() -> None:
    client = FakeGeminiClient([FakeGeminiResponse(text=_SUPPORTED_JSON)])
    critic = GeminiCritic(api_key="gem-key", client=client)

    result = critic.critique(_request())

    assert critic.provider_name == "gemini"
    assert result.verdict == "supported"
    call = client.models.calls[0]
    assert call["config"] == {"temperature": 0}
    assert "<draft>" in call["contents"]


def test_gemini_critic_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(CriticConfigurationError):
        GeminiCritic(api_key="")


# ---------------------------------------------------------------------------
# build_critic_provider (D-02: no silent fallback)
# ---------------------------------------------------------------------------


def test_build_critic_provider_anthropic_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRITIC_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

    critic = build_critic_provider()

    assert isinstance(critic, AnthropicCritic)
    assert critic.provider_name == "anthropic"


def test_build_critic_provider_missing_anthropic_key_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRITIC_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key-is-available")

    with pytest.raises(CriticConfigurationError):
        build_critic_provider()


def test_build_critic_provider_gemini_is_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRITIC_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    critic = build_critic_provider()

    assert isinstance(critic, GeminiCritic)


def test_build_critic_provider_unknown_name_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRITIC_PROVIDER", "other")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

    with pytest.raises(CriticConfigurationError):
        build_critic_provider()
