"""Mocked Gemini provider tests for offline-safe extraction behavior."""
from __future__ import annotations

import copy
import json
import traceback
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from src.config import get_settings
from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page
from src.db.schema import init_db
from src.extraction.gemini import GeminiSDFExtractionProvider, MALFORMED_OUTPUT_REASON
from src.extraction.models import ReviewState, SDFFieldName
from src.extraction.pipeline import PROVIDER_ABSTENTION_REASON, extract_document
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
    parsed: Any | None = None


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


def valid_payload_object(*, vendor_span: str = "Acme Pharma Ltd.", vendor_confidence: float = 0.94) -> dict[str, Any]:
    fields = {
        "doc_type": field_payload("Supplier Declaration Form", normalized_value="SDF", confidence=0.96),
        "vendor_name": field_payload("Acme Pharma Ltd.", confidence=vendor_confidence, span=vendor_span),
        "manufacturing_date": field_payload("2024-01-05", normalized_date="2024-01-05", confidence=0.91),
        "effective_date": field_payload("2024-02-01", normalized_date="2024-02-01", confidence=0.90),
        "revision_date": field_payload("2024-03-15", normalized_date="2024-03-15", confidence=0.88),
        "expiry_date": field_payload("2027-01-31", normalized_date="2027-01-31", confidence=0.93),
    }
    return {"fields": fields}


def valid_payload(*, vendor_span: str = "Acme Pharma Ltd.", vendor_confidence: float = 0.94) -> str:
    return json.dumps(valid_payload_object(vendor_span=vendor_span, vendor_confidence=vendor_confidence))


def field_payload(
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: str | None = None,
    confidence: float,
    span: str | None = None,
) -> dict[str, Any]:
    return {
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "normalized_date": normalized_date,
        "confidence": confidence,
        "evidence": {"page_num": 0, "verbatim_span": span or raw_value, "bbox": None},
        "abstention_reason": None,
    }


def malformed_payload_cases() -> list[Any]:
    cases: list[Any] = []

    def add(case_id: str, mutate: Any) -> None:
        payload = copy.deepcopy(valid_payload_object())
        mutate(payload)
        cases.append(pytest.param(json.dumps(payload), id=case_id))

    add("missing-field", lambda payload: payload["fields"].pop("expiry_date"))
    add(
        "extra-seventh-field",
        lambda payload: payload["fields"].__setitem__("delivery_date", field_payload("2026-01-01", confidence=0.9)),
    )
    add("extra-top-level", lambda payload: payload.__setitem__("trace_id", "RAW_RESPONSE_SENTINEL"))
    add(
        "extra-nested-property",
        lambda payload: payload["fields"]["vendor_name"].__setitem__("provider_note", "RAW_RESPONSE_SENTINEL"),
    )
    add("invalid-confidence", lambda payload: payload["fields"]["vendor_name"].__setitem__("confidence", 1.01))
    add("invalid-date", lambda payload: payload["fields"]["manufacturing_date"].__setitem__("normalized_date", "01/05/2024"))
    add("missing-evidence", lambda payload: payload["fields"]["vendor_name"].__setitem__("evidence", None))
    add(
        "value-plus-abstention",
        lambda payload: payload["fields"]["vendor_name"].__setitem__("abstention_reason", "RAW_RESPONSE_SENTINEL"),
    )
    add("negative-page", lambda payload: payload["fields"]["vendor_name"]["evidence"].__setitem__("page_num", -1))
    add(
        "oversized-bbox",
        lambda payload: payload["fields"]["vendor_name"]["evidence"].__setitem__(
            "bbox", {"x": 0.0, "y": 0.0, "width": 1_000_001.0, "height": 10.0}
        ),
    )
    add(
        "extra-bbox-property",
        lambda payload: payload["fields"]["vendor_name"]["evidence"].__setitem__(
            "bbox", {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0, "unit": "px"}
        ),
    )
    add(
        "oversized-span",
        lambda payload: payload["fields"]["vendor_name"]["evidence"].__setitem__("verbatim_span", "x" * 501),
    )
    cases.append(pytest.param("not-json RAW_RESPONSE_SENTINEL", id="malformed-json"))
    cases.append(pytest.param(f"```json\n{valid_payload()}\n```", id="markdown-fence-not-repaired"))
    return cases


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
    schema = call["config"]["response_json_schema"]
    fields_ref = schema["properties"]["fields"]["$ref"].rsplit("/", 1)[-1]
    fields_schema = schema["$defs"][fields_ref]
    expected_names = {field.value for field in SDFFieldName}
    assert set(fields_schema["properties"]) == expected_names
    assert set(fields_schema["required"]) == expected_names
    assert "items" not in fields_schema
    assert "temperature" not in call["config"]
    from google.genai import types as genai_types

    sdk_config = genai_types.GenerateContentConfig(**call["config"])
    assert sdk_config.response_json_schema == schema
    assert "Run id:" not in call["contents"]
    assert "run-gemini-001" not in call["contents"]
    assert "Document id:" not in call["contents"]
    assert "supplier-sdf.pdf" not in call["contents"]
    assert "JSON schema:" not in call["contents"]
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
    assert all(field.abstention_reason == PROVIDER_ABSTENTION_REASON for field in stored.fields.values())


@pytest.mark.parametrize("response_text", malformed_payload_cases())
def test_gemini_provider_rejects_adversarial_structured_responses(response_text: str) -> None:
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient([FakeGeminiResponse(response_text)]),
        max_attempts=1,
    )

    result = provider.extract_fields(
        document=DocumentMetadata(
            doc_id="content-derived-doc-id-sentinel",
            filename="SECRET-supplier-sdf.pdf",
            file_path="C:/confidential/SECRET-supplier-sdf.pdf",
            page_count=1,
            status="ingested",
        ),
        pages=(DocumentPage(doc_id="content-derived-doc-id-sentinel", page_num=0, page_text=PAGE_TEXT),),
        run_id="run-adversarial",
    )

    assert tuple(field.field_name for field in result.fields) == tuple(SDFFieldName)
    assert all(field.raw_value is None for field in result.fields)
    assert all(field.normalized_value is None for field in result.fields)
    assert all(field.normalized_date is None for field in result.fields)
    assert all(field.confidence == 0.0 for field in result.fields)
    assert all(field.evidence is None for field in result.fields)
    assert all(field.abstention_reason == MALFORMED_OUTPUT_REASON for field in result.fields)
    assert "RAW_RESPONSE_SENTINEL" not in repr(result)
    assert "content-derived-doc-id-sentinel" not in repr(result)
    assert "SECRET-supplier-sdf.pdf" not in repr(result)


def test_gemini_provider_revalidates_parsed_dict_with_iso_dates_and_integer_bbox() -> None:
    parsed = valid_payload_object()
    parsed["fields"]["vendor_name"]["evidence"]["bbox"] = {
        "x": 10,
        "y": 20,
        "width": 100,
        "height": 30,
    }
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient(
            [FakeGeminiResponse(text="RAW_TEXT_SENTINEL", parsed=parsed)]
        ),
        max_attempts=1,
    )

    result = provider.extract_fields(
        document=DocumentMetadata(
            doc_id="content-derived-doc-id-sentinel",
            filename="SECRET-supplier-sdf.pdf",
            file_path="C:/confidential/SECRET-supplier-sdf.pdf",
            page_count=1,
            status="ingested",
        ),
        pages=(DocumentPage(doc_id="content-derived-doc-id-sentinel", page_num=0, page_text=PAGE_TEXT),),
        run_id="SECRET/RUN/PATH",
    )

    vendor = next(field for field in result.fields if field.field_name == SDFFieldName.VENDOR_NAME)
    manufacturing = next(field for field in result.fields if field.field_name == SDFFieldName.MANUFACTURING_DATE)
    assert vendor.raw_value == "Acme Pharma Ltd."
    assert vendor.evidence is not None
    assert vendor.evidence.bbox == {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
    assert manufacturing.normalized_date == date(2024, 1, 5)
    assert "RAW_TEXT_SENTINEL" not in repr(result)


def test_provider_controlled_trace_identifier_is_bounded_and_content_free() -> None:
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient(
            [
                FakeGeminiResponse(
                    text=valid_payload(),
                    response_id="SECRET raw provider payload C:/confidential/path",
                )
            ]
        ),
        max_attempts=1,
    )

    result = provider.extract_fields(
        document=DocumentMetadata(
            doc_id="doc-001",
            filename="supplier-sdf.pdf",
            file_path="/tmp/supplier-sdf.pdf",
            page_count=1,
            status="ingested",
        ),
        pages=(DocumentPage(doc_id="doc-001", page_num=0, page_text=PAGE_TEXT),),
        run_id="run-trace-bound",
    )

    assert result.trace_id is None
    assert "SECRET raw provider payload" not in repr(result)


def test_retryable_gemini_errors_are_bounded_and_wrapped_without_secret_or_page_text() -> None:
    secret_key = "secret-gemini-key"
    sleep_delays: list[float] = []
    client = FakeGeminiClient([
        RetryableProviderError("503 temporarily unavailable with vendor page internals"),
        RetryableProviderError("503 temporarily unavailable with vendor page internals"),
    ])
    provider = GeminiSDFExtractionProvider(
        api_key=secret_key,
        client=client,
        max_attempts=2,
        retry_sleep=sleep_delays.append,
    )

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
    assert len(sleep_delays) == 1
    assert 0.0 <= sleep_delays[0] <= 2.0
    message = str(exc_info.value)
    assert exc_info.value.reason_code == "extraction_provider_error"
    assert "RetryableProviderError" in message
    assert "run-retry-001" not in message
    assert secret_key not in message
    assert "Acme Pharma Ltd." not in message
    assert "temporarily unavailable" not in message
    assert "doc-001" not in message
    assert "supplier-sdf.pdf" not in message
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    formatted = "".join(traceback.format_exception(exc_info.value))
    assert "temporarily unavailable" not in formatted
    assert secret_key not in formatted


@pytest.mark.parametrize("max_attempts", [0, 6, True, 1.5, "2"])
def test_gemini_retry_attempt_bounds_fail_before_any_client_call(max_attempts: Any) -> None:
    client = FakeGeminiClient([FakeGeminiResponse(valid_payload())])

    with pytest.raises(ExtractionConfigurationError) as exc_info:
        GeminiSDFExtractionProvider(
            api_key="test-key",
            client=client,
            max_attempts=max_attempts,
        )

    assert exc_info.value.reason_code == "extraction_configuration_error"
    assert "1 through 5" in str(exc_info.value)
    assert client.models.calls == []


def test_nonretryable_error_message_cannot_trigger_retry_or_leak_through_traceback() -> None:
    raw_sentinel = "SECRET /confidential/path 503 timeout provider payload"
    client = FakeGeminiClient(
        [
            RuntimeError(raw_sentinel),
            FakeGeminiResponse(valid_payload()),
        ]
    )
    sleep_delays: list[float] = []
    provider = GeminiSDFExtractionProvider(
        api_key="secret-gemini-key",
        client=client,
        max_attempts=5,
        retry_sleep=sleep_delays.append,
    )

    with pytest.raises(ExtractionProviderError) as exc_info:
        provider.extract_fields(
            document=DocumentMetadata(
                doc_id="content-derived-doc-id-sentinel",
                filename="SECRET-supplier-sdf.pdf",
                file_path="C:/confidential/SECRET-supplier-sdf.pdf",
                page_count=1,
                status="ingested",
            ),
            pages=(DocumentPage(doc_id="content-derived-doc-id-sentinel", page_num=0, page_text=PAGE_TEXT),),
            run_id="SECRET/RUN/PATH",
        )

    assert len(client.models.calls) == 1
    assert sleep_delays == []
    formatted = "".join(traceback.format_exception(exc_info.value))
    for fragment in (
        raw_sentinel,
        "secret-gemini-key",
        "content-derived-doc-id-sentinel",
        "SECRET-supplier-sdf.pdf",
        "SECRET/RUN/PATH",
        "Acme Pharma Ltd.",
    ):
        assert fragment not in formatted


def test_default_google_client_disables_sdk_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    from google import genai

    fake_client = FakeGeminiClient([FakeGeminiResponse(valid_payload())])
    captured: dict[str, Any] = {}

    def fake_client_factory(**kwargs: Any) -> FakeGeminiClient:
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr(genai, "Client", fake_client_factory)
    provider = GeminiSDFExtractionProvider(api_key="test-key", max_attempts=1)

    provider.extract_fields(
        document=DocumentMetadata(
            doc_id="doc-001",
            filename="supplier-sdf.pdf",
            file_path="/tmp/supplier-sdf.pdf",
            page_count=1,
            status="ingested",
        ),
        pages=(DocumentPage(doc_id="doc-001", page_num=0, page_text=PAGE_TEXT),),
        run_id="run-sdk-retries-disabled",
    )

    assert captured["api_key"] == "test-key"
    assert captured["http_options"].retry_options.attempts == 1
    assert len(fake_client.models.calls) == 1


def test_environment_configures_default_adapter_retry_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_EXTRACTION_MAX_ATTEMPTS", "5")
    get_settings.cache_clear()
    try:
        provider = GeminiSDFExtractionProvider(
            api_key="test-key",
            client=FakeGeminiClient([FakeGeminiResponse(valid_payload())]),
        )
        assert provider.diagnostics.max_attempts == 5
    finally:
        get_settings.cache_clear()


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
