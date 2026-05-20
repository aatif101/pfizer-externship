"""Provider protocol and DTOs for offline SDF extraction orchestration.

This module intentionally has no live Gemini/Claude dependency. Production VLM
adapters can implement ``SDFExtractionProvider`` later; tests use a fake provider
that returns these typed payloads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from src.db.queries import DocumentMetadata, DocumentPage
from src.extraction.models import SDFFieldName


class ExtractionConfigurationError(RuntimeError):
    """Raised when a live extraction provider is not configured safely."""

    reason_code = "extraction_configuration_error"


class ExtractionProviderError(RuntimeError):
    """Raised when a provider call fails after bounded retry/handling."""

    reason_code = "extraction_provider_error"


class ExtractionValidationError(RuntimeError):
    """Raised when untrusted provider output cannot be validated."""

    reason_code = "extraction_validation_error"


@dataclass(frozen=True)
class ProviderSourceEvidence:
    """Provider-cited source evidence for one extracted field."""

    page_num: int
    verbatim_span: str | None = None
    bbox: dict[str, Any] | list[Any] | None = None


@dataclass(frozen=True)
class ProviderFieldPayload:
    """Provider output for a single candidate SDF field."""

    field_name: SDFFieldName | str
    raw_value: str | None = None
    normalized_value: str | int | float | bool | None = None
    normalized_date: date | str | None = None
    confidence: float = 0.0
    evidence: ProviderSourceEvidence | None = None
    abstention_reason: str | None = None


@dataclass(frozen=True)
class ProviderExtractionResult:
    """Provider response shape consumed by the extraction pipeline."""

    fields: tuple[ProviderFieldPayload, ...]
    trace_id: str | None = None
    provider_name: str | None = None


class SDFExtractionProvider(Protocol):
    """Minimal protocol for an SDF field-extraction provider."""

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        """Return candidate six-field SDF extractions for an ingested document."""
