"""Answer provider protocol and offline-safe provider builder seam.

Importing this module is credential-free. Live providers are imported lazily by
``build_answer_provider`` so tests and default app startup can inject fake
providers without importing optional SDK adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.retrieval.models import RetrievalHit


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


def build_answer_provider(provider: str | AnswerProvider | None = None, **kwargs: object) -> AnswerProvider | None:
    """Build a live answer provider by name without making imports eager.

    ``None`` and blank names return ``None`` so callers can keep fake providers
    easy to inject. Currently supported live provider: ``gemini``.
    """

    if provider is None:
        return None
    if not isinstance(provider, str):
        return provider

    provider_name = provider.strip().lower()
    if not provider_name:
        return None
    if provider_name == "gemini":
        from src.rag.gemini import GeminiAnswerProvider

        return GeminiAnswerProvider(**kwargs)
    raise AnswerConfigurationError(f"Unsupported answer provider: {provider_name}")


__all__ = [
    "AnswerConfigurationError",
    "AnswerProvider",
    "AnswerProviderError",
    "AnswerProviderRequest",
    "AnswerProviderResult",
    "AnswerValidationError",
    "build_answer_provider",
]
