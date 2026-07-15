"""Gemini extraction usage telemetry tests.

These tests keep the observability contract bounded: usage rows may contain run,
document, provider/model, status, trace id, latency, token counts, and estimated
cost, but never prompts, page text, raw provider payloads, image/PDF bytes,
secrets, or local confidential paths.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page
from src.db.schema import init_db
from src.eval.repository import list_extraction_usage_observations
from src.extraction.gemini import GeminiSDFExtractionProvider
from src.extraction.models import ReviewState, SDFFieldName
from src.extraction.pipeline import PROVIDER_ABSTENTION_REASON, extract_document
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
class FakeUsageMetadata:
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    thoughts_token_count: int | None = None
    total_token_count: int | None = None


@dataclass
class FakeGeminiResponse:
    text: str
    response_id: str = "gemini-trace-usage-001"
    usage_metadata: Any | None = None
    model_version: Any | None = None
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


def field_payload(
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: str | None = None,
    confidence: float,
) -> dict[str, Any]:
    return {
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "normalized_date": normalized_date,
        "confidence": confidence,
        "evidence": {"page_num": 0, "verbatim_span": raw_value, "bbox": None},
        "abstention_reason": None,
    }


def valid_payload() -> str:
    fields = {
        "doc_type": field_payload("Supplier Declaration Form", normalized_value="SDF", confidence=0.96),
        "vendor_name": field_payload("Acme Pharma Ltd.", confidence=0.94),
        "manufacturing_date": field_payload("2024-01-05", normalized_date="2024-01-05", confidence=0.91),
        "effective_date": field_payload("2024-02-01", normalized_date="2024-02-01", confidence=0.90),
        "revision_date": field_payload("2024-03-15", normalized_date="2024-03-15", confidence=0.88),
        "expiry_date": field_payload("2027-01-31", normalized_date="2027-01-31", confidence=0.93),
    }
    return json.dumps({"fields": fields})


def assert_usage_row_is_bounded(row: object) -> None:
    row_repr = repr(row)
    forbidden_fragments = {
        "Supplier Declaration Form",
        "Acme Pharma Ltd.",
        "Manufacturing Date",
        "Run id:",
        "Packet labeling policy",
        "not-json and not logged",
        "/tmp/supplier-sdf.pdf",
        "verbatim_span",
        "raw_value",
        '"fields"',
        "SECRET",
    }
    for fragment in forbidden_fragments:
        assert fragment not in row_repr


def test_gemini_provider_prices_25_candidate_and_thinking_tokens_with_auditable_models() -> None:
    client = FakeGeminiClient(
        [
            FakeGeminiResponse(
                valid_payload(),
                usage_metadata=FakeUsageMetadata(
                    prompt_token_count=1_000,
                    candidates_token_count=250,
                    thoughts_token_count=50,
                    total_token_count=1_300,
                ),
                model_version="gemini-2.5-flash",
            )
        ]
    )
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
        run_id="run-gemini-usage-provider",
    )

    assert result.provider_name == "gemini"
    assert result.provider_model == "gemini-2.5-flash"
    assert result.usage_metadata is not None
    assert result.usage_metadata.model == "gemini-2.5-flash"
    assert result.usage_metadata.requested_model == "gemini-2.5-flash"
    assert result.usage_metadata.resolved_model == "gemini-2.5-flash"
    assert result.usage_metadata.pricing_model == "gemini-2.5-flash"
    assert result.usage_metadata.input_tokens == 1_000
    assert result.usage_metadata.output_tokens == 250
    assert result.usage_metadata.thought_tokens == 50
    assert result.usage_metadata.total_tokens == 1_300
    assert result.usage_metadata.estimated_cost_usd == pytest.approx((1_000 * 0.30 + 300 * 2.50) / 1_000_000)
    assert "Acme Pharma Ltd." not in repr(result.usage_metadata)


def test_gemini_provider_unknown_model_keeps_tokens_but_null_cost() -> None:
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        model="gemini-future-model",
        client=FakeGeminiClient(
            [
                FakeGeminiResponse(
                    valid_payload(),
                    usage_metadata={
                        "prompt_token_count": "100",
                        "candidates_token_count": "20",
                        "total_token_count": "120",
                    },
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
        run_id="run-unknown-model",
    )

    assert result.usage_metadata is not None
    assert result.usage_metadata.model == "gemini-future-model"
    assert result.usage_metadata.requested_model == "gemini-future-model"
    assert result.usage_metadata.resolved_model is None
    assert result.usage_metadata.pricing_model is None
    assert result.usage_metadata.input_tokens == 100
    assert result.usage_metadata.output_tokens == 20
    assert result.usage_metadata.total_tokens == 120
    assert result.usage_metadata.estimated_cost_usd is None


def test_gemini_35_uses_the_same_schema_path_and_july_2026_price() -> None:
    client = FakeGeminiClient(
        [
            FakeGeminiResponse(
                valid_payload(),
                usage_metadata=FakeUsageMetadata(
                    prompt_token_count=1_000,
                    candidates_token_count=250,
                    thoughts_token_count=50,
                    total_token_count=1_300,
                ),
                model_version="gemini-3.5-flash",
            )
        ]
    )
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        model="gemini-3.5-flash",
        client=client,
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
        run_id="run-gemini-35",
    )

    call = client.models.calls[0]
    assert call["model"] == "gemini-3.5-flash"
    assert call["config"]["response_json_schema"]
    assert "temperature" not in call["config"]
    assert result.usage_metadata is not None
    assert result.usage_metadata.requested_model == "gemini-3.5-flash"
    assert result.usage_metadata.resolved_model == "gemini-3.5-flash"
    assert result.usage_metadata.pricing_model == "gemini-3.5-flash"
    assert result.usage_metadata.thought_tokens == 50
    assert result.usage_metadata.estimated_cost_usd == pytest.approx((1_000 * 1.50 + 300 * 9.00) / 1_000_000)


def test_recognized_resolved_model_prices_an_unknown_requested_alias() -> None:
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        model="internal-quality-alias",
        client=FakeGeminiClient(
            [
                FakeGeminiResponse(
                    valid_payload(),
                    model_version="gemini-2.5-flash",
                    usage_metadata={
                        "prompt_token_count": 100,
                        "candidates_token_count": 20,
                        "thoughts_token_count": 5,
                    },
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
        run_id="run-resolved-model",
    )

    assert result.usage_metadata is not None
    assert result.usage_metadata.model == "gemini-2.5-flash"
    assert result.usage_metadata.requested_model == "internal-quality-alias"
    assert result.usage_metadata.resolved_model == "gemini-2.5-flash"
    assert result.usage_metadata.pricing_model == "gemini-2.5-flash"
    assert result.usage_metadata.total_tokens == 125
    assert result.usage_metadata.estimated_cost_usd == pytest.approx((100 * 0.30 + 25 * 2.50) / 1_000_000)


@pytest.mark.parametrize("model", ["gemini-2.5-flash-latest", "models/gemini-2.5-flash", "gemini-2.5-flash-preview"])
def test_model_aliases_and_prefixes_never_inherit_exact_registry_prices(model: str) -> None:
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        model=model,
        client=FakeGeminiClient(
            [FakeGeminiResponse(valid_payload(), model_version=model, usage_metadata={"prompt_token_count": 10})]
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
        run_id="run-alias-model",
    )

    assert result.usage_metadata is not None
    assert result.usage_metadata.pricing_model is None
    assert result.usage_metadata.estimated_cost_usd is None


def test_invalid_usage_counters_are_ignored_and_missing_total_is_derived() -> None:
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient(
            [
                FakeGeminiResponse(
                    valid_payload(),
                    usage_metadata={
                        "prompt_token_count": 100,
                        "candidates_token_count": -1,
                        "thoughts_token_count": 5,
                        "total_token_count": True,
                    },
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
        run_id="run-invalid-counters",
    )

    assert result.usage_metadata is not None
    assert result.usage_metadata.input_tokens == 100
    assert result.usage_metadata.output_tokens is None
    assert result.usage_metadata.thought_tokens == 5
    assert result.usage_metadata.total_tokens == 105
    assert result.usage_metadata.estimated_cost_usd == pytest.approx((100 * 0.30 + 5 * 2.50) / 1_000_000)


def test_pipeline_persists_one_bounded_text_usage_observation_for_mocked_gemini(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient(
            [
                FakeGeminiResponse(
                    valid_payload(),
                    usage_metadata=FakeUsageMetadata(
                        prompt_token_count=1_000,
                        candidates_token_count=250,
                        total_token_count=1_250,
                    ),
                )
            ]
        ),
        max_attempts=1,
    )

    result = extract_document(tmp_db_path, "doc-001", provider, today=date(2026, 1, 1), run_id="run-gemini-usage")

    assert result.record.dashboard_needs_review is False
    rows = list_extraction_usage_observations(
        tmp_db_path,
        run_id="run-gemini-usage",
        doc_id="doc-001",
        stage="text_extraction",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.stage == "text_extraction"
    assert row.provider == "gemini"
    assert row.model == "gemini-2.5-flash"
    assert row.status == "complete"
    assert row.latency_ms is not None
    assert row.latency_ms >= 0
    assert row.input_tokens == 1_000
    assert row.output_tokens == 250
    assert row.total_tokens == 1_250
    assert row.estimated_cost_usd == pytest.approx((1_000 * 0.30 + 250 * 2.50) / 1_000_000)
    assert row.trace_id == "gemini-trace-usage-001"
    assert row.error_reason is None
    assert_usage_row_is_bounded(row)


def test_pipeline_persists_nullable_usage_fields_when_gemini_metadata_is_absent(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient([FakeGeminiResponse(valid_payload(), usage_metadata=None)]),
        max_attempts=1,
    )

    extract_document(tmp_db_path, "doc-001", provider, today=date(2026, 1, 1), run_id="run-no-usage")

    rows = list_extraction_usage_observations(
        tmp_db_path,
        run_id="run-no-usage",
        doc_id="doc-001",
        stage="text_extraction",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "complete"
    assert row.input_tokens is None
    assert row.output_tokens is None
    assert row.total_tokens is None
    assert row.estimated_cost_usd is None
    assert row.model == "gemini-2.5-flash"
    assert_usage_row_is_bounded(row)


def test_malformed_gemini_json_with_usage_persists_abstained_usage_observation(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = GeminiSDFExtractionProvider(
        api_key="test-key",
        client=FakeGeminiClient(
            [
                FakeGeminiResponse(
                    "not-json and not logged",
                    response_id="gemini-malformed-trace",
                    usage_metadata=FakeUsageMetadata(
                        prompt_token_count=80,
                        candidates_token_count=12,
                        total_token_count=92,
                    ),
                )
            ]
        ),
        max_attempts=1,
    )

    result = extract_document(tmp_db_path, "doc-001", provider, today=date(2026, 1, 1), run_id="run-malformed-usage")

    assert result.record.dashboard_needs_review is True
    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert all(field.review_state == ReviewState.ABSTAINED for field in stored.fields.values())
    assert all(field.abstention_reason == PROVIDER_ABSTENTION_REASON for field in stored.fields.values())
    assert set(stored.fields) == set(SDFFieldName)

    rows = list_extraction_usage_observations(
        tmp_db_path,
        run_id="run-malformed-usage",
        doc_id="doc-001",
        stage="text_extraction",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "abstained"
    assert row.error_reason == "all_fields_abstained"
    assert row.input_tokens == 80
    assert row.output_tokens == 12
    assert row.total_tokens == 92
    assert row.estimated_cost_usd == pytest.approx((80 * 0.30 + 12 * 2.50) / 1_000_000)
    assert row.trace_id == "gemini-malformed-trace"
    assert_usage_row_is_bounded(row)
