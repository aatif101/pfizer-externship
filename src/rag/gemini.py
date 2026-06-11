"""Lazy Gemini answer provider for grounded RAG responses.

Importing this module is offline-safe: credentials, optional SDK imports, and
network clients are resolved only when ``GeminiAnswerProvider`` is constructed or
called. The provider receives bounded retrieval snippets from the answer service
and surfaces only sanitized, typed errors.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_none

from src.config import get_settings
from src.rag.providers import (
    AnswerConfigurationError,
    AnswerProviderError,
    AnswerProviderRequest,
    AnswerProviderResult,
    AnswerValidationError,
)

DEFAULT_GEMINI_ANSWER_MODEL = "gemini-2.5-flash"
_PROVIDER_NAME = "gemini"
_MAX_EVIDENCE_CHARS = 2000
_MAX_EVIDENCE_ITEMS = 5


@dataclass(frozen=True)
class GeminiAnswerProviderDiagnostics:
    """Non-secret diagnostics for live Gemini answer setup and tests."""

    provider_name: str
    model: str
    max_attempts: int


class GeminiAnswerProvider:
    """Gemini implementation of the answer provider protocol.

    Tests can inject ``client`` or ``client_factory`` to keep this adapter fully
    deterministic and offline. Exception messages intentionally contain only
    provider/model/run/error-class metadata, never API keys, raw responses, or
    full evidence snippets.
    """

    provider_name = _PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
        max_attempts: int = 2,
    ) -> None:
        settings = get_settings()
        self.model = (model or settings.gemini_model or DEFAULT_GEMINI_ANSWER_MODEL).strip()
        self.max_attempts = max(1, int(max_attempts))
        self._client = client
        self._client_factory = client_factory
        self._api_key = (api_key if api_key is not None else settings.gemini_api_key).strip()
        self.diagnostics = GeminiAnswerProviderDiagnostics(
            provider_name=self.provider_name,
            model=self.model,
            max_attempts=self.max_attempts,
        )

        if self._client is None and self._client_factory is None and not self._api_key:
            raise AnswerConfigurationError("GEMINI_API_KEY is required to use the Gemini answer provider.")

    def answer(self, request: AnswerProviderRequest) -> AnswerProviderResult:
        """Call Gemini and return stripped plain answer text plus trace metadata."""

        try:
            response = self._generate_content_with_retry(contents=_build_contents(request))
        except AnswerConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider boundary sanitizes arbitrary SDK failures.
            raise AnswerProviderError(
                "Gemini answer provider failed after bounded retry "
                f"(provider={self.provider_name}, model={self.model}, run_id={request.run_id}, "
                f"error_class={exc.__class__.__name__})."
            ) from exc

        answer_text = _strip_simple_fences(_response_text(response)).strip()
        if not answer_text:
            raise AnswerValidationError(
                "Gemini answer provider returned a blank answer "
                f"(provider={self.provider_name}, model={self.model}, run_id={request.run_id})."
            )

        return AnswerProviderResult(
            answer_text=answer_text,
            trace_id=_response_trace_id(response),
            provider_name=self.provider_name,
        )

    def _generate_content_with_retry(self, *, contents: str) -> Any:
        retrying = Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_none(),
            retry=retry_if_exception(_is_retryable_provider_exception),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return self._generate_content(contents=contents)
        raise AssertionError("unreachable tenacity retry state")

    def _generate_content(self, *, contents: str) -> Any:
        client = self._get_client()
        return client.models.generate_content(model=self.model, contents=contents, config={"temperature": 0})

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory(self._api_key)
            return self._client
        try:
            from google import genai  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001 - optional dependency boundary.
            raise AnswerConfigurationError("google-genai is installed/configured incorrectly for Gemini answers.") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client


def _build_contents(request: AnswerProviderRequest) -> str:
    evidence_blocks = "\n\n".join(
        (
            f"<evidence index=\"{idx}\" doc_id=\"{hit.doc_id}\" "
            f"filename=\"{hit.filename}\" page=\"{hit.display_page_num}\" score=\"{hit.score:.4f}\">\n"
            f"{_bounded_evidence(hit.evidence_text or hit.snippet)}\n</evidence>"
        )
        for idx, hit in enumerate(request.evidence[:_MAX_EVIDENCE_ITEMS], start=1)
    )
    return f"""You answer Pfizer supplier-document compliance questions.
Use only the supplied evidence snippets. Answer concisely in plain text.
If the evidence does not support the answer, say that the supplied evidence is
insufficient. Do not invent facts, do not cite uncited documents, and do not
include markdown fences.

Run id: {request.run_id}
Question: {request.question}

Evidence snippets:
{evidence_blocks}
"""


def _bounded_evidence(evidence: str) -> str:
    stripped = evidence.strip()
    if len(stripped) <= _MAX_EVIDENCE_CHARS:
        return stripped
    return stripped[: _MAX_EVIDENCE_CHARS - 1].rstrip() + "…"


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    text = getattr(response, "text", None)
    return text if isinstance(text, str) else ""


def _response_trace_id(response: Any) -> str | None:
    for attr in ("trace_id", "response_id", "id"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _strip_simple_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    return re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*|\s*```$", "", stripped).strip()


def _is_retryable_provider_exception(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status_code, int) and status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    return any(token in name for token in ("timeout", "temporar", "rate", "unavailable")) or any(
        token in message for token in ("429", "500", "502", "503", "504", "timeout", "temporarily unavailable")
    )


__all__ = [
    "DEFAULT_GEMINI_ANSWER_MODEL",
    "GeminiAnswerProvider",
    "GeminiAnswerProviderDiagnostics",
]
