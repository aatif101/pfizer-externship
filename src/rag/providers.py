"""Answer provider protocol and lazy live-provider adapters.

Importing this module is offline-safe. The Gemini adapter initializes SDK clients
only when constructed/called and surfaces typed, sanitized provider errors.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_none

from src.config import get_settings
from src.retrieval.models import RetrievalHit

DEFAULT_GEMINI_ANSWER_MODEL = "gemini-2.5-flash"
_PROVIDER_NAME = "gemini"


class AnswerConfigurationError(RuntimeError):
    """Raised when a live answer provider is not configured safely."""

    reason_code = "provider_configuration_error"


class AnswerProviderError(RuntimeError):
    """Raised when an answer provider call fails at the provider boundary."""

    reason_code = "provider_exception"


class AnswerValidationError(RuntimeError):
    """Raised when untrusted provider output cannot be validated."""

    reason_code = "provider_malformed_result"


@dataclass(frozen=True)
class AnswerProviderRequest:
    """Bounded prompt input passed to answer providers.

    Evidence contains retrieval-owned snippets only; providers never receive raw
    full page text through this service contract.
    """

    question: str
    run_id: str
    evidence: tuple[RetrievalHit, ...]


@dataclass(frozen=True)
class AnswerProviderResult:
    """Provider response shape consumed by the answer service."""

    answer_text: str
    trace_id: str | None = None
    provider_name: str | None = None


class AnswerProvider(Protocol):
    """Minimal protocol for a grounded answer generation provider."""

    provider_name: str

    def answer(self, request: AnswerProviderRequest) -> AnswerProviderResult:
        """Return concise answer text for bounded retrieval evidence."""


@dataclass(frozen=True)
class GeminiAnswerProviderDiagnostics:
    """Non-secret diagnostics for live Gemini answer setup and tests."""

    provider_name: str
    model: str
    max_attempts: int


class GeminiAnswerProvider:
    """Gemini implementation of the answer provider protocol.

    Raw Gemini responses are parsed locally but never exposed in public DTOs or
    exception messages. Tests can inject ``client`` or ``client_factory`` to keep
    this adapter deterministic and offline.
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
        if self._client is None and not self._api_key:
            raise AnswerConfigurationError("GEMINI_API_KEY is required to use the Gemini answer provider.")

    def answer(self, request: AnswerProviderRequest) -> AnswerProviderResult:
        """Call Gemini and parse a minimal structured answer result."""

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

        payload = _parse_json_object(_response_text(response))
        if payload is None:
            raise AnswerValidationError(
                "Gemini answer provider returned malformed structured output "
                f"(provider={self.provider_name}, model={self.model}, run_id={request.run_id})."
            )
        answer_text = payload.get("answer_text", payload.get("answer"))
        if not isinstance(answer_text, str):
            raise AnswerValidationError(
                "Gemini answer provider omitted answer_text "
                f"(provider={self.provider_name}, model={self.model}, run_id={request.run_id})."
            )
        trace_id = payload.get("trace_id") if isinstance(payload.get("trace_id"), str) else _response_trace_id(response)
        return AnswerProviderResult(answer_text=answer_text, trace_id=trace_id, provider_name=self.provider_name)

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
        config = {
            "response_mime_type": "application/json",
            "temperature": 0,
        }
        return client.models.generate_content(model=self.model, contents=contents, config=config)

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
            f"filename=\"{hit.filename}\" page=\"{hit.display_page_num}\" score=\"{hit.score}\">\n"
            f"{hit.snippet}\n</evidence>"
        )
        for idx, hit in enumerate(request.evidence, start=1)
    )
    return f"""You answer Pfizer supplier-document compliance questions.
Return ONLY valid JSON. Do not include markdown.
Use only the evidence snippets below. If the evidence is insufficient, say so in
one concise sentence; do not invent facts.

JSON schema:
{{"answer_text": "concise grounded answer", "trace_id": "optional provider trace id"}}

Run id: {request.run_id}
Question: {request.question}

Evidence snippets:
{evidence_blocks}
"""


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


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_retryable_provider_exception(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status_code, int) and status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    name = exc.__class__.__name__.lower()
    return any(token in name for token in ("timeout", "temporar", "rate", "unavailable"))


__all__ = [
    "AnswerConfigurationError",
    "AnswerProvider",
    "AnswerProviderError",
    "AnswerProviderRequest",
    "AnswerProviderResult",
    "AnswerValidationError",
    "GeminiAnswerProvider",
    "GeminiAnswerProviderDiagnostics",
]
