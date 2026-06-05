"""Gemini visual fallback provider tests.

The visual provider may send selected page images to Gemini, but the prompt and
persistable result metadata must stay bounded: no raw page text, local paths,
PDF/image bytes, secrets, prompts in observations, or provider payload logging.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from src.db.queries import DocumentMetadata, DocumentPage
from src.extraction.gemini import GeminiSDFVisualFallbackProvider, MALFORMED_OUTPUT_REASON
from src.extraction.models import SDFFieldName
from src.extraction.providers import VisualFallbackRequest

SECRET_PAGE_TEXT = "Supplier Declaration Form\nVendor Name: Acme Pharma Ltd.\nSECRET raw page text"
SECRET_LOCAL_PATH = "C:/confidential/pfizer/supplier-sdf.pdf"
IMAGE_BYTES = b"\x89PNG\r\n\x1a\nvisual-page-bytes"


@dataclass(frozen=True)
class FakeUsageMetadata:
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    total_token_count: int | None = None


@dataclass(frozen=True)
class FakeGeminiResponse:
    text: str
    response_id: str = "gemini-visual-trace-001"
    usage_metadata: Any | None = None


@dataclass(frozen=True)
class FakeImagePart:
    data: bytes
    mime_type: str


class FakePartFactory:
    calls: list[dict[str, Any]] = []

    @classmethod
    def from_bytes(cls, *, data: bytes, mime_type: str) -> FakeImagePart:
        cls.calls.append({"data": data, "mime_type": mime_type})
        return FakeImagePart(data=data, mime_type=mime_type)


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


def document_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        doc_id="doc-visual-001",
        filename="supplier-sdf.pdf",
        file_path=SECRET_LOCAL_PATH,
        page_count=2,
        status="ingested",
    )


def visual_request(
    *,
    fields: tuple[SDFFieldName, ...] = (SDFFieldName.VENDOR_NAME, SDFFieldName.EXPIRY_DATE),
) -> VisualFallbackRequest:
    return VisualFallbackRequest(
        eligible_field_names=fields,
        pages=(
            DocumentPage(doc_id="doc-visual-001", page_num=0, page_text=SECRET_PAGE_TEXT, image_blob=IMAGE_BYTES),
            DocumentPage(doc_id="doc-visual-001", page_num=1, page_text="Revision Date: SECRET", image_blob=b"second-image"),
        ),
        reason_codes={field: "field_abstained" for field in fields},
    )


def field_payload(field_name: str, raw_value: str, *, page_num: int = 0) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "raw_value": raw_value,
        "normalized_value": raw_value,
        "normalized_date": None,
        "confidence": 0.95,
        "evidence": {"page_num": page_num, "verbatim_span": raw_value, "bbox": None},
        "abstention_reason": None,
    }


def valid_visual_payload() -> str:
    return json.dumps(
        {
            "trace_id": "provider-json-trace",
            "fields": [
                field_payload("vendor_name", "Acme Pharma Ltd."),
                field_payload("expiry_date", "2027-01-31"),
                field_payload("doc_type", "Supplier Declaration Form"),
            ],
        }
    )


def make_provider(client: FakeGeminiClient) -> GeminiSDFVisualFallbackProvider:
    FakePartFactory.calls = []
    return GeminiSDFVisualFallbackProvider(
        api_key="test-key",
        client=client,
        part_factory=FakePartFactory,
        max_attempts=1,
    )


def test_visual_provider_sends_png_image_parts_and_bounded_prompt() -> None:
    client = FakeGeminiClient([FakeGeminiResponse(valid_visual_payload())])
    provider = make_provider(client)

    provider.extract_visual_fields(document=document_metadata(), request=visual_request(), run_id="run-visual-gemini")

    assert len(client.models.calls) == 1
    call = client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["config"] == {"response_mime_type": "application/json", "temperature": 0}
    contents = call["contents"]
    assert isinstance(contents, list)
    assert len(contents) == 3
    prompt = contents[0]
    assert isinstance(prompt, str)
    assert contents[1:] == [FakeImagePart(data=IMAGE_BYTES, mime_type="image/png"), FakeImagePart(data=b"second-image", mime_type="image/png")]
    assert FakePartFactory.calls == [
        {"data": IMAGE_BYTES, "mime_type": "image/png"},
        {"data": b"second-image", "mime_type": "image/png"},
    ]
    assert "Document id: doc-visual-001" in prompt
    assert "Run id: run-visual-gemini" in prompt
    assert "Image-backed page numbers: 0, 1" in prompt
    assert "vendor_name" in prompt
    assert "expiry_date" in prompt
    assert SECRET_PAGE_TEXT not in prompt
    assert SECRET_LOCAL_PATH not in prompt
    assert "Acme Pharma Ltd." not in prompt
    assert repr(IMAGE_BYTES) not in prompt


def test_visual_prompt_contains_only_requested_field_allowlist() -> None:
    client = FakeGeminiClient([FakeGeminiResponse(valid_visual_payload())])
    provider = make_provider(client)

    result = provider.extract_visual_fields(
        document=document_metadata(),
        request=visual_request(fields=(SDFFieldName.EXPIRY_DATE,)),
        run_id="run-expiry-only",
    )

    prompt = client.models.calls[0]["contents"][0]
    assert "Requested fields exactly: expiry_date" in prompt
    assert "expiry_date: field_abstained" in prompt
    assert "vendor_name" not in prompt
    assert "manufacturing_date" not in prompt
    assert "effective_date" not in prompt
    assert "revision_date" not in prompt
    assert "doc_type" not in prompt
    assert [field.field_name for field in result.fields] == ["expiry_date"]


def test_visual_provider_populates_usage_metadata_and_filters_unrequested_fields() -> None:
    client = FakeGeminiClient(
        [
            FakeGeminiResponse(
                valid_visual_payload(),
                response_id="gemini-visual-trace-usage",
                usage_metadata=FakeUsageMetadata(prompt_token_count=1000, candidates_token_count=250, total_token_count=1250),
            )
        ]
    )
    provider = make_provider(client)

    result = provider.extract_visual_fields(document=document_metadata(), request=visual_request(), run_id="run-usage")

    assert result.provider_name == "gemini"
    assert result.provider_model == "gemini-2.5-flash"
    assert result.trace_id == "gemini-visual-trace-usage"
    assert [field.field_name for field in result.fields] == ["vendor_name", "expiry_date"]
    assert result.usage_metadata is not None
    assert result.usage_metadata.model == "gemini-2.5-flash"
    assert result.usage_metadata.input_tokens == 1000
    assert result.usage_metadata.output_tokens == 250
    assert result.usage_metadata.total_tokens == 1250
    assert result.usage_metadata.estimated_cost_usd == pytest.approx(0.0003)
    assert SECRET_PAGE_TEXT not in repr(result.usage_metadata)
    assert SECRET_LOCAL_PATH not in repr(result.usage_metadata)


def test_visual_provider_malformed_json_returns_safe_requested_field_abstentions_with_usage() -> None:
    client = FakeGeminiClient(
        [
            FakeGeminiResponse(
                "not-json and not logged",
                response_id="gemini-visual-malformed",
                usage_metadata={"prompt_token_count": "80", "candidates_token_count": "12", "total_token_count": "92"},
            )
        ]
    )
    provider = make_provider(client)

    result = provider.extract_visual_fields(
        document=document_metadata(),
        request=visual_request(fields=(SDFFieldName.VENDOR_NAME,)),
        run_id="run-malformed",
    )

    assert result.trace_id == "gemini-visual-malformed"
    assert result.provider_name == "gemini"
    assert result.provider_model == "gemini-2.5-flash"
    assert len(result.fields) == 1
    assert result.fields[0].field_name == SDFFieldName.VENDOR_NAME
    assert result.fields[0].abstention_reason == MALFORMED_OUTPUT_REASON
    assert result.fields[0].raw_value is None
    assert result.usage_metadata is not None
    assert result.usage_metadata.input_tokens == 80
    assert result.usage_metadata.output_tokens == 12
    assert result.usage_metadata.total_tokens == 92
    assert result.usage_metadata.estimated_cost_usd == pytest.approx(0.0000192)
    assert "not-json and not logged" not in repr(result)
    assert SECRET_PAGE_TEXT not in repr(result)
    assert SECRET_LOCAL_PATH not in repr(result)


def test_visual_provider_error_is_sanitized_without_payload_text_paths_or_images() -> None:
    client = FakeGeminiClient([RuntimeError("SECRET provider payload with C:/confidential path and page text")])
    provider = make_provider(client)

    with pytest.raises(Exception) as exc_info:
        provider.extract_visual_fields(document=document_metadata(), request=visual_request(), run_id="run-error")

    message = str(exc_info.value)
    assert "Gemini visual fallback provider failed after bounded retry" in message
    assert "error_class=RuntimeError" in message
    assert "SECRET" not in message
    assert SECRET_LOCAL_PATH not in message
    assert SECRET_PAGE_TEXT not in message
    assert repr(IMAGE_BYTES) not in message
