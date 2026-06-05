"""Provider protocol and DTOs for offline SDF extraction orchestration.

This module intentionally has no live Gemini/Claude dependency. Production VLM
adapters can implement ``SDFExtractionProvider`` later; tests use a fake provider
that returns these typed payloads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

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
class ProviderUsageMetadata:
    """Bounded provider usage metadata safe to persist for observability.

    This DTO intentionally contains only numeric token/cost telemetry and model
    identity. It must not grow prompt text, page text, provider payloads, images,
    PDFs, secrets, or local file paths.
    """

    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class ProviderExtractionResult:
    """Provider response shape consumed by the extraction pipeline."""

    fields: tuple[ProviderFieldPayload, ...]
    trace_id: str | None = None
    provider_name: str | None = None
    provider_model: str | None = None
    usage_metadata: ProviderUsageMetadata | None = None


VisualFallbackReasonCode = Literal[
    "field_abstained",
    "field_needs_review",
    "no_eligible_fields",
    "missing_page_images",
    "not_configured",
]
VisualFallbackStatus = Literal["ready", "skipped", "complete", "abstained", "error"]


@dataclass(frozen=True)
class VisualFallbackRequest:
    """Bounded visual fallback request for targeted image-based extraction.

    ``eligible_field_names`` and ``reason_codes`` are the only field-level
    context needed by visual providers. ``pages`` must contain selected
    ``DocumentPage`` objects whose ``image_blob`` is populated; callers should
    not include raw page text in prompts, local paths, PDFs, secrets, or previous
    provider payloads when adapting this request to a live API.
    """

    eligible_field_names: tuple[SDFFieldName, ...]
    pages: tuple[DocumentPage, ...]
    reason_codes: dict[SDFFieldName, VisualFallbackReasonCode]


@dataclass(frozen=True)
class VisualFallbackRequestPlan:
    """Decision made before a visual provider can be invoked.

    A skipped plan carries only a bounded reason code. A ready plan carries the
    sanitized request object; no raw values, spans, page text, image bytes, paths,
    provider payloads, prompts, or secrets should be persisted from this object.
    """

    status: VisualFallbackStatus
    reason_code: VisualFallbackReasonCode | None = None
    request: VisualFallbackRequest | None = None


@dataclass(frozen=True)
class VisualFallbackProviderResult:
    """Visual fallback invocation outcome safe for orchestration tests."""

    plan: VisualFallbackRequestPlan
    provider_result: ProviderExtractionResult | None = None


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


class SDFVisualFallbackProvider(Protocol):
    """Optional provider protocol for targeted image-based fallback extraction."""

    def extract_visual_fields(
        self,
        *,
        document: DocumentMetadata,
        request: VisualFallbackRequest,
        run_id: str,
    ) -> ProviderExtractionResult:
        """Return candidate fields for the request's eligible field allowlist."""
