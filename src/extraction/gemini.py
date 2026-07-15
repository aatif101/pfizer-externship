"""Gemini-backed SDF extraction provider.

The adapter is intentionally lazy and offline-safe: importing this module never
requires credentials, network access, or the ``google-genai`` package to be
initialized. Live calls are made only from ``extract_fields`` and return the same
provider DTOs consumed by the extraction pipeline. Provider output is untrusted;
raw responses and page text are not logged or surfaced in exceptions.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from time import sleep
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_random_exponential

from src.config import get_settings
from src.db.queries import DocumentMetadata, DocumentPage
from src.extraction.models import SDFFieldName
from src.extraction.providers import (
    ExtractionConfigurationError,
    ExtractionProviderError,
    ProviderExtractionResult,
    ProviderFieldPayload,
    ProviderSourceEvidence,
    ProviderUsageMetadata,
    VisualFallbackRequest,
)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
MALFORMED_OUTPUT_REASON = "Provider returned malformed structured output."
_PROVIDER_NAME = "gemini"
_MAX_PROVIDER_TEXT_LENGTH = 500
_MAX_ABSTENTION_REASON_LENGTH = 240
_MAX_BBOX_COORDINATE = 1_000_000.0
_MAX_MODEL_IDENTIFIER_LENGTH = 128
_MODEL_IDENTIFIER_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._:/"
)

_BoundedProviderString = Annotated[str, Field(max_length=_MAX_PROVIDER_TEXT_LENGTH)]
_FiniteNormalizedFloat = Annotated[float, Field(allow_inf_nan=False)]


class _GeminiBBox(BaseModel):
    """Strict, finite, size-bounded provider bounding box."""

    model_config = ConfigDict(extra="forbid", strict=True)

    x: float = Field(ge=-_MAX_BBOX_COORDINATE, le=_MAX_BBOX_COORDINATE, allow_inf_nan=False)
    y: float = Field(ge=-_MAX_BBOX_COORDINATE, le=_MAX_BBOX_COORDINATE, allow_inf_nan=False)
    width: float = Field(ge=0.0, le=_MAX_BBOX_COORDINATE, allow_inf_nan=False)
    height: float = Field(ge=0.0, le=_MAX_BBOX_COORDINATE, allow_inf_nan=False)


class _GeminiEvidence(BaseModel):
    """Untrusted provider evidence after structural validation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    page_num: int = Field(ge=0)
    verbatim_span: str = Field(min_length=1, max_length=_MAX_PROVIDER_TEXT_LENGTH)
    bbox: _GeminiBBox | None = None

    @field_validator("verbatim_span")
    @classmethod
    def verbatim_span_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("verbatim_span must not be blank")
        return value


class _GeminiField(BaseModel):
    """One fixed-key provider field before adaptation to domain-neutral DTOs."""

    model_config = ConfigDict(extra="forbid", strict=True)

    raw_value: _BoundedProviderString | None
    normalized_value: _BoundedProviderString | int | _FiniteNormalizedFloat | bool | None
    normalized_date: date | None
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    evidence: _GeminiEvidence | None
    abstention_reason: str | None = Field(default=None, max_length=_MAX_ABSTENTION_REASON_LENGTH)

    @field_validator("normalized_date", mode="before")
    @classmethod
    def parse_exact_iso_date(cls, value: Any) -> Any:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-":
            return date.fromisoformat(value)
        raise ValueError("normalized_date must be an ISO YYYY-MM-DD date")

    @model_validator(mode="after")
    def validate_value_or_abstention(self) -> _GeminiField:
        values = (self.raw_value, self.normalized_value, self.normalized_date)
        has_value = any(value is not None and (not isinstance(value, str) or bool(value.strip())) for value in values)
        has_reason = self.abstention_reason is not None and bool(self.abstention_reason.strip())

        if has_reason:
            if has_value or self.evidence is not None:
                raise ValueError("abstention fields cannot carry a value or evidence")
            return self
        if self.abstention_reason is not None:
            raise ValueError("abstention_reason must not be blank")
        if not has_value or self.evidence is None:
            raise ValueError("accepted fields require a value and evidence")
        return self


class _GeminiFields(BaseModel):
    """Exactly the six canonical SDF fields; provider-controlled names are impossible."""

    model_config = ConfigDict(extra="forbid", strict=True)

    doc_type: _GeminiField
    vendor_name: _GeminiField
    manufacturing_date: _GeminiField
    effective_date: _GeminiField
    revision_date: _GeminiField
    expiry_date: _GeminiField


class _GeminiExtractionResponse(BaseModel):
    """Strict structured-output envelope shared by text and visual extraction."""

    model_config = ConfigDict(extra="forbid", strict=True)

    fields: _GeminiFields


@dataclass(frozen=True)
class _GeminiPrice:
    input_usd_per_1m: float
    output_and_thinking_usd_per_1m: float


_GEMINI_STANDARD_PRICING_USD_PER_1M = MappingProxyType(
    {
        "gemini-2.5-flash": _GeminiPrice(input_usd_per_1m=0.30, output_and_thinking_usd_per_1m=2.50),
        "gemini-3.5-flash": _GeminiPrice(input_usd_per_1m=1.50, output_and_thinking_usd_per_1m=9.00),
    }
)


@dataclass(frozen=True)
class GeminiProviderDiagnostics:
    """Non-secret diagnostics for live provider setup and tests."""

    provider_name: str
    model: str
    max_attempts: int


class GeminiSDFExtractionProvider:
    """Gemini implementation of the SDF extraction provider protocol."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
        max_attempts: int | None = None,
        retry_sleep: Callable[[float], None] | None = None,
    ) -> None:
        settings = get_settings()
        configured_model = model or settings.gemini_model or DEFAULT_GEMINI_MODEL
        bounded_model = _bounded_model_identifier(configured_model)
        if bounded_model is None:
            raise ExtractionConfigurationError("Gemini extraction model must be a bounded model identifier.")
        configured_attempts = settings.gemini_extraction_max_attempts if max_attempts is None else max_attempts
        if (
            isinstance(configured_attempts, bool)
            or not isinstance(configured_attempts, int)
            or not 1 <= configured_attempts <= 5
        ):
            raise ExtractionConfigurationError("Gemini extraction max attempts must be an integer from 1 through 5.")

        self.model = bounded_model
        self.max_attempts = configured_attempts
        self._client = client
        self._client_factory = client_factory
        self._retry_sleep = retry_sleep or sleep
        self._api_key = (api_key if api_key is not None else settings.gemini_api_key).strip()
        self.diagnostics = GeminiProviderDiagnostics(
            provider_name=_PROVIDER_NAME,
            model=self.model,
            max_attempts=self.max_attempts,
        )

        if self._client is None and not self._api_key:
            raise ExtractionConfigurationError("GEMINI_API_KEY is required to use the Gemini extraction provider.")

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        """Call Gemini and convert structured output into provider DTOs.

        Exceptions are sanitized: callers receive typed errors containing only
        provider, bounded model identity, and exception class — never caller IDs,
        API keys, page text, image bytes, or raw model responses.
        """

        try:
            response = self._generate_content_with_retry(
                contents=_build_contents(pages=pages)
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary sanitizes arbitrary SDK failures.
            raise ExtractionProviderError(
                "Gemini extraction provider failed after bounded retry "
                f"(provider={_PROVIDER_NAME}, model={self.model}, error_class={exc.__class__.__name__})."
            ) from None

        usage_metadata = _extract_usage_metadata(response, model=self.model)
        fields = _parse_fields(response)
        if fields is None:
            return _malformed_result(trace_id=_response_trace_id(response), model=self.model, usage_metadata=usage_metadata)

        return ProviderExtractionResult(
            fields=tuple(fields),
            trace_id=_response_trace_id(response),
            provider_name=_PROVIDER_NAME,
            provider_model=self.model,
            usage_metadata=usage_metadata,
        )

    def _generate_content_with_retry(self, *, contents: Any) -> Any:
        retrying = Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_random_exponential(multiplier=0.25, max=2.0),
            retry=retry_if_exception(_is_retryable_provider_exception),
            sleep=self._retry_sleep,
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return self._generate_content(contents=contents)
        raise AssertionError("unreachable tenacity retry state")

    def _generate_content(self, *, contents: Any) -> Any:
        client = self._get_client()
        config = {
            "response_mime_type": "application/json",
            # google-genai 2.7's legacy response_schema path attempts to
            # parameterize a Pydantic v2 model class and fails before the HTTP
            # request. The SDK's supported JSON Schema path accepts the exact
            # schema generated from the same strict model and leaves local
            # validation under this adapter's control.
            "response_json_schema": _GeminiExtractionResponse.model_json_schema(),
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
            from google.genai import types as genai_types  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 - optional dependency boundary.
            raise ExtractionConfigurationError("google-genai is installed/configured incorrectly for Gemini extraction.") from None
        self._client = genai.Client(
            api_key=self._api_key,
            http_options=genai_types.HttpOptions(
                retry_options=genai_types.HttpRetryOptions(attempts=1),
            ),
        )
        return self._client


class GeminiSDFVisualFallbackProvider(GeminiSDFExtractionProvider):
    """Gemini implementation of targeted image-based visual fallback extraction."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
        part_factory: Any | None = None,
        max_attempts: int | None = None,
        retry_sleep: Callable[[float], None] | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            client=client,
            client_factory=client_factory,
            max_attempts=max_attempts,
            retry_sleep=retry_sleep,
        )
        self._part_factory = part_factory

    def extract_visual_fields(
        self,
        *,
        document: DocumentMetadata,
        request: VisualFallbackRequest,
        run_id: str,
    ) -> ProviderExtractionResult:
        """Call Gemini with bounded instructions plus selected page image parts.

        The request prompt intentionally excludes raw page text, local filesystem
        paths, previous provider payloads, PDFs, secrets, and image bytes. Image
        data is attached only as SDK ``Part`` objects for pages already selected
        by the pipeline's visual fallback planner.
        """

        requested_fields = tuple(request.eligible_field_names)
        try:
            response = self._generate_content_with_retry(
                contents=_build_visual_contents(
                    request=request,
                    part_factory=self._get_part_factory(),
                )
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary sanitizes arbitrary SDK failures.
            raise ExtractionProviderError(
                "Gemini visual fallback provider failed after bounded retry "
                f"(provider={_PROVIDER_NAME}, model={self.model}, error_class={exc.__class__.__name__})."
            ) from None

        usage_metadata = _extract_usage_metadata(response, model=self.model)
        fields = _parse_fields(response)
        if fields is None:
            return _malformed_result(
                trace_id=_response_trace_id(response),
                model=self.model,
                usage_metadata=usage_metadata,
                field_names=requested_fields,
            )

        allowed_fields = set(requested_fields)
        return ProviderExtractionResult(
            fields=tuple(_filter_requested_fields(fields, allowed_fields)),
            trace_id=_response_trace_id(response),
            provider_name=_PROVIDER_NAME,
            provider_model=self.model,
            usage_metadata=usage_metadata,
        )

    def _get_part_factory(self) -> Any:
        if self._part_factory is not None:
            return self._part_factory
        try:
            from google.genai.types import Part  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 - optional dependency boundary.
            raise ExtractionConfigurationError("google-genai is installed/configured incorrectly for Gemini visual fallback.") from None
        self._part_factory = Part
        return self._part_factory


def _build_contents(*, pages: tuple[DocumentPage, ...]) -> str:
    page_blocks = "\n\n".join(
        f"<page index=\"{page.page_num}\">\n{page.page_text or ''}\n</page>" for page in pages
    )
    field_names = ", ".join(field.value for field in SDFFieldName)
    return f"""You are extracting Pfizer supplier SDF compliance metadata.
Return ONLY valid JSON. Do not include markdown.

Required fields exactly: {field_names}
Page references must be 0-indexed. For every non-abstained field include a short
verbatim_span copied from the cited page. If uncertain or unsupported, set all
value fields to null and provide an abstention_reason. Never invent values.

Packet labeling policy:
Many supplier PDFs are packets containing emails, handwritten notes, template
pages, processing records, SDS pages, and multiple supporting certificates.
First identify the most directly relevant certificate/quality/compliance
document for the product/material itself, then extract all six fields from that
primary sub-document only. Prefer Certificate of Analysis, Certificate of
Quality, Certificate of Compliance, or equivalent product/material certificates.
Do not use email dates, handwritten notes, template release dates, delivery
dates, retest dates, processing records, or unrelated attachment dates as values
for the six fields unless the exact target field is explicitly present in the
primary product/material certificate. For example, do not map Delivery Date to
effective_date and do not map Retest Date to expiry_date.

Field labeling rules (per docs/field-definitions.md):
- effective_date may be sourced from the synonym labels "Approved On", "Issue
  Date", or "Date of Issue" on the primary certificate.
- If expiry_date is printed as "N/A", return the literal value "N/A" (do not
  abstain) — a printed "N/A" means "no expiry".
- vendor_name must be the full legal name as printed, never an abbreviation.

Pages:
{page_blocks}
"""


def _build_visual_contents(
    *,
    request: VisualFallbackRequest,
    part_factory: Any,
) -> list[Any]:
    prompt = _build_visual_prompt(request=request)
    image_parts = [
        part_factory.from_bytes(data=page.image_blob, mime_type="image/png")
        for page in request.pages
        if page.image_blob is not None
    ]
    return [prompt, *image_parts]


def _build_visual_prompt(*, request: VisualFallbackRequest) -> str:
    requested_fields = ", ".join(field.value for field in request.eligible_field_names)
    page_numbers = ", ".join(str(page.page_num) for page in request.pages)
    reason_lines = "\n".join(
        f"- {field.value}: {request.reason_codes[field]}"
        for field in request.eligible_field_names
    )
    vendor_region_rule = ""
    if SDFFieldName.VENDOR_NAME in request.eligible_field_names:
        vendor_region_rule = (
            "For vendor_name, also include a finite x/y/width/height bounding box around the printed "
            "supplier label or logo. This is required when the supplier name is visible in the image "
            "but absent from embedded page text.\n"
        )
    return f"""You are performing targeted visual fallback extraction for Pfizer supplier SDF compliance metadata.
Return ONLY valid JSON. Do not include markdown.

Image-backed page numbers: {page_numbers}

Requested fields exactly: {requested_fields}
Eligibility reason codes:
{reason_lines}

Use only the attached page images. Do not rely on page text, file paths, prior provider output, or unstated context.
The response schema always requires all six fixed field keys. Extract only fields from the requested field allowlist; for every unrequested or unsupported field set all value fields and evidence to null and provide a short abstention_reason.
Page references must be 0-indexed and must reference one of the image-backed page numbers above. For every non-abstained field include a short verbatim_span visible in the cited page image.
{vendor_region_rule}

Packet labeling policy:
Many supplier PDFs are packets containing emails, handwritten notes, template pages, processing records, SDS pages, and multiple supporting certificates.
First identify the most directly relevant certificate/quality/compliance document for the product/material itself, then extract requested fields from that primary sub-document only.
Do not use email dates, handwritten notes, template release dates, delivery dates, retest dates, processing records, or unrelated attachment dates as values unless the exact target field is explicitly present in the primary product/material certificate.

Field labeling rules (per docs/field-definitions.md), applied only to requested fields:
- An effective date may be sourced from the synonym labels "Approved On", "Issue Date", or "Date of Issue" on the primary certificate.
- If an expiry is printed as "N/A", return the literal value "N/A" (do not abstain) — a printed "N/A" means "no expiry".
- A vendor must be the full legal name as printed, never an abbreviation.
"""


def _filter_requested_fields(
    fields: list[ProviderFieldPayload],
    allowed_fields: set[SDFFieldName],
) -> list[ProviderFieldPayload]:
    filtered: list[ProviderFieldPayload] = []
    for field in fields:
        try:
            field_name = SDFFieldName(field.field_name)
        except ValueError:
            continue
        if field_name in allowed_fields:
            filtered.append(field)
    return filtered


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    text = response.get("text") if isinstance(response, dict) else _safe_getattr(response, "text")
    if isinstance(text, str):
        return text
    return ""


def _response_trace_id(response: Any) -> str | None:
    for attr in ("trace_id", "response_id", "id"):
        value = _response_value(response, attr)
        bounded = _bounded_model_identifier(value)
        if bounded is not None:
            return bounded
    return None


def _extract_usage_metadata(response: Any, *, model: str) -> ProviderUsageMetadata:
    requested_model = _bounded_model_identifier(model)
    resolved_model = _bounded_model_identifier(_response_value(response, "model_version"))
    pricing_model = _pricing_model_for(requested_model=requested_model, resolved_model=resolved_model)

    raw_usage = _response_value(response, "usage_metadata")

    input_tokens = (
        _optional_int(_usage_value(raw_usage, "prompt_token_count")) if raw_usage is not None else None
    )
    output_tokens = (
        _optional_int(_usage_value(raw_usage, "candidates_token_count")) if raw_usage is not None else None
    )
    thought_tokens = (
        _optional_int(_usage_value(raw_usage, "thoughts_token_count")) if raw_usage is not None else None
    )
    total_tokens = (
        _optional_int(_usage_value(raw_usage, "total_token_count")) if raw_usage is not None else None
    )
    if total_tokens is None and any(value is not None for value in (input_tokens, output_tokens, thought_tokens)):
        total_tokens = sum(value or 0 for value in (input_tokens, output_tokens, thought_tokens))

    return ProviderUsageMetadata(
        model=resolved_model or requested_model,
        requested_model=requested_model,
        resolved_model=resolved_model,
        pricing_model=pricing_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thought_tokens=thought_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=_estimate_gemini_cost_usd(
            pricing_model=pricing_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thought_tokens=thought_tokens,
        ),
    )


def _response_value(response: Any, field_name: str) -> Any:
    if isinstance(response, dict):
        return response.get(field_name)
    return _safe_getattr(response, field_name)


def _usage_value(raw_usage: Any, field_name: str) -> Any:
    if isinstance(raw_usage, dict):
        return raw_usage.get(field_name)
    return _safe_getattr(raw_usage, field_name)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        integer = int(value)
    except Exception:  # noqa: BLE001 - untrusted provider scalar conversion.
        return None
    return integer if integer >= 0 else None


def _estimate_gemini_cost_usd(
    *,
    pricing_model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    thought_tokens: int | None,
) -> float | None:
    if pricing_model is None:
        return None
    if input_tokens is None and output_tokens is None and thought_tokens is None:
        return None
    price = _GEMINI_STANDARD_PRICING_USD_PER_1M[pricing_model]
    input_cost = ((input_tokens or 0) / 1_000_000) * price.input_usd_per_1m
    output_cost = (
        ((output_tokens or 0) + (thought_tokens or 0)) / 1_000_000
    ) * price.output_and_thinking_usd_per_1m
    return input_cost + output_cost


def _pricing_model_for(*, requested_model: str | None, resolved_model: str | None) -> str | None:
    for candidate in (resolved_model, requested_model):
        if candidate is None:
            continue
        exact_key = candidate.strip().casefold()
        if exact_key in _GEMINI_STANDARD_PRICING_USD_PER_1M:
            return exact_key
    return None


def _bounded_model_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or len(stripped) > _MAX_MODEL_IDENTIFIER_LENGTH:
        return None
    if any(character not in _MODEL_IDENTIFIER_CHARACTERS for character in stripped):
        return None
    return stripped


def _parse_fields(response: Any) -> list[ProviderFieldPayload] | None:
    parsed = _response_value(response, "parsed")
    try:
        if parsed is not None:
            validated = _GeminiExtractionResponse.model_validate(parsed)
        else:
            validated = _GeminiExtractionResponse.model_validate_json(_response_text(response))
    except Exception:  # noqa: BLE001 - fail closed on any untrusted SDK/payload behavior.
        return None

    fields: list[ProviderFieldPayload] = []
    for field_name in SDFFieldName:
        provider_field = getattr(validated.fields, field_name.value)
        evidence = provider_field.evidence
        fields.append(
            ProviderFieldPayload(
                field_name=field_name,
                raw_value=provider_field.raw_value,
                normalized_value=provider_field.normalized_value,
                normalized_date=provider_field.normalized_date,
                confidence=provider_field.confidence,
                evidence=(
                    ProviderSourceEvidence(
                        page_num=evidence.page_num,
                        verbatim_span=evidence.verbatim_span,
                        bbox=evidence.bbox.model_dump(mode="json") if evidence.bbox is not None else None,
                    )
                    if evidence is not None
                    else None
                ),
                abstention_reason=provider_field.abstention_reason,
            )
        )
    return fields


def _malformed_result(
    *,
    trace_id: str | None,
    model: str,
    usage_metadata: ProviderUsageMetadata | None,
    field_names: tuple[SDFFieldName, ...] | None = None,
) -> ProviderExtractionResult:
    result_field_names = field_names or tuple(SDFFieldName)
    return ProviderExtractionResult(
        fields=tuple(
            ProviderFieldPayload(
                field_name=field,
                confidence=0.0,
                evidence=None,
                abstention_reason=MALFORMED_OUTPUT_REASON,
            )
            for field in result_field_names
        ),
        trace_id=trace_id,
        provider_name=_PROVIDER_NAME,
        provider_model=model,
        usage_metadata=usage_metadata,
    )


def _is_retryable_provider_exception(exc: BaseException) -> bool:
    status = _status_code(_safe_getattr(exc, "status_code"))
    if status is None:
        status = _status_code(_safe_getattr(exc, "code"))
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    class_name = exc.__class__.__name__.lower()
    return "timeout" in class_name or "ratelimit" in class_name or "rate_limit" in class_name


def _status_code(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    enum_value = _safe_getattr(value, "value")
    if isinstance(enum_value, int) and not isinstance(enum_value, bool):
        return enum_value
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) == 3:
        return int(value)
    return None


def _safe_getattr(value: Any, field_name: str) -> Any:
    try:
        return getattr(value, field_name, None)
    except Exception:  # noqa: BLE001 - provider/SDK objects are untrusted at this boundary.
        return None
