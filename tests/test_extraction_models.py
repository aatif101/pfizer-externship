"""Tests for the typed SDF extraction contract."""
from __future__ import annotations

from dataclasses import fields as dataclass_fields
from datetime import date

import pytest
from pydantic import ValidationError

from src.extraction.models import (
    ExtractionDocumentStatus,
    ExtractionRunDocument,
    ExtractionRunStatus,
    ExtractionRunSummary,
    ExtractedField,
    ReviewState,
    SDFExtractionRecord,
    SDFFieldName,
    SourceEvidence,
)


def test_extraction_lifecycle_models_are_typed_frozen_and_content_free() -> None:
    document = ExtractionRunDocument(
        run_id="run-001",
        doc_id="doc-001",
        status=ExtractionDocumentStatus.PENDING,
        attempt_count=0,
        trace_id=None,
        error_reason=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    summary = ExtractionRunSummary(
        run_id="run-001",
        status=ExtractionRunStatus.RUNNING,
        document_count=0,
        field_count=0,
        expected_document_count=1,
        attempted_document_count=0,
        succeeded_document_count=0,
        failed_document_count=0,
        provider="gemini",
        requested_model="gemini-2.5-flash",
        resolved_model=None,
        corpus_version="holdout-v1",
        manifest_hash="a" * 64,
        trace_id=None,
        started_at=None,
        completed_at=None,
        created_at=None,
        updated_at=None,
    )

    assert [status.value for status in ExtractionRunStatus] == ["running", "completed", "partial", "failed"]
    assert [status.value for status in ExtractionDocumentStatus] == ["pending", "running", "completed", "failed"]
    assert document.status is ExtractionDocumentStatus.PENDING
    assert summary.status is ExtractionRunStatus.RUNNING
    public_field_names = {
        field.name
        for dto in (ExtractionRunDocument, ExtractionRunSummary)
        for field in dataclass_fields(dto)
    }
    assert public_field_names.isdisjoint(
        {
            "filename",
            "file_path",
            "field_value",
            "verbatim_span",
            "page_text",
            "image_blob",
            "provider_payload",
            "raw_error",
            "api_key",
            "secret",
        }
    )
    forbidden = ("page text sentinel", "provider payload sentinel", "secret sentinel", "C:\\private\\doc.pdf")
    assert not any(value in repr(document) + repr(summary) for value in forbidden)
    with pytest.raises(AttributeError):
        document.attempt_count = 1  # type: ignore[misc]


def make_field(
    field_name: SDFFieldName,
    raw_value: str = "Sample value",
    confidence: float = 0.9,
    page_num: int = 0,
) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=raw_value,
        confidence=confidence,
        evidence=SourceEvidence(
            page_num=page_num,
            bbox={"x": 10, "y": 20, "width": 100, "height": 30},
            verbatim_span=raw_value,
        ),
        review_state=ReviewState.PENDING,
    )


def make_record() -> SDFExtractionRecord:
    fields = {field_name: make_field(field_name) for field_name in SDFFieldName}
    fields[SDFFieldName.MANUFACTURING_DATE] = ExtractedField(
        field_name=SDFFieldName.MANUFACTURING_DATE,
        raw_value="2024-01-05",
        normalized_value="2024-01-05",
        normalized_date=date(2024, 1, 5),
        confidence=0.95,
        evidence=SourceEvidence(page_num=1, bbox=[10, 20, 100, 30], verbatim_span="2024-01-05"),
        review_state=ReviewState.REVIEWED,
    )
    return SDFExtractionRecord(
        doc_id="doc-001",
        filename="supplier-sdf.pdf",
        fields=fields,
        trace_id="trace-123",
        run_id="run-456",
    )


def test_accepts_full_six_field_sample_record() -> None:
    record = make_record()

    assert set(record.fields) == set(SDFFieldName)
    assert record.aggregate_confidence == pytest.approx(0.9083333333333333)
    assert record.aggregate_review_state == ReviewState.PENDING
    assert record.dashboard_values[SDFFieldName.MANUFACTURING_DATE.value] == "2024-01-05"
    assert record.dashboard_review_state == ReviewState.PENDING.value
    assert record.dashboard_needs_review is False
    assert record.trace_id == "trace-123"


def test_accepts_abstained_field_with_reason_and_without_value_or_span() -> None:
    field = ExtractedField(
        field_name=SDFFieldName.EXPIRY_DATE,
        raw_value=None,
        confidence=0.0,
        evidence=SourceEvidence(page_num=0),
        review_state=ReviewState.ABSTAINED,
        abstention_reason="Expiry date is not present on the supplied page.",
    )

    assert field.needs_review is True
    assert field.value_for_dashboard is None


def test_rejects_unknown_field_name() -> None:
    with pytest.raises(ValidationError):
        ExtractedField(
            field_name="lot_number",
            raw_value="ABC123",
            confidence=0.9,
            evidence=SourceEvidence(page_num=0, verbatim_span="ABC123"),
        )


def test_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        make_field(SDFFieldName.VENDOR_NAME, confidence=-0.01)

    with pytest.raises(ValidationError):
        make_field(SDFFieldName.VENDOR_NAME, confidence=1.01)


def test_rejects_negative_source_page() -> None:
    with pytest.raises(ValidationError):
        SourceEvidence(page_num=-1, verbatim_span="Vendor")


def test_rejects_malformed_bbox() -> None:
    with pytest.raises(ValidationError):
        SourceEvidence(page_num=0, bbox="10,20,100,30", verbatim_span="Vendor")

    with pytest.raises(ValidationError):
        SourceEvidence(page_num=0, bbox={"x": object()}, verbatim_span="Vendor")


def test_rejects_missing_value_without_abstention() -> None:
    with pytest.raises(ValidationError):
        ExtractedField(
            field_name=SDFFieldName.VENDOR_NAME,
            raw_value=None,
            confidence=0.5,
            evidence=SourceEvidence(page_num=0),
            review_state=ReviewState.NEEDS_REVIEW,
        )


def test_rejects_abstention_without_reason() -> None:
    with pytest.raises(ValidationError):
        ExtractedField(
            field_name=SDFFieldName.EXPIRY_DATE,
            raw_value=None,
            confidence=0.0,
            evidence=SourceEvidence(page_num=0),
            review_state=ReviewState.ABSTAINED,
        )


def test_rejects_record_missing_required_sdf_field() -> None:
    fields = {field_name: make_field(field_name) for field_name in SDFFieldName}
    fields.pop(SDFFieldName.REVISION_DATE)

    with pytest.raises(ValidationError):
        SDFExtractionRecord(doc_id="doc-001", filename="supplier-sdf.pdf", fields=fields)
