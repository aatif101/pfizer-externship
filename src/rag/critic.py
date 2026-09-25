"""Faithfulness critic contracts for the agentic RAG graph.

Importing this module is credential-free and imports no LLM SDK. Live critic
adapters (Claude Sonnet, opt-in Gemini) arrive in plan 06-04 and implement
``CriticProvider``. Every critic failure is typed with ``reason_code =
"critic_error"`` so the graph can fail closed (D-02): a draft the critic did
not accept is never returned as an answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.retrieval.models import RetrievalHit


class CriticConfigurationError(RuntimeError):
    """Raised when no critic can be configured safely (e.g. missing key)."""

    reason_code = "critic_error"


class CriticProviderError(RuntimeError):
    """Raised when a critic call fails at the provider boundary."""

    reason_code = "critic_error"


class CriticValidationError(RuntimeError):
    """Raised when untrusted critic output cannot be validated."""

    reason_code = "critic_error"


class CriticVerdict(BaseModel):
    """Structured faithfulness verdict for one draft answer."""

    model_config = ConfigDict(extra="ignore")

    verdict: Literal["supported", "partially_supported", "unsupported"]
    faithfulness: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=5)


@dataclass(frozen=True)
class CriticRequest:
    """Bounded critic input: the question, the draft, and retrieval evidence."""

    question: str
    draft: str
    evidence: tuple[RetrievalHit, ...]
    run_id: str


class CriticProvider(Protocol):
    """Minimal protocol for a faithfulness critic."""

    provider_name: str

    def critique(self, request: CriticRequest) -> CriticVerdict:
        """Return a verdict on whether the draft is supported by the evidence."""


def _strip_simple_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    return re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*|\s*```$", "", stripped).strip()


def parse_critic_verdict(text: str) -> CriticVerdict:
    """Parse raw critic JSON (optionally ``` fenced) into a ``CriticVerdict``.

    Any validation failure raises ``CriticValidationError`` so callers fail closed.
    """

    try:
        return CriticVerdict.model_validate_json(_strip_simple_fences(text))
    except (ValidationError, ValueError) as exc:
        raise CriticValidationError("critic verdict failed validation") from exc


__all__ = [
    "CriticConfigurationError",
    "CriticProvider",
    "CriticProviderError",
    "CriticRequest",
    "CriticValidationError",
    "CriticVerdict",
    "parse_critic_verdict",
]
