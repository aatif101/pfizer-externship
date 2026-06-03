"""Gemini-backed SDF extraction provider.

The adapter is intentionally lazy and offline-safe: importing this module never
requires credentials, network access, or the ``google-genai`` package to be
initialized. Live calls are made only from ``extract_fields`` and return the same
provider DTOs consumed by the extraction pipeline. Provider output is untrusted;
raw responses and page text are not logged or surfaced in exceptions.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_none

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
)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
MALFORMED_OUTPUT_REASON = "Provider returned malformed structured output."
_PROVIDER_NAME = "gemini"
_GEMINI_2_5_FLASH_INPUT_USD_PER_1M = 0.15
_GEMINI_2_5_FLASH_OUTPUT_USD_PER_1M = 0.60


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
        max_attempts: int = 2,
    ) -> None:
        settings = get_settings()
        self.model = (model or settings.gemini_model or DEFAULT_GEMINI_MODEL).strip()
        self.max_attempts = max(1, int(max_attempts))
        self._client = client
        self._client_factory = client_factory
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

        Exceptions are sanitized: callers receive typed errors containing model,
        provider, run/document identifiers, and exception class only — never API
        keys, page text, image bytes, or raw model responses.
        """

        try:
            response = self._generate_content_with_retry(
                contents=_build_contents(document=document, pages=pages, run_id=run_id)
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary sanitizes arbitrary SDK failures.
            raise ExtractionProviderError(
                "Gemini extraction provider failed after bounded retry "
                f"(provider={_PROVIDER_NAME}, model={self.model}, run_id={run_id}, "
                f"doc_id={document.doc_id}, error_class={exc.__class__.__name__})."
            ) from exc

        usage_metadata = _extract_usage_metadata(response, model=self.model)
        response_text = _response_text(response)
        payload = _parse_json_object(response_text)
        if payload is None:
            return _malformed_result(trace_id=_response_trace_id(response), model=self.model, usage_metadata=usage_metadata)

        fields = _parse_fields(payload)
        if fields is None:
            return _malformed_result(trace_id=_response_trace_id(response), model=self.model, usage_metadata=usage_metadata)

        return ProviderExtractionResult(
            fields=tuple(fields),
            trace_id=_response_trace_id(response),
            provider_name=_PROVIDER_NAME,
            provider_model=self.model,
            usage_metadata=usage_metadata,
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
            raise ExtractionConfigurationError("google-genai is installed/configured incorrectly for Gemini extraction.") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client


def _build_contents(*, document: DocumentMetadata, pages: tuple[DocumentPage, ...], run_id: str) -> str:
    page_blocks = "\n\n".join(
        f"<page index=\"{page.page_num}\">\n{page.page_text or ''}\n</page>" for page in pages
    )
    field_names = ", ".join(field.value for field in SDFFieldName)
    return f"""You are extracting Pfizer supplier SDF compliance metadata.
Return ONLY valid JSON. Do not include markdown.

Document id: {document.doc_id}
Filename: {document.filename}
Run id: {run_id}

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

JSON schema:
{{
  "trace_id": "optional provider trace id",
  "fields": [
    {{
      "field_name": "doc_type | vendor_name | manufacturing_date | effective_date | revision_date | expiry_date",
      "raw_value": "string or null",
      "normalized_value": "string/number/boolean or null",
      "normalized_date": "YYYY-MM-DD or null",
      "confidence": 0.0,
      "evidence": {{"page_num": 0, "verbatim_span": "short copied text", "bbox": null}},
      "abstention_reason": "string or null"
    }}
  ]
}}

Pages:
{page_blocks}
"""


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    return ""


def _response_trace_id(response: Any) -> str | None:
    for attr in ("trace_id", "response_id", "id"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_usage_metadata(response: Any, *, model: str) -> ProviderUsageMetadata | None:
    raw_usage = getattr(response, "usage_metadata", None)
    if raw_usage is None and isinstance(response, dict):
        raw_usage = response.get("usage_metadata")
    if raw_usage is None:
        return None

    input_tokens = _optional_int(_usage_value(raw_usage, "prompt_token_count"))
    output_tokens = _optional_int(_usage_value(raw_usage, "candidates_token_count"))
    total_tokens = _optional_int(_usage_value(raw_usage, "total_token_count"))
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    return ProviderUsageMetadata(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=_estimate_gemini_cost_usd(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def _usage_value(raw_usage: Any, field_name: str) -> Any:
    if isinstance(raw_usage, dict):
        return raw_usage.get(field_name)
    return getattr(raw_usage, field_name, None)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    return integer if integer >= 0 else None


def _estimate_gemini_cost_usd(*, model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if model.strip().lower() != DEFAULT_GEMINI_MODEL:
        return None
    if input_tokens is None and output_tokens is None:
        return None
    input_cost = ((input_tokens or 0) / 1_000_000) * _GEMINI_2_5_FLASH_INPUT_USD_PER_1M
    output_cost = ((output_tokens or 0) / 1_000_000) * _GEMINI_2_5_FLASH_OUTPUT_USD_PER_1M
    return input_cost + output_cost


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


def _parse_fields(payload: dict[str, Any]) -> list[ProviderFieldPayload] | None:
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list):
        return None

    fields: list[ProviderFieldPayload] = []
    for item in raw_fields:
        if not isinstance(item, dict):
            return None
        field_name = item.get("field_name")
        if not isinstance(field_name, str):
            return None

        raw_evidence = item.get("evidence")
        evidence = None
        if isinstance(raw_evidence, dict):
            page_num = raw_evidence.get("page_num")
            evidence = ProviderSourceEvidence(
                page_num=page_num if isinstance(page_num, int) else -1,
                verbatim_span=_optional_str(raw_evidence.get("verbatim_span")),
                bbox=raw_evidence.get("bbox"),
            )

        fields.append(
            ProviderFieldPayload(
                field_name=field_name,
                raw_value=_optional_str(item.get("raw_value")),
                normalized_value=item.get("normalized_value"),
                normalized_date=item.get("normalized_date"),
                confidence=_float_or_zero(item.get("confidence")),
                evidence=evidence,
                abstention_reason=_optional_str(item.get("abstention_reason")),
            )
        )
    return fields


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _malformed_result(
    *,
    trace_id: str | None,
    model: str,
    usage_metadata: ProviderUsageMetadata | None,
) -> ProviderExtractionResult:
    return ProviderExtractionResult(
        fields=tuple(
            ProviderFieldPayload(
                field_name=field,
                confidence=0.0,
                evidence=ProviderSourceEvidence(page_num=0),
                abstention_reason=MALFORMED_OUTPUT_REASON,
            )
            for field in SDFFieldName
        ),
        trace_id=trace_id,
        provider_name=_PROVIDER_NAME,
        provider_model=model,
        usage_metadata=usage_metadata,
    )


def _is_retryable_provider_exception(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    class_name = exc.__class__.__name__.lower()
    if "timeout" in class_name or "ratelimit" in class_name or "rate_limit" in class_name:
        return True
    message = str(exc).lower()
    return any(token in message for token in ("429", "503", "504", "timeout", "temporarily unavailable"))
