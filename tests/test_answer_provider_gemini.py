"""Offline Gemini answer-provider tests using injected fake clients."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest


def test_importing_rag_and_gemini_provider_is_offline_safe_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    import src.rag
    import src.rag.gemini

    assert src.rag.GeminiAnswerProvider.provider_name == "gemini"
    assert src.rag.gemini.GeminiAnswerProvider.provider_name == "gemini"


def test_missing_gemini_api_key_raises_typed_configuration_error() -> None:
    from src.rag.gemini import GeminiAnswerProvider
    from src.rag.providers import AnswerConfigurationError

    with pytest.raises(AnswerConfigurationError) as exc_info:
        GeminiAnswerProvider(api_key="")

    assert exc_info.value.reason_code == "provider_configuration_error"
    assert "GEMINI_API_KEY" in str(exc_info.value)


@dataclass
class FakeGeminiResponse:
    text: str
    response_id: str = "gemini-answer-trace-001"


class FakeGeminiModels:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeGeminiClient:
    def __init__(self, responses: list[Any]) -> None:
        self.models = FakeGeminiModels(responses)


class RetryableProviderError(RuntimeError):
    status_code = 503


class NonRetryableProviderError(RuntimeError):
    status_code = 400


def _request(
    *,
    snippet: str = "Acme Pharma Ltd. expiry date is 2027-01-31.",
    evidence_text: str = "",
) -> Any:
    from src.rag.providers import AnswerProviderRequest
    from src.retrieval.models import RetrievalHit, RetrievalScoreComponents

    return AnswerProviderRequest(
        question="What is Acme's expiry date?",
        run_id="run-answer-001",
        evidence=(
            RetrievalHit(
                doc_id="doc-acme",
                filename="acme-sdf.pdf",
                page_num=0,
                display_page_num=1,
                score=0.91,
                score_components=RetrievalScoreComponents(lexical_score=0.91),
                snippet=snippet,
                evidence_text=evidence_text,
            ),
        ),
    )


def test_fake_client_success_returns_plain_text_and_trace_id_without_network() -> None:
    from src.rag.gemini import GeminiAnswerProvider

    client = FakeGeminiClient([FakeGeminiResponse("```\nThe expiry date is 2027-01-31.\n```")])
    provider = GeminiAnswerProvider(api_key="test-key", client=client, max_attempts=1)

    result = provider.answer(_request())

    assert result.answer_text == "The expiry date is 2027-01-31."
    assert result.provider_name == "gemini"
    assert result.trace_id == "gemini-answer-trace-001"
    call = client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["config"] == {"temperature": 0}
    assert "Use only the supplied evidence snippets" in call["contents"]
    assert "Acme Pharma Ltd." in call["contents"]


def test_client_factory_is_lazy_and_allowed_without_api_key() -> None:
    from src.rag.gemini import GeminiAnswerProvider

    made_with: list[str] = []

    def factory(api_key: str) -> FakeGeminiClient:
        made_with.append(api_key)
        return FakeGeminiClient([FakeGeminiResponse("Factory-backed answer.", response_id="trace-factory")])

    provider = GeminiAnswerProvider(api_key="", client_factory=factory, max_attempts=1)

    assert made_with == []
    result = provider.answer(_request())

    assert made_with == [""]
    assert result.answer_text == "Factory-backed answer."
    assert result.trace_id == "trace-factory"


def test_retryable_transient_failure_retries_then_succeeds() -> None:
    from src.rag.gemini import GeminiAnswerProvider

    client = FakeGeminiClient([
        RetryableProviderError("503 raw provider details that should not escape"),
        FakeGeminiResponse("Recovered answer.", response_id="trace-recovered"),
    ])
    provider = GeminiAnswerProvider(api_key="test-key", client=client, max_attempts=2)

    result = provider.answer(_request())

    assert result.answer_text == "Recovered answer."
    assert result.trace_id == "trace-recovered"
    assert len(client.models.calls) == 2


def test_nonretryable_failure_is_sanitized_and_not_retried() -> None:
    from src.rag.gemini import GeminiAnswerProvider
    from src.rag.providers import AnswerProviderError

    secret_key = "secret-gemini-key"
    raw_response = "RAW_PROVIDER_RESPONSE_SHOULD_NOT_APPEAR"
    snippet = "FULL_SNIPPET_SHOULD_NOT_APPEAR " * 20
    client = FakeGeminiClient([NonRetryableProviderError(raw_response)])
    provider = GeminiAnswerProvider(api_key=secret_key, client=client, max_attempts=3)

    with pytest.raises(AnswerProviderError) as exc_info:
        provider.answer(_request(snippet=snippet))

    assert len(client.models.calls) == 1
    message = str(exc_info.value)
    assert exc_info.value.reason_code == "provider_exception"
    assert "NonRetryableProviderError" in message
    assert "provider=gemini" in message
    assert "run-answer-001" in message
    assert secret_key not in message
    assert raw_response not in message
    assert "FULL_SNIPPET_SHOULD_NOT_APPEAR" not in message


def test_retry_exhaustion_is_bounded_and_sanitized() -> None:
    from src.rag.gemini import GeminiAnswerProvider
    from src.rag.providers import AnswerProviderError

    raw_response = "temporarily unavailable with raw internals"
    client = FakeGeminiClient([
        RetryableProviderError(raw_response),
        RetryableProviderError(raw_response),
    ])
    provider = GeminiAnswerProvider(api_key="test-key", client=client, max_attempts=2)

    with pytest.raises(AnswerProviderError) as exc_info:
        provider.answer(_request())

    assert len(client.models.calls) == 2
    message = str(exc_info.value)
    assert "RetryableProviderError" in message
    assert raw_response not in message


def test_blank_response_raises_typed_validation_error_without_raw_response() -> None:
    from src.rag.gemini import GeminiAnswerProvider
    from src.rag.providers import AnswerValidationError

    client = FakeGeminiClient([FakeGeminiResponse("   ")])
    provider = GeminiAnswerProvider(api_key="test-key", client=client, max_attempts=1)

    with pytest.raises(AnswerValidationError) as exc_info:
        provider.answer(_request())

    assert exc_info.value.reason_code == "provider_malformed_result"
    assert "blank answer" in str(exc_info.value)
    assert "Acme Pharma Ltd." not in str(exc_info.value)


def test_prompt_bounds_evidence_text_before_provider_call() -> None:
    from src.rag.gemini import _MAX_EVIDENCE_CHARS, GeminiAnswerProvider

    long_secret_tail = " SECRET_TAIL_SHOULD_NOT_BE_SENT"
    # Evidence text well over the 2000-char cap; the tail sits beyond the cap.
    long_evidence = "Supplier compliance evidence. " + ("filler " * 400) + long_secret_tail
    assert len(long_evidence) > _MAX_EVIDENCE_CHARS
    client = FakeGeminiClient([FakeGeminiResponse("Bounded answer.")])
    provider = GeminiAnswerProvider(api_key="test-key", client=client, max_attempts=1)

    provider.answer(_request(snippet="short teaser", evidence_text=long_evidence))

    contents = client.models.calls[0]["contents"]
    assert "Supplier compliance evidence." in contents
    assert long_secret_tail not in contents
    assert len(contents) < len(long_evidence) + 600


def test_prompt_embeds_evidence_text_not_short_snippet() -> None:
    from src.rag.gemini import GeminiAnswerProvider

    client = FakeGeminiClient([FakeGeminiResponse("Grounded answer.")])
    provider = GeminiAnswerProvider(api_key="test-key", client=client, max_attempts=1)

    provider.answer(
        _request(
            snippet="SHORT_TEASER_ONLY",
            evidence_text="WIDE_EVIDENCE_BODY with full grounding sentences the judge must also see.",
        )
    )

    contents = client.models.calls[0]["contents"]
    # The wide evidence_text is what the generator sees, not the short teaser.
    assert "WIDE_EVIDENCE_BODY with full grounding sentences" in contents
    assert "SHORT_TEASER_ONLY" not in contents


def test_prompt_falls_back_to_snippet_when_evidence_text_empty() -> None:
    from src.rag.gemini import GeminiAnswerProvider

    client = FakeGeminiClient([FakeGeminiResponse("Fallback answer.")])
    provider = GeminiAnswerProvider(api_key="test-key", client=client, max_attempts=1)

    provider.answer(_request(snippet="FALLBACK_SNIPPET_TEXT", evidence_text=""))

    contents = client.models.calls[0]["contents"]
    assert "FALLBACK_SNIPPET_TEXT" in contents


def test_build_answer_provider_lazily_exposes_gemini_and_preserves_injected_providers() -> None:
    from src.rag.providers import AnswerProviderResult, build_answer_provider

    class InjectedProvider:
        provider_name = "fake"

        def answer(self, request: Any) -> AnswerProviderResult:
            return AnswerProviderResult("fake answer", provider_name=self.provider_name)

    injected = InjectedProvider()
    built = build_answer_provider("gemini", api_key="test-key", client=FakeGeminiClient([FakeGeminiResponse("ok")]))

    assert build_answer_provider(None) is None
    assert build_answer_provider(injected) is injected
    assert getattr(built, "provider_name") == "gemini"


def test_optional_google_genai_import_failure_is_sanitized_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    from src.rag.gemini import GeminiAnswerProvider
    from src.rag.providers import AnswerConfigurationError

    original_import = builtins.__import__

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "google" or name.startswith("google."):
            raise ImportError("raw google import failure details")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    provider = GeminiAnswerProvider(api_key="test-key", max_attempts=1)

    with pytest.raises(AnswerConfigurationError) as exc_info:
        provider.answer(_request())

    assert "google-genai" in str(exc_info.value)
    assert "raw google import failure details" not in str(exc_info.value)
