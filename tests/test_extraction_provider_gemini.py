"""Mocked Gemini provider tests for offline-safe extraction behavior."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from src.config import get_settings
from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page
from src.db.schema import init_db
from src.extraction.gemini import GeminiSDFExtractionProvider, MALFORMED_OUTPUT_REASON
from src.extraction.models import ReviewState, SDFFieldName
from src.extraction.pipeline import extract_document
from src.extraction.providers import ExtractionConfigurationError, ExtractionProviderError
from src.extraction.repository import get_extraction_record

PAGE_TEXT = """
Supplier Declaration Form
Vendor Name: Acme Pharma Ltd.
Manufacturing Date: 2024-01-05
Effective Date: 2024-02-01
Revision Date: 2024-03-15
Expiry Date: 2027-01-31
"""


@dataclass
class FakeGeminiResponse:
    text: str
    response_id: str = "gemini-trace-001"


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


def prepare_doc(db_path: str) -> None:
    init_db(db_path)
    insert_document(
        db_path,
        doc_id="doc-001",
        filename="supplier-sdf.pdf",
        file_path="/tmp/supplier-sdf.pdf",
        page_count=1,
        docling_json=None,
    )
    insert_page(db_path, doc_id="doc-001", page_num=0, page_text=PAGE_TEXT, image_blob=None)


def valid_payload(*, vendor_span: str = "Acme Pharma Ltd.", vendor_confidence: float = 0.94) -> str:
    fields = [
        field_payload("doc_type", "Supplier Declaration Form", normalized_value="SDF", confidence=0.96),
        field_payload("vendor_name", "Acme Pharma Ltd.", confidence=vendor_confidence, span=vendor_span),
        field_payload("manufacturing_date", "2024-01-05", normalized_date="2024-01-05", confidence=0.91),
        field_payload("effective_date", "2024-02-01", normalized_date="2024-02-01", confidence=0.90),
        field_payload("revision_date", "2024-03-15", normalized_date="2024-03-15", confidence=0.88),
        field_payload("expiry_date", "2027-01-31", normalized_date="2027-01-31", confidence=0.93),
    ]
    return json.dumps({"trace_id": "provider-json-trace", "fields": fields})


def field_payload(
    field_name: str,
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: str | None = None,
    confidence: float,
    span: str | None = None,
) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "normalized_date": normalized_date,
        "confidence": confidence,
        "evidence": {"page_num": 0, "verbatim_span": span or raw_value, "bbox": None},
        "abstention_reason": None,
    }


def test_missing_gemini_api_key_raises_typed_configuration_error() -> None:
    get_settings.cache_clear()

    with pytest.raises(ExtractionConfigurationError) as exc_info:
        GeminiSDFExtractionProvider(api_key="")

    assert exc_info.value.reason_code == "extraction_configuration_error"
    assert "GEMINI_API_KEY" in str(exc_info.value)


def test_gemini_provider_parses_structured_six_field_output_without_network() -> None:
    client = FakeGeminiClient([FakeGeminiResponse(valid_payload())])
    provider = GeminiSDFExtractionProvider(api_key="test-key", client=client, max_attempts=1)

    result = provider.extract_fields(
        document=DocumentMetadata(
            doc_id="doc-001",
            filename="supplier-sdf.pdf",
            file_path="/tmp/supplier-sdf.pdf",
            page_count=1,
            status="ingested",
        ),
        pages=(DocumentPage(doc_id="doc-001", page_num=0, page_text=PAGE_TEXT),),
        run_id="run-gemini-001",
    )

    assert result.provider_name == "gemini"
    assert result.trace_id == "gemini-trace-001"
    assert len(result.fields) == 6
    assert {field.field_name for field in result.fields} == {field.value for field in SDFFieldName}
    call = client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["config"]["response_mime_type"] == "application/json"
    assert "Run id: run-gemini-001" in call["contents"]
    assert "Packet labeling policy" in call["contents"]
    assert "primary product/material certificate" in call["contents"]
    assert "do not map Delivery Date to" in call["contents"]
    assert "do not map Retest Date to expiry_date" in call["contents"]


def test_malformed_gemini_json_becomes_abstention_records(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient([FakeGeminiResponse("not-json and not logged")]),
        max_attempts=1,
    )

    result = extract_document(tmp_db_path, "doc-001", provider, today=date(2026, 1, 1), run_id="run-bad-json")

    assert result.diagnostics.provider_name == "gemini"
    assert result.record.dashboard_needs_review is True
    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert all(field.review_state == ReviewState.ABSTAINED for field in stored.fields.values())
    assert all(field.abstention_reason == MALFORMED_OUTPUT_REASON for field in stored.fields.values())


def test_retryable_gemini_errors_are_bounded_and_wrapped_without_secret_or_page_text() -> None:
    secret_key = "secret-gemini-key"
    client = FakeGeminiClient([
        RetryableProviderError("503 temporarily unavailable with vendor page internals"),
        RetryableProviderError("503 temporarily unavailable with vendor page internals"),
    ])
    provider = GeminiSDFExtractionProvider(api_key=secret_key, client=client, max_attempts=2)

    with pytest.raises(ExtractionProviderError) as exc_info:
        provider.extract_fields(
            document=DocumentMetadata(
                doc_id="doc-001",
                filename="supplier-sdf.pdf",
                file_path="/tmp/supplier-sdf.pdf",
                page_count=1,
                status="ingested",
            ),
            pages=(DocumentPage(doc_id="doc-001", page_num=0, page_text=PAGE_TEXT),),
            run_id="run-retry-001",
        )

    assert len(client.models.calls) == 2
    message = str(exc_info.value)
    assert exc_info.value.reason_code == "extraction_provider_error"
    assert "RetryableProviderError" in message
    assert "run-retry-001" in message
    assert secret_key not in message
    assert "Acme Pharma Ltd." not in message
    assert "temporarily unavailable" not in message


def test_low_confidence_gemini_field_requires_review_after_pipeline_validation(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient([FakeGeminiResponse(valid_payload(vendor_confidence=0.70))]),
        max_attempts=1,
    )

    extract_document(tmp_db_path, "doc-001", provider, today=date(2026, 1, 1), run_id="run-low-confidence")

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert stored.fields[SDFFieldName.VENDOR_NAME].review_state == ReviewState.NEEDS_REVIEW
    assert stored.fields[SDFFieldName.DOC_TYPE].review_state == ReviewState.PENDING


def test_gemini_span_mismatch_is_abstained_by_pipeline_grounding(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient([FakeGeminiResponse(valid_payload(vendor_span="Different supplier"))]),
        max_attempts=1,
    )

    extract_document(tmp_db_path, "doc-001", provider, today=date(2026, 1, 1), run_id="run-span-mismatch")

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    vendor = stored.fields[SDFFieldName.VENDOR_NAME]
    assert vendor.review_state == ReviewState.ABSTAINED
    assert vendor.abstention_reason == "Provider source span was not found in the cited page text."
