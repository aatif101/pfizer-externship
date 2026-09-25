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
from src.tracing import observe, safe_update_current_generation

DEFAULT_GEMINI_ANSWER_MODEL = "gemini-2.5-flash"
_PROVIDER_NAME = "gemini"
_MAX_EVIDENCE_CHARS = 2000
_MAX_EVIDENCE_ITEMS = 5
_MAX_REVISION_HINT_CHARS = 1000
_MAX_COMPLETE_TEXT_PROMPT_CHARS = 4000


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
            response = self._generate_traced(contents=_build_contents(request))
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

    def complete_text(self, prompt: str, *, role: str) -> str:
        """Raw-text completion seam for the agentic decomposer/rewriter.

        The prompt is bounded to 4000 chars; errors are sanitized to the
        exception class name. ``role`` is "decompose" or "rewrite".
        """

        bounded = (prompt or "")[:_MAX_COMPLETE_TEXT_PROMPT_CHARS]
        try:
            response = self._generate_aux_traced(contents=bounded, role=role)
        except AnswerConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider boundary sanitizes arbitrary SDK failures.
            raise AnswerProviderError(
                "Gemini auxiliary completion failed "
                f"(provider={self.provider_name}, model={self.model}, error_class={exc.__class__.__name__})."
            ) from exc
        return _strip_simple_fences(_response_text(response)).strip()

    @observe(name="generation.draft", as_type="generation", capture_input=False, capture_output=False)
    def _generate_traced(self, *, contents: str) -> Any:
        response = self._generate_content_with_retry(contents=contents)
        self._report_usage(response)
        return response

    @observe(name="generation.aux", as_type="generation", capture_input=False, capture_output=False)
    def _generate_aux_traced(self, *, contents: str, role: str) -> Any:
        response = self._generate_content_with_retry(contents=contents)
        self._report_usage(response)
        return response

    def _report_usage(self, response: Any) -> None:
        input_tokens, output_tokens = _usage_tokens(response)
        safe_update_current_generation(model=self.model, input_tokens=input_tokens, output_tokens=output_tokens)

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
    revision_block = ""
    if request.revision_hint:
        revision_block = (
            "\n<revision_feedback>\n"
            f"{request.revision_hint.strip()[:_MAX_REVISION_HINT_CHARS]}\n"
            "</revision_feedback>\n"
            "Revise the answer so every claim is supported by the evidence; "
            "if the evidence is insufficient, say so.\n"
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
{revision_block}"""


def _bounded_evidence(evidence: str) -> str:
    stripped = evidence.strip()
    if len(stripped) <= _MAX_EVIDENCE_CHARS:
        return stripped
    return stripped[: _MAX_EVIDENCE_CHARS - 1].rstrip() + "…"


def _usage_tokens(response: Any) -> tuple[int | None, int | None]:
    """Return (input, output) token counts from Gemini usage_metadata, or None each."""

    usage = getattr(response, "usage_metadata", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage_metadata")
    if usage is None:
        return None, None

    def _read(name: str) -> int | None:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    return _read("prompt_token_count"), _read("candidates_token_count")


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
