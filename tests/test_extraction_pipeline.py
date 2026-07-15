"""Integration tests for the offline fake-provider extraction pipeline."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from typing import Any

import pytest

from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page, load_document_pages
from src.db.schema import init_db
from src.extraction.models import ReviewState, SDFFieldName
from src.extraction.pipeline import (
    DocumentNotFoundError,
    NoPagesError,
    NoPageTextError,
    InvalidConfidenceThresholdError,
    ProviderInvocationError,
    ProviderOutputError,
    extract_document,
)
from src.eval.repository import list_extraction_usage_observations
from src.extraction.providers import (
    ExtractionProviderError,
    ProviderExtractionResult,
    ProviderFieldPayload,
    ProviderSourceEvidence,
    ProviderUsageMetadata,
)
from src.extraction.repository import get_extraction_record, list_compliance_records, list_extraction_run_summaries


PAGE_TEXT = """
Supplier Declaration Form
Vendor Name: Acme Pharma Ltd.
Manufacturing Date: 2024-01-05
Effective Date: 2024-02-01
Revision Date: 2024-03-15
Expiry Date: 2027-01-31
This certificate remains controlled under Pfizer supplier documentation rules.
"""


@dataclass
class FakeProvider:
    fields: tuple[ProviderFieldPayload, ...]
    trace_id: str | None = "trace-fake-001"
    provider_name: str | None = "fake-provider"
    seen_run_id: str | None = None
    expected_page_nums: tuple[int, ...] = (0,)
    provider_model: str | None = None
    usage_metadata: ProviderUsageMetadata | None = None

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        assert document.doc_id == "doc-001"
        assert tuple(page.page_num for page in pages) == self.expected_page_nums
        self.seen_run_id = run_id
        return ProviderExtractionResult(
            fields=self.fields,
            trace_id=self.trace_id,
            provider_name=self.provider_name,
            provider_model=self.provider_model,
            usage_metadata=self.usage_metadata,
        )


@dataclass
class FakeTraceContext:
    updates: list[dict[str, Any]]
    raise_on_update: bool = False

    def update_current_trace(self, **kwargs: Any) -> None:
        if self.raise_on_update:
            raise RuntimeError("trace backend unavailable with SECRET_TRACE_TOKEN_SHOULD_NOT_APPEAR")
        self.updates.append(kwargs)


class ExplodingProvider:
    provider_name = "exploding-provider"
    seen_run_id: str | None = None

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        self.seen_run_id = run_id
        raise RuntimeError("SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR raw response text")


class TypedExplodingProvider(ExplodingProvider):
    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        self.seen_run_id = run_id
        raise ExtractionProviderError("SECRET_TYPED_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR")


class MalformedProvider:
    provider_name = "malformed-provider"

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> object:
        return object()


def provider_field(
    field_name: SDFFieldName,
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: str | None = None,
    confidence: float = 0.9,
    span: str | None = None,
    page_num: int = 0,
) -> ProviderFieldPayload:
    return ProviderFieldPayload(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        normalized_date=normalized_date,
        confidence=confidence,
        evidence=ProviderSourceEvidence(
            page_num=page_num,
            verbatim_span=span or raw_value,
            bbox={"x": 10, "y": 20, "width": 160, "height": 24},
        ),
    )


def all_fields(overrides: dict[SDFFieldName, ProviderFieldPayload] | None = None) -> tuple[ProviderFieldPayload, ...]:
    fields = {
        SDFFieldName.DOC_TYPE: provider_field(
            SDFFieldName.DOC_TYPE,
            "Supplier Declaration Form",
            normalized_value="SDF",
            confidence=0.96,
        ),
        SDFFieldName.VENDOR_NAME: provider_field(
            SDFFieldName.VENDOR_NAME,
            "Acme Pharma Ltd.",
            confidence=0.94,
        ),
        SDFFieldName.MANUFACTURING_DATE: provider_field(
            SDFFieldName.MANUFACTURING_DATE,
            "2024-01-05",
            normalized_date="2024-01-05",
            confidence=0.91,
        ),
        SDFFieldName.EFFECTIVE_DATE: provider_field(
            SDFFieldName.EFFECTIVE_DATE,
            "2024-02-01",
            normalized_date="2024-02-01",
            confidence=0.9,
        ),
        SDFFieldName.REVISION_DATE: provider_field(
            SDFFieldName.REVISION_DATE,
            "2024-03-15",
            normalized_date="2024-03-15",
            confidence=0.88,
        ),
        SDFFieldName.EXPIRY_DATE: provider_field(
            SDFFieldName.EXPIRY_DATE,
            "2027-01-31",
            normalized_date="2027-01-31",
            confidence=0.93,
        ),
    }
    if overrides:
        fields.update(overrides)
    return tuple(fields[field_name] for field_name in SDFFieldName)


def prepare_doc(db_path: str, *, page_text: str | None = PAGE_TEXT, include_page: bool = True) -> None:
    init_db(db_path)
    insert_document(
        db_path,
        doc_id="doc-001",
        filename="supplier-sdf.pdf",
        file_path="/tmp/supplier-sdf.pdf",
        page_count=1,
        docling_json=None,
    )
    if include_page:
        insert_page(db_path, doc_id="doc-001", page_num=0, page_text=page_text, image_blob=None)
    else:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM pages WHERE doc_id = ?", ("doc-001",))
            conn.commit()
        finally:
            conn.close()


def extraction_count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM extractions WHERE doc_id = ?", ("doc-001",)).fetchone()[0]
    finally:
        conn.close()


def trace_metadata(fake_context: FakeTraceContext) -> list[dict[str, Any]]:
    return [update.get("metadata", {}) for update in fake_context.updates]


def assert_extraction_trace_metadata_is_safe(metadata: dict[str, Any]) -> None:
    forbidden_fragments = {
        "SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR",
        "SECRET_TRACE_TOKEN_SHOULD_NOT_APPEAR",
        "raw response text",
        "Document metadata was not found",
        "Provider did not return",
        "Acme Pharma Ltd.",
        "2027-01-31",
        "Supplier Declaration Form",
        "verbatim_span",
        "raw_value",
        "normalized_value",
        "file_path",
        "supplier-sdf.pdf",
    }
    metadata_repr = repr(metadata)
    for fragment in forbidden_fragments:
        assert_not_exposed(fragment, metadata_repr)


def assert_not_exposed(fragment: str, content: str) -> None:
    if fragment in content:
        raise AssertionError("forbidden content was exposed")


def test_load_document_pages_preserves_ordered_zero_indexed_pages(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)

    loaded = load_document_pages(tmp_db_path, "doc-001")

    assert loaded is not None
    assert loaded.document.filename == "supplier-sdf.pdf"
    assert [page.page_num for page in loaded.pages] == [0]
    assert loaded.pages[0].page_text == PAGE_TEXT
    assert loaded.pages[0].image_blob is None


def test_extract_document_fake_provider_persists_fields_compliance_risk_and_run_metadata(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = FakeProvider(fields=all_fields())

    result = extract_document(
        tmp_db_path,
        "doc-001",
        provider,
        today=date(2026, 1, 6),
        run_id="run-offline-001",
    )

    assert provider.seen_run_id == "run-offline-001"
    assert result.diagnostics.run_id == "run-offline-001"
    assert result.diagnostics.trace_id == "trace-fake-001"
    assert result.diagnostics.page_count == 1
    assert result.diagnostics.needs_review is True
    assert result.record.risk_level == "amber"
    assert result.record.age_days == 732
    assert extraction_count(tmp_db_path) == 6

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert set(stored.fields) == set(SDFFieldName)
    assert stored.run_id == "run-offline-001"
    assert stored.trace_id == "trace-fake-001"
    assert stored.fields[SDFFieldName.VENDOR_NAME].evidence.verbatim_span == "Acme Pharma Ltd."
    assert stored.fields[SDFFieldName.MANUFACTURING_DATE].normalized_value == "2024-01-05"

    compliance = list_compliance_records(tmp_db_path)[0]
    assert compliance["doc_id"] == "doc-001"
    assert compliance["doc_type"] == "Supplier Declaration Form"
    assert compliance["vendor_name"] == "Acme Pharma Ltd."
    assert compliance["manufacturing_date"] == "2024-01-05"
    assert compliance["expiry_date"] == "2027-01-31"
    assert compliance["risk_level"] == "amber"
    assert compliance["compliance_status"] == "needs_review"
    assert compliance["needs_review"] == 1
    assert compliance["run_id"] == "run-offline-001"
    assert compliance["trace_id"] == "trace-fake-001"
    assert compliance["source_page"] == 0
    assert compliance["source_verbatim_span"] == "2027-01-31"


def test_text_pipeline_persists_full_model_and_thought_usage_provenance(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = FakeProvider(
        fields=all_fields(),
        provider_model="gemini-3.5-flash-preview-2026-06",
        usage_metadata=ProviderUsageMetadata(
            model="gemini-3.5-flash-preview-2026-06",
            requested_model="gemini-3.5-flash-preview",
            resolved_model="gemini-3.5-flash-preview-2026-06",
            pricing_model=None,
            input_tokens=101,
            output_tokens=17,
            thought_tokens=13,
            total_tokens=131,
            estimated_cost_usd=None,
        ),
    )

    extract_document(
        tmp_db_path,
        "doc-001",
        provider,
        today=date(2026, 1, 6),
        run_id="run-text-provenance",
    )

    row = list_extraction_usage_observations(
        tmp_db_path,
        run_id="run-text-provenance",
        stage="text_extraction",
    )[0]
    assert row.requested_model == "gemini-3.5-flash-preview"
    assert row.resolved_model == "gemini-3.5-flash-preview-2026-06"
    assert row.pricing_model is None
    assert row.input_tokens == 101
    assert row.output_tokens == 17
    assert row.thought_tokens == 13
    assert row.total_tokens == 131
    assert row.estimated_cost_usd is None
    assert list_extraction_run_summaries(tmp_db_path)[0].resolved_model == "gemini-3.5-flash-preview-2026-06"


def test_extract_document_success_updates_safe_trace_metadata(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.extraction import pipeline

    prepare_doc(tmp_db_path)
    fake_context = FakeTraceContext(updates=[])
    monkeypatch.setattr(pipeline, "langfuse_context", fake_context)

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields()),
        today=date(2026, 1, 6),
        run_id="run-trace-success",
    )

    assert result.diagnostics.review_state == "pending"
    assert len(fake_context.updates) == 1
    assert fake_context.updates[0]["tags"] == ["extraction"]
    metadata = trace_metadata(fake_context)[0]
    assert metadata == {
        "boundary": "extraction",
        "status": "completed",
        "run_id": "run-trace-success",
        "doc_id": "doc-001",
        "trace_id": "trace-fake-001",
        "provider_name": "fake-provider",
        "page_count": 1,
        "review_state": "pending",
        "needs_review": True,
    }
    assert_extraction_trace_metadata_is_safe(metadata)


def test_extract_document_missing_document_updates_sanitized_error_trace(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.extraction import pipeline

    init_db(tmp_db_path)
    fake_context = FakeTraceContext(updates=[])
    monkeypatch.setattr(pipeline, "langfuse_context", fake_context)

    with pytest.raises(DocumentNotFoundError):
        extract_document(tmp_db_path, "missing-doc", FakeProvider(fields=all_fields()), run_id="run-missing-doc")

    metadata = trace_metadata(fake_context)[0]
    assert metadata == {
        "boundary": "extraction",
        "status": "error",
        "run_id": "run-missing-doc",
        "doc_id": "missing-doc",
        "error_class": "DocumentNotFoundError",
        "reason_code": "document_not_found",
    }
    assert_extraction_trace_metadata_is_safe(metadata)


def test_extract_document_page_failures_update_sanitized_error_trace(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.extraction import pipeline

    fake_context = FakeTraceContext(updates=[])
    monkeypatch.setattr(pipeline, "langfuse_context", fake_context)
    provider = FakeProvider(fields=all_fields())

    prepare_doc(tmp_db_path, include_page=False)
    with pytest.raises(NoPagesError):
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-no-pages-trace")

    assert trace_metadata(fake_context)[0] == {
        "boundary": "extraction",
        "status": "error",
        "run_id": "run-no-pages-trace",
        "doc_id": "doc-001",
        "error_class": "NoPagesError",
        "reason_code": "no_pages",
    }
    assert provider.seen_run_id is None

    fake_context.updates.clear()
    prepare_doc(tmp_db_path, page_text="   ")
    with pytest.raises(NoPageTextError):
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-no-text-trace")

    assert trace_metadata(fake_context)[0] == {
        "boundary": "extraction",
        "status": "error",
        "run_id": "run-no-text-trace",
        "doc_id": "doc-001",
        "error_class": "NoPageTextError",
        "reason_code": "no_page_text",
    }
    for metadata in trace_metadata(fake_context):
        assert_extraction_trace_metadata_is_safe(metadata)


def test_extract_document_provider_exception_trace_metadata_omits_secret_message(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.extraction import pipeline

    prepare_doc(tmp_db_path)
    fake_context = FakeTraceContext(updates=[])
    monkeypatch.setattr(pipeline, "langfuse_context", fake_context)
    provider = ExplodingProvider()

    with pytest.raises(ProviderInvocationError) as exc_info:
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-provider-error")

    assert_not_exposed("SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR", str(exc_info.value))
    assert exc_info.value.__cause__ is None
    assert provider.seen_run_id == "run-provider-error"
    metadata = trace_metadata(fake_context)[0]
    assert metadata == {
        "boundary": "extraction",
        "status": "error",
        "run_id": "run-provider-error",
        "doc_id": "doc-001",
        "error_class": "ProviderInvocationError",
        "reason_code": "provider_invocation_failed",
    }
    assert_extraction_trace_metadata_is_safe(metadata)


def test_typed_provider_exception_is_also_reduced_to_the_safe_boundary(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    provider = TypedExplodingProvider()

    with pytest.raises(ProviderInvocationError) as exc_info:
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-typed-provider-error")

    assert_not_exposed("SECRET_TYPED_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR", str(exc_info.value))
    assert exc_info.value.__cause__ is None
    assert provider.seen_run_id == "run-typed-provider-error"


def test_extract_document_validation_failure_trace_metadata_is_sanitized(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.extraction import pipeline

    prepare_doc(tmp_db_path)
    fake_context = FakeTraceContext(updates=[])
    monkeypatch.setattr(pipeline, "langfuse_context", fake_context)

    with pytest.raises(ProviderOutputError) as exc_info:
        extract_document(tmp_db_path, "doc-001", MalformedProvider(), run_id="run-malformed-provider")  # type: ignore[arg-type]

    assert exc_info.value.__cause__ is None
    metadata = trace_metadata(fake_context)[0]
    assert metadata == {
        "boundary": "extraction",
        "status": "error",
        "run_id": "run-malformed-provider",
        "doc_id": "doc-001",
        "error_class": "ProviderOutputError",
        "reason_code": "provider_output_invalid",
    }
    assert_extraction_trace_metadata_is_safe(metadata)


def test_extract_document_trace_context_failure_does_not_change_success_or_error_behavior(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.extraction import pipeline

    prepare_doc(tmp_db_path)
    failing_context = FakeTraceContext(updates=[], raise_on_update=True)
    monkeypatch.setattr(pipeline, "langfuse_context", failing_context)

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields()),
        today=date(2026, 1, 6),
        run_id="run-trace-failure-success",
    )

    assert result.diagnostics.run_id == "run-trace-failure-success"
    assert result.record.doc_id == "doc-001"
    assert failing_context.updates == []

    with pytest.raises(ProviderInvocationError):
        extract_document(tmp_db_path, "doc-001", ExplodingProvider(), run_id="run-trace-failure-error")
    assert failing_context.updates == []


def test_missing_provider_field_becomes_abstention_and_needs_review(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    fields = tuple(field for field in all_fields() if field.field_name != SDFFieldName.REVISION_DATE)

    extract_document(tmp_db_path, "doc-001", FakeProvider(fields=fields), today=date(2026, 1, 1))

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    revision = stored.fields[SDFFieldName.REVISION_DATE]
    assert revision.review_state == ReviewState.ABSTAINED
    assert revision.abstention_reason == "Provider did not return this required SDF field."
    assert list_compliance_records(tmp_db_path)[0]["needs_review"] == 1


def test_span_mismatch_abstains_instead_of_persisting_confident_fact(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    mismatched = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Acme Pharma Ltd.",
        span="A different supplier name that is not on the page",
        confidence=0.99,
    )

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: mismatched})),
        today=date(2026, 1, 1),
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    vendor = stored.fields[SDFFieldName.VENDOR_NAME]
    assert vendor.review_state == ReviewState.ABSTAINED
    assert vendor.raw_value is None
    assert vendor.abstention_reason == "Provider source span was not found in the cited page text."


def test_low_confidence_boundary_marks_only_below_threshold_for_review(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    low = provider_field(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd.", confidence=0.749)
    boundary = provider_field(SDFFieldName.DOC_TYPE, "Supplier Declaration Form", normalized_value="SDF", confidence=0.75)

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: low, SDFFieldName.DOC_TYPE: boundary})),
        today=date(2026, 1, 1),
        low_confidence_threshold=0.75,
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert stored.fields[SDFFieldName.VENDOR_NAME].review_state == ReviewState.NEEDS_REVIEW
    assert stored.fields[SDFFieldName.DOC_TYPE].review_state == ReviewState.PENDING


def test_invalid_page_number_abstains_field(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    invalid_page = provider_field(SDFFieldName.EXPIRY_DATE, "2027-01-31", normalized_date="2027-01-31", page_num=3)

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EXPIRY_DATE: invalid_page})),
        today=date(2026, 1, 1),
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    expiry = stored.fields[SDFFieldName.EXPIRY_DATE]
    assert expiry.review_state == ReviewState.ABSTAINED
    assert expiry.abstention_reason == "Provider cited a page number that was not persisted for this document."


def test_invalid_bbox_shape_abstains_field_without_crashing(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    invalid_bbox = ProviderFieldPayload(
        field_name=SDFFieldName.VENDOR_NAME,
        raw_value="Acme Pharma Ltd.",
        confidence=0.99,
        evidence=ProviderSourceEvidence(
            page_num=0,
            verbatim_span="Acme Pharma Ltd.",
            bbox={"bad": object()},
        ),
    )

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: invalid_bbox})),
        today=date(2026, 1, 1),
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    vendor = stored.fields[SDFFieldName.VENDOR_NAME]
    assert vendor.review_state == ReviewState.ABSTAINED
    assert vendor.evidence.bbox is None
    assert vendor.abstention_reason == "Provider returned a non-JSON-serializable source bounding box."


def test_placeholder_values_are_abstained_instead_of_persisted(tmp_db_path: str) -> None:
    page_text = PAGE_TEXT + "\nManufacturing Date: MMM/YYYY\nBatch Number: XXXXXXX\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    placeholder = provider_field(
        SDFFieldName.MANUFACTURING_DATE,
        "MMM/YYYY",
        span="Manufacturing Date: MMM/YYYY",
        confidence=0.99,
    )

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.MANUFACTURING_DATE: placeholder})),
        today=date(2026, 1, 1),
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    manufacturing = stored.fields[SDFFieldName.MANUFACTURING_DATE]
    assert manufacturing.review_state == ReviewState.ABSTAINED
    assert manufacturing.raw_value is None
    assert manufacturing.abstention_reason == "Provider returned a placeholder/redacted value rather than a real field value."


def test_delivery_date_is_not_accepted_as_effective_date(tmp_db_path: str) -> None:
    page_text = PAGE_TEXT + "\nDelivery Date: 04/17/2025\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    delivery_as_effective = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        "2025-04-17",
        normalized_date="2025-04-17",
        span="Delivery Date: 04/17/2025",
        confidence=0.99,
    )

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: delivery_as_effective})),
        today=date(2026, 1, 1),
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    effective = stored.fields[SDFFieldName.EFFECTIVE_DATE]
    assert effective.review_state == ReviewState.ABSTAINED
    assert effective.raw_value is None
    assert effective.abstention_reason == "Provider mapped Delivery Date to effective_date, but delivery dates are not effective dates."


def test_retest_date_is_not_accepted_as_expiry_date(tmp_db_path: str) -> None:
    page_text = PAGE_TEXT + "\nRetest Date: 29FEB2028\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    retest_as_expiry = provider_field(
        SDFFieldName.EXPIRY_DATE,
        "2028-02-29",
        normalized_date="2028-02-29",
        span="Retest Date: 29FEB2028",
        confidence=0.99,
    )

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EXPIRY_DATE: retest_as_expiry})),
        today=date(2026, 1, 1),
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    expiry = stored.fields[SDFFieldName.EXPIRY_DATE]
    assert expiry.review_state == ReviewState.ABSTAINED
    assert expiry.raw_value is None
    assert expiry.abstention_reason == "Provider mapped Retest Date to expiry_date, but retest dates are not expiry dates."


def test_explicit_not_applicable_expiry_value_is_still_allowed(tmp_db_path: str) -> None:
    page_text = PAGE_TEXT + "\nExpiration Date: N/A\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    not_applicable_expiry = provider_field(
        SDFFieldName.EXPIRY_DATE,
        "N/A",
        normalized_value="N/A",
        span="Expiration Date: N/A",
        confidence=0.99,
    )

    extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EXPIRY_DATE: not_applicable_expiry})),
        today=date(2026, 1, 1),
    )

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    expiry = stored.fields[SDFFieldName.EXPIRY_DATE]
    assert expiry.review_state == ReviewState.PENDING
    assert expiry.value_for_dashboard == "N/A"


def test_empty_page_text_returns_typed_failure_without_provider_call(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path, page_text="   ")
    provider = FakeProvider(fields=all_fields())

    with pytest.raises(NoPageTextError) as exc_info:
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-empty-text")

    assert exc_info.value.reason_code == "no_page_text"
    assert exc_info.value.run_id == "run-empty-text"
    assert provider.seen_run_id is None


def test_no_pages_returns_typed_failure_without_provider_call(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path, include_page=False)
    provider = FakeProvider(fields=all_fields())

    with pytest.raises(NoPagesError) as exc_info:
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-no-pages")

    assert exc_info.value.reason_code == "no_pages"
    assert exc_info.value.run_id == "run-no-pages"
    assert provider.seen_run_id is None


@pytest.mark.parametrize("provider_span", ["acme pharma ltd.", "Acme   Pharma Ltd."])
def test_text_grounding_rejects_case_or_whitespace_only_matches(
    tmp_db_path: str,
    provider_span: str,
) -> None:
    prepare_doc(tmp_db_path)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Acme Pharma Ltd.",
        span=provider_span,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    vendor = result.record.fields[SDFFieldName.VENDOR_NAME]
    assert vendor.review_state is ReviewState.ABSTAINED
    assert vendor.evidence.verbatim_span is None


def test_exact_but_unrelated_span_cannot_support_a_different_raw_value(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Fabricated Vendor LLC",
        span="Supplier Declaration Form",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


def test_provider_normalized_vendor_cannot_replace_the_printed_grounded_value(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Acme Pharma Ltd.",
        normalized_value="Fabricated Vendor LLC",
        span="Vendor Name: Acme Pharma Ltd.",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    vendor = result.record.fields[SDFFieldName.VENDOR_NAME]
    assert vendor.raw_value == "Acme Pharma Ltd."
    assert vendor.normalized_value == "Acme Pharma Ltd."
    assert vendor.value_for_dashboard == "Acme Pharma Ltd."


def test_issued_by_is_an_explicit_primary_vendor_label(tmp_db_path: str) -> None:
    page_text = "Certificate of Quality\nIssued by Acme Pharma Ltd.\nManufacturing Date: 2024-01-01"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Acme Pharma Ltd.",
        span="Issued by Acme Pharma Ltd.",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.PENDING


def test_page_citation_disambiguates_a_value_repeated_on_another_packet_page(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=1,
        page_text="Email attachment footer: Acme Pharma Ltd.",
        image_blob=None,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields(), expected_page_nums=(0, 1)),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.PENDING


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("2024-01-31", date(2024, 1, 31)),
        ("2024/01/31", date(2024, 1, 31)),
        ("2024.01.31", date(2024, 1, 31)),
        ("31/01/2024", date(2024, 1, 31)),
        ("01/31/2024", date(2024, 1, 31)),
        ("31-JAN-2024", date(2024, 1, 31)),
        ("31JAN2024", date(2024, 1, 31)),
        ("20240131", date(2024, 1, 31)),
        ("Jan 31, 2024", date(2024, 1, 31)),
    ],
)
def test_allowlisted_pharmaceutical_dates_preserve_raw_and_normalize_locally(
    tmp_db_path: str,
    printed: str,
    expected: date,
) -> None:
    page_text = PAGE_TEXT.replace("Effective Date: 2024-02-01", f"Approved On: {printed}")
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        printed,
        normalized_date="2099-12-31",
        span=f"Approved On: {printed}",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    effective = result.record.fields[SDFFieldName.EFFECTIVE_DATE]
    assert effective.raw_value == printed
    assert effective.normalized_date == expected
    assert effective.evidence.verbatim_span == f"Approved On: {printed}"


def test_partial_year_month_is_preserved_without_inventing_a_day(tmp_db_path: str) -> None:
    printed = "2024-01"
    prepare_doc(
        tmp_db_path,
        page_text=PAGE_TEXT.replace("Effective Date: 2024-02-01", f"Approved On: {printed}"),
    )
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        printed,
        span=f"Approved On: {printed}",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    effective = result.record.fields[SDFFieldName.EFFECTIVE_DATE]
    assert effective.raw_value == printed
    assert effective.normalized_value == printed
    assert effective.normalized_date is None
    assert effective.review_state is ReviewState.NEEDS_REVIEW


@pytest.mark.parametrize("printed", ["01/2024", "JAN 2024"])
def test_pharmaceutical_month_granularity_normalizes_without_inventing_a_day(
    tmp_db_path: str,
    printed: str,
) -> None:
    prepare_doc(
        tmp_db_path,
        page_text=PAGE_TEXT.replace("Effective Date: 2024-02-01", f"Approved On: {printed}"),
    )
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        printed,
        span=f"Approved On: {printed}",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    effective = result.record.fields[SDFFieldName.EFFECTIVE_DATE]
    assert effective.raw_value == printed
    assert effective.normalized_value == "2024-01"
    assert effective.normalized_date is None
    assert effective.review_state is ReviewState.NEEDS_REVIEW


def test_ambiguous_numeric_date_abstains_instead_of_guessing(tmp_db_path: str) -> None:
    printed = "01/02/2024"
    prepare_doc(
        tmp_db_path,
        page_text=PAGE_TEXT.replace("Effective Date: 2024-02-01", f"Issue Date: {printed}"),
    )
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        printed,
        normalized_date="2024-01-02",
        span=f"Issue Date: {printed}",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EFFECTIVE_DATE].review_state is ReviewState.ABSTAINED


def test_mixed_date_separators_abstain_instead_of_expanding_the_allowlist(tmp_db_path: str) -> None:
    printed = "2024-01/31"
    prepare_doc(
        tmp_db_path,
        page_text=PAGE_TEXT.replace("Effective Date: 2024-02-01", f"Issue Date: {printed}"),
    )
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        printed,
        span=f"Issue Date: {printed}",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EFFECTIVE_DATE].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("field_name", "packet_section", "raw_value"),
    [
        (SDFFieldName.EFFECTIVE_DATE, "From: buyer@example.test\nSent: 2025-04-17", "2025-04-17"),
        (SDFFieldName.REVISION_DATE, "Safety Data Sheet\nRevision Date: 2025-04-17", "2025-04-17"),
        (SDFFieldName.EFFECTIVE_DATE, "Processing Record\nEffective Date: 2025-04-17", "2025-04-17"),
        (SDFFieldName.REVISION_DATE, "Template Release Date: 2025-04-17", "2025-04-17"),
        (SDFFieldName.REVISION_DATE, "Handwritten Note Date: 2025-04-17", "2025-04-17"),
        (SDFFieldName.REVISION_DATE, "Unrelated Attachment Date: 2025-04-17", "2025-04-17"),
    ],
)
def test_packet_trap_dates_abstain_even_when_the_span_is_literal(
    tmp_db_path: str,
    field_name: SDFFieldName,
    packet_section: str,
    raw_value: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=PAGE_TEXT + "\n" + packet_section + "\n")
    candidate = provider_field(
        field_name,
        raw_value,
        normalized_date=raw_value,
        span=packet_section,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({field_name: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[field_name].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("field_name", "decoy_line"),
    [
        (SDFFieldName.EFFECTIVE_DATE, "Delivery Date: 2025-04-17"),
        (SDFFieldName.EXPIRY_DATE, "Retest Date: 2025-04-17"),
        (SDFFieldName.EFFECTIVE_DATE, "Sent: 2025-04-17"),
    ],
)
def test_value_only_decoy_cannot_borrow_a_nearby_valid_certificate_label(
    tmp_db_path: str,
    field_name: SDFFieldName,
    decoy_line: str,
) -> None:
    page_text = PAGE_TEXT + f"\nCertificate of Analysis\n{decoy_line}\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        field_name,
        "2025-04-17",
        span="2025-04-17",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({field_name: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[field_name].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("field_name", "page_text", "raw_value", "span"),
    [
        (
            SDFFieldName.REVISION_DATE,
            "Internal Calibration Report\nRevision Date: 2025-01-01",
            "2025-01-01",
            "Revision Date: 2025-01-01",
        ),
        (
            SDFFieldName.REVISION_DATE,
            "Certificate of Analysis\nSafety Data Sheet\nRevision Date: 2025-01-01",
            "2025-01-01",
            "Revision Date: 2025-01-01",
        ),
        (
            SDFFieldName.EFFECTIVE_DATE,
            "Certificate of Analysis\nNot Effective Date: 2025-01-01",
            "2025-01-01",
            "Not Effective Date: 2025-01-01",
        ),
        (
            SDFFieldName.VENDOR_NAME,
            "Certificate of Analysis\nEmail signature\nVendor: Outside LLC",
            "Outside LLC",
            "Vendor: Outside LLC",
        ),
    ],
)
def test_nonprimary_or_negated_claims_abstain_for_every_field_scope(
    tmp_db_path: str,
    field_name: SDFFieldName,
    page_text: str,
    raw_value: str,
    span: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(field_name, raw_value, span=span, confidence=0.99)

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({field_name: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[field_name].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("field_name", "raw_value", "span"),
    [
        (SDFFieldName.VENDOR_NAME, "Acme", "Vendor Name: Acme Pharma Ltd."),
        (SDFFieldName.DOC_TYPE, "Certificate", "Certificate of Analysis"),
    ],
)
def test_truncated_vendor_or_document_type_cannot_pass_substring_grounding(
    tmp_db_path: str,
    field_name: SDFFieldName,
    raw_value: str,
    span: str,
) -> None:
    page_text = f"Certificate of Analysis\nVendor Name: Acme Pharma Ltd.\n{span}\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(field_name, raw_value, span=span, confidence=0.99)

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({field_name: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[field_name].review_state is ReviewState.ABSTAINED


def test_untrusted_placeholder_normalization_cannot_override_a_valid_printed_vendor(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Acme Pharma Ltd.",
        normalized_value="TBD",
        span="Vendor Name: Acme Pharma Ltd.",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.VENDOR_NAME].normalized_value == "Acme Pharma Ltd."


def test_custom_specification_establishes_primary_scope_after_email_metadata(tmp_db_path: str) -> None:
    page_text = (
        "From: sender@example.test\nSent via email\n"
        "Custom Specification SH3B21975\n"
        "Vendor Name: Acme Pharma Ltd.\n"
        "Effective Date: 2025-01-01\n"
    )
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        "2025-01-01",
        span="Effective Date: 2025-01-01",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EFFECTIVE_DATE].review_state is ReviewState.PENDING


def test_inline_specification_mention_inside_email_cannot_reopen_primary_scope(tmp_db_path: str) -> None:
    page_text = (
        "From: sender@example.test\n"
        "Please review the attached custom specification ABC.\n"
        "Effective Date: 2025-01-01\n"
    )
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        "2025-01-01",
        span="Effective Date: 2025-01-01",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EFFECTIVE_DATE].review_state is ReviewState.ABSTAINED


def test_processing_certificate_heading_closes_primary_certificate_scope(tmp_db_path: str) -> None:
    page_text = (
        "Certificate of Analysis\n"
        "Certificate of Processing\n"
        "Production Date: 2025-01-01\n"
    )
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.MANUFACTURING_DATE,
        "2025-01-01",
        span="Production Date: 2025-01-01",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.MANUFACTURING_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.MANUFACTURING_DATE].review_state is ReviewState.ABSTAINED


def test_sent_via_email_heading_closes_primary_certificate_scope(tmp_db_path: str) -> None:
    page_text = (
        "Certificate of Analysis\n"
        "Sent via email\n"
        "Effective Date: 2025-01-01\n"
    )
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        "2025-01-01",
        span="Effective Date: 2025-01-01",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EFFECTIVE_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EFFECTIVE_DATE].review_state is ReviewState.ABSTAINED


def test_primary_scope_carries_across_certificate_continuation_pages(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    insert_document(
        tmp_db_path,
        doc_id="doc-001",
        filename="multi-page-certificate.pdf",
        file_path="C:/confidential/multi-page-certificate.pdf",
        page_count=2,
        docling_json=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=0,
        page_text="Certificate of Analysis\nPage 1 of 2",
        image_blob=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=1,
        page_text="Expiry Date: 2027-01-01\nPage 2 of 2",
        image_blob=None,
    )
    candidate = provider_field(
        SDFFieldName.EXPIRY_DATE,
        "2027-01-01",
        normalized_date="2027-01-01",
        span="Expiry Date: 2027-01-01",
        page_num=1,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(
            fields=all_fields({SDFFieldName.EXPIRY_DATE: candidate}),
            expected_page_nums=(0, 1),
        ),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.PENDING


@pytest.mark.parametrize(
    ("heading", "field_name", "raw_value", "claim_line"),
    [
        pytest.param(
            "SDS",
            SDFFieldName.REVISION_DATE,
            "2025-01-01",
            "Revision Date: 2025-01-01",
            id="sds",
        ),
        pytest.param(
            "EMAIL",
            SDFFieldName.EFFECTIVE_DATE,
            "2025-01-01",
            "Effective Date: 2025-01-01",
            id="email",
        ),
        pytest.param(
            "Dosimetry Record",
            SDFFieldName.MANUFACTURING_DATE,
            "2025-01-01",
            "Production Date: 2025-01-01",
            id="dosimetry-record",
        ),
    ],
)
def test_inherited_nonprimary_heading_alias_closes_primary_scope(
    tmp_db_path: str,
    heading: str,
    field_name: SDFFieldName,
    raw_value: str,
    claim_line: str,
) -> None:
    init_db(tmp_db_path)
    insert_document(
        tmp_db_path,
        doc_id="doc-001",
        filename="packet.pdf",
        file_path="C:/confidential/packet.pdf",
        page_count=2,
        docling_json=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=0,
        page_text="Certificate of Analysis\nPage 1 of 2",
        image_blob=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=1,
        page_text=f"{heading}\n{claim_line}",
        image_blob=None,
    )
    candidate = provider_field(
        field_name,
        raw_value,
        span=claim_line,
        page_num=1,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(
            fields=all_fields({field_name: candidate}),
            expected_page_nums=(0, 1),
        ),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[field_name].review_state is ReviewState.ABSTAINED


def test_standalone_product_name_cannot_populate_vendor_name(tmp_db_path: str) -> None:
    page_text = "Certificate of Analysis\nProduct Name\nAspirin\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Aspirin",
        span="Aspirin",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


def test_standalone_signatory_cannot_populate_vendor_name(tmp_db_path: str) -> None:
    page_text = "Certificate of Analysis\nApproved By\nJane Smith\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Jane Smith",
        span="Jane Smith",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("decoy_label", "raw_value"),
    [
        pytest.param("Product Name", "Aspirin Pharma", id="product-name-corporate-token"),
        pytest.param("Approved By", "Jane Smith Quality Labs", id="approved-by-corporate-token"),
    ],
)
def test_split_row_vendor_decoy_overrides_corporate_identity_terms(
    tmp_db_path: str,
    decoy_label: str,
    raw_value: str,
) -> None:
    page_text = f"Certificate of Analysis\n{decoy_label}\n{raw_value}\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        raw_value,
        span=raw_value,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("decoy_label", "intervening_row", "raw_value"),
    [
        pytest.param(
            "Product Name",
            "Product Code",
            "Aspirin Pharma",
            id="product-name-with-product-code-row",
        ),
        pytest.param(
            "Approved By",
            "Title",
            "Jane Smith Quality Labs",
            id="approved-by-with-title-row",
        ),
    ],
)
def test_intervening_table_row_cannot_hide_vendor_decoy_label(
    tmp_db_path: str,
    decoy_label: str,
    intervening_row: str,
    raw_value: str,
) -> None:
    page_text = f"Certificate of Analysis\n{decoy_label}\n{intervening_row}\n{raw_value}\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        raw_value,
        span=raw_value,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


def test_full_flattened_table_header_row_cannot_hide_vendor_decoy_label(tmp_db_path: str) -> None:
    page_text = (
        "Certificate of Analysis\n"
        "Product Name\n"
        "Product Code\n"
        "CAS Number\n"
        "Lot Number\n"
        "Batch Number\n"
        "Aspirin Pharma\n"
    )
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Aspirin Pharma",
        span="Aspirin Pharma",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("claim_line", "raw_value"),
    [
        pytest.param("Product: Aspirin Pharma", "Aspirin Pharma", id="product"),
        pytest.param("Material: Quality Labs", "Quality Labs", id="material"),
        pytest.param("Item Name: Vaccine Pharma", "Vaccine Pharma", id="item-name"),
    ],
)
def test_direct_product_or_material_label_cannot_populate_vendor_name(
    tmp_db_path: str,
    claim_line: str,
    raw_value: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        raw_value,
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("claim_line", "raw_value"),
    [
        pytest.param("Testing Laboratory: Quality Labs", "Quality Labs", id="testing-laboratory"),
        pytest.param("Customer: Pfizer Inc.", "Pfizer Inc.", id="customer"),
        pytest.param("Distributor: Supply Pharma LLC", "Supply Pharma LLC", id="distributor"),
        pytest.param("Contract Laboratory: Analytical Labs", "Analytical Labs", id="contract-laboratory"),
        pytest.param("Certificate Holder: Sponsor Pharma Ltd.", "Sponsor Pharma Ltd.", id="certificate-holder"),
    ],
)
def test_nonvendor_organization_role_cannot_populate_vendor_name(
    tmp_db_path: str,
    claim_line: str,
    raw_value: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        raw_value,
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("claim_line", "attribute_tail"),
    [
        pytest.param(
            "Supplier Address: 123 Pharma Road",
            "Address: 123 Pharma Road",
            id="supplier-address",
        ),
        pytest.param("Vendor ID: ACME-42", "ID: ACME-42", id="vendor-id"),
        pytest.param(
            "Manufacturer Contact: Jane Smith",
            "Contact: Jane Smith",
            id="manufacturer-contact",
        ),
    ],
)
def test_reserved_vendor_attribute_tail_cannot_populate_vendor_name(
    tmp_db_path: str,
    claim_line: str,
    attribute_tail: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        attribute_tail,
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("claim_line", "product_value"),
    [
        pytest.param(
            "Aspirin Pharma manufactured by Acme Labs",
            "Aspirin Pharma",
            id="manufactured-by",
        ),
        pytest.param(
            "Vaccine Pharma produced at Acme Laboratories",
            "Vaccine Pharma",
            id="produced-at",
        ),
        pytest.param(
            "Material Aspirin Pharma assembled in a Quality Labs facility",
            "Aspirin Pharma",
            id="assembled-in-facility",
        ),
    ],
)
def test_product_before_manufacturing_relation_cannot_populate_vendor_name(
    tmp_db_path: str,
    claim_line: str,
    product_value: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        product_value,
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


def test_entity_after_manufacturing_relation_can_populate_vendor_name(tmp_db_path: str) -> None:
    claim_line = "Aspirin tablets manufactured by Acme Labs"
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Acme Labs",
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.PENDING


@pytest.mark.parametrize(
    ("claim_line", "truncated_value"),
    [
        pytest.param(
            "Aspirin tablets manufactured by Acme Labs LLC",
            "Acme Labs",
            id="llc-suffix",
        ),
        pytest.param(
            "Aspirin tablets produced at Acme Laboratories GmbH",
            "Acme Laboratories",
            id="gmbh-suffix",
        ),
    ],
)
def test_manufacturing_relation_requires_complete_legal_vendor_name(
    tmp_db_path: str,
    claim_line: str,
    truncated_value: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        truncated_value,
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("claim_line", "complete_value"),
    [
        pytest.param(
            "Aspirin tablets manufactured by Acme Labs LLC",
            "Acme Labs LLC",
            id="llc-suffix",
        ),
        pytest.param(
            "Aspirin tablets produced at Acme Laboratories GmbH",
            "Acme Laboratories GmbH",
            id="gmbh-suffix",
        ),
    ],
)
def test_manufacturing_relation_accepts_complete_legal_vendor_name(
    tmp_db_path: str,
    claim_line: str,
    complete_value: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        complete_value,
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.PENDING


def test_date_value_cannot_borrow_target_label_from_another_line(tmp_db_path: str) -> None:
    evidence_span = "Expiry Date: 2027-01-01\nShipping Date: 2030-01-01"
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{evidence_span}\n")
    candidate = provider_field(
        SDFFieldName.EXPIRY_DATE,
        "2030-01-01",
        normalized_date="2030-01-01",
        span=evidence_span,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EXPIRY_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


def test_split_row_date_cannot_use_value_from_a_competing_label(tmp_db_path: str) -> None:
    page_text = "Certificate of Analysis\nExpiry Date:\nShipping Date: 2030-01-01\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.EXPIRY_DATE,
        "2030-01-01",
        normalized_date="2030-01-01",
        span="Shipping Date: 2030-01-01",
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EXPIRY_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


def test_same_line_date_cannot_use_value_from_a_competing_label(tmp_db_path: str) -> None:
    claim_line = "Expiry Date: 2027-01-01 / Shipping Date: 2030-01-01"
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        SDFFieldName.EXPIRY_DATE,
        "2030-01-01",
        normalized_date="2030-01-01",
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.EXPIRY_DATE: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize(
    ("field_name", "claim_line"),
    [
        pytest.param(
            SDFFieldName.EXPIRY_DATE,
            "Previous Expiry Date: 2030-01-01",
            id="previous-expiry",
        ),
        pytest.param(
            SDFFieldName.EXPIRY_DATE,
            "Proposed Expiry Date: 2030-01-01",
            id="proposed-expiry",
        ),
        pytest.param(
            SDFFieldName.EFFECTIVE_DATE,
            "Proposed Effective Date: 2030-01-01",
            id="proposed-effective",
        ),
        pytest.param(
            SDFFieldName.REVISION_DATE,
            "Next Revision Date: 2030-01-01",
            id="next-revision",
        ),
        pytest.param(
            SDFFieldName.MANUFACTURING_DATE,
            "Planned Manufacturing Date: 2030-01-01",
            id="planned-manufacturing",
        ),
        pytest.param(
            SDFFieldName.EXPIRY_DATE,
            "Estimated Expiry Date: 2030-01-01",
            id="estimated-expiry",
        ),
        pytest.param(
            SDFFieldName.EXPIRY_DATE,
            "Tentative Expiry Date: 2030-01-01",
            id="tentative-expiry",
        ),
        pytest.param(
            SDFFieldName.EXPIRY_DATE,
            "Target Expiry Date: 2030-01-01",
            id="target-expiry",
        ),
        pytest.param(
            SDFFieldName.EFFECTIVE_DATE,
            "Scheduled Effective Date: 2030-01-01",
            id="scheduled-effective",
        ),
        pytest.param(
            SDFFieldName.MANUFACTURING_DATE,
            "Anticipated Manufacturing Date: 2030-01-01",
            id="anticipated-manufacturing",
        ),
    ],
)
def test_noncurrent_date_modifier_cannot_populate_current_certificate_field(
    tmp_db_path: str,
    field_name: SDFFieldName,
    claim_line: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"Certificate of Analysis\n{claim_line}\n")
    candidate = provider_field(
        field_name,
        "2030-01-01",
        normalized_date="2030-01-01",
        span=claim_line,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({field_name: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[field_name].review_state is ReviewState.ABSTAINED


def test_certificate_template_cannot_produce_a_compliant_record(tmp_db_path: str) -> None:
    page_text = (
        "Certificate of Analysis Template\n"
        "Vendor Name: Example Pharma LLC\n"
        "Manufacturing Date: 2026-01-01\n"
        "Effective Date: 2026-01-02\n"
        "Revision Date: 2026-02-01\n"
        "Expiry Date: 2030-01-01\n"
    )
    prepare_doc(tmp_db_path, page_text=page_text)
    fields = all_fields(
        {
            SDFFieldName.DOC_TYPE: provider_field(
                SDFFieldName.DOC_TYPE,
                "Certificate of Analysis Template",
                span="Certificate of Analysis Template",
                confidence=0.99,
            ),
            SDFFieldName.VENDOR_NAME: provider_field(
                SDFFieldName.VENDOR_NAME,
                "Example Pharma LLC",
                span="Vendor Name: Example Pharma LLC",
                confidence=0.99,
            ),
            SDFFieldName.MANUFACTURING_DATE: provider_field(
                SDFFieldName.MANUFACTURING_DATE,
                "2026-01-01",
                normalized_date="2026-01-01",
                span="Manufacturing Date: 2026-01-01",
                confidence=0.99,
            ),
            SDFFieldName.EFFECTIVE_DATE: provider_field(
                SDFFieldName.EFFECTIVE_DATE,
                "2026-01-02",
                normalized_date="2026-01-02",
                span="Effective Date: 2026-01-02",
                confidence=0.99,
            ),
            SDFFieldName.REVISION_DATE: provider_field(
                SDFFieldName.REVISION_DATE,
                "2026-02-01",
                normalized_date="2026-02-01",
                span="Revision Date: 2026-02-01",
                confidence=0.99,
            ),
            SDFFieldName.EXPIRY_DATE: provider_field(
                SDFFieldName.EXPIRY_DATE,
                "2030-01-01",
                normalized_date="2030-01-01",
                span="Expiry Date: 2030-01-01",
                confidence=0.99,
            ),
        }
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=fields),
        today=date(2026, 7, 15),
    )

    assert all(field.review_state is ReviewState.ABSTAINED for field in result.record.fields.values())
    assert result.record.risk_level == "unknown"
    assert result.record.compliance_status == "needs_review"


def test_specification_changes_heading_cannot_open_primary_scope(tmp_db_path: str) -> None:
    page_text = "Specification Changes\nExpiry Date: 2030-01-01\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    fields = all_fields(
        {
            SDFFieldName.DOC_TYPE: provider_field(
                SDFFieldName.DOC_TYPE,
                "Specification Changes",
                span="Specification Changes",
                confidence=0.99,
            ),
            SDFFieldName.EXPIRY_DATE: provider_field(
                SDFFieldName.EXPIRY_DATE,
                "2030-01-01",
                normalized_date="2030-01-01",
                span="Expiry Date: 2030-01-01",
                confidence=0.99,
            ),
        }
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=fields),
        today=date(2026, 7, 15),
    )

    assert result.record.fields[SDFFieldName.DOC_TYPE].review_state is ReviewState.ABSTAINED
    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize("heading", ["Specification SPEC-123", "Specification 12345"])
def test_identifier_suffixed_specification_remains_a_primary_document(
    tmp_db_path: str,
    heading: str,
) -> None:
    prepare_doc(tmp_db_path, page_text=f"{heading}\n")
    candidate = provider_field(
        SDFFieldName.DOC_TYPE,
        heading,
        span=heading,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.DOC_TYPE: candidate})),
        today=date(2026, 7, 15),
    )

    assert result.record.fields[SDFFieldName.DOC_TYPE].review_state is ReviewState.PENDING


def test_fields_from_a_second_primary_certificate_cannot_mix_with_selected_doc_type(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    insert_document(
        tmp_db_path,
        doc_id="doc-001",
        filename="multiple-certificates.pdf",
        file_path="C:/confidential/multiple-certificates.pdf",
        page_count=2,
        docling_json=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=0,
        page_text=(
            "Certificate of Analysis\n"
            "Manufacturing Date: 2025-01-01\n"
            "Effective Date: 2025-01-02\n"
            "Revision Date: 2025-01-03\n"
            "Expiry Date: 2027-01-01\n"
        ),
        image_blob=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=1,
        page_text="Certificate of Quality\nVendor Name: Supporting Labs LLC\n",
        image_blob=None,
    )
    fields = all_fields(
        {
            SDFFieldName.DOC_TYPE: provider_field(
                SDFFieldName.DOC_TYPE,
                "Certificate of Analysis",
                span="Certificate of Analysis",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.VENDOR_NAME: provider_field(
                SDFFieldName.VENDOR_NAME,
                "Supporting Labs LLC",
                span="Vendor Name: Supporting Labs LLC",
                page_num=1,
                confidence=0.99,
            ),
            SDFFieldName.MANUFACTURING_DATE: provider_field(
                SDFFieldName.MANUFACTURING_DATE,
                "2025-01-01",
                normalized_date="2025-01-01",
                span="Manufacturing Date: 2025-01-01",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.EFFECTIVE_DATE: provider_field(
                SDFFieldName.EFFECTIVE_DATE,
                "2025-01-02",
                normalized_date="2025-01-02",
                span="Effective Date: 2025-01-02",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.REVISION_DATE: provider_field(
                SDFFieldName.REVISION_DATE,
                "2025-01-03",
                normalized_date="2025-01-03",
                span="Revision Date: 2025-01-03",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.EXPIRY_DATE: provider_field(
                SDFFieldName.EXPIRY_DATE,
                "2027-01-01",
                normalized_date="2027-01-01",
                span="Expiry Date: 2027-01-01",
                page_num=0,
                confidence=0.99,
            ),
        }
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=fields, expected_page_nums=(0, 1)),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.DOC_TYPE].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


def test_packing_list_heading_closes_inherited_primary_certificate_scope(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    insert_document(
        tmp_db_path,
        doc_id="doc-001",
        filename="certificate-with-packing-list.pdf",
        file_path="C:/confidential/certificate-with-packing-list.pdf",
        page_count=2,
        docling_json=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=0,
        page_text="Certificate of Analysis\nCertificate Number: COA-001\n",
        image_blob=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=1,
        page_text=(
            "PACKING LIST\n"
            "Vendor Name: Logistics Pharma LLC\n"
            "Expiry Date: 2030-01-01\n"
        ),
        image_blob=None,
    )
    fields = all_fields(
        {
            SDFFieldName.DOC_TYPE: provider_field(
                SDFFieldName.DOC_TYPE,
                "Certificate of Analysis",
                span="Certificate of Analysis",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.VENDOR_NAME: provider_field(
                SDFFieldName.VENDOR_NAME,
                "Logistics Pharma LLC",
                span="Vendor Name: Logistics Pharma LLC",
                page_num=1,
                confidence=0.99,
            ),
            SDFFieldName.EXPIRY_DATE: provider_field(
                SDFFieldName.EXPIRY_DATE,
                "2030-01-01",
                normalized_date="2030-01-01",
                span="Expiry Date: 2030-01-01",
                page_num=1,
                confidence=0.99,
            ),
        }
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=fields, expected_page_nums=(0, 1)),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.DOC_TYPE].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED
    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


def test_unrecognized_certificate_heading_closes_inherited_primary_scope(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    insert_document(
        tmp_db_path,
        doc_id="doc-001",
        filename="analysis-with-insurance-certificate.pdf",
        file_path="C:/confidential/analysis-with-insurance-certificate.pdf",
        page_count=2,
        docling_json=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=0,
        page_text="Certificate of Analysis\nCertificate Number: COA-001\n",
        image_blob=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=1,
        page_text=(
            "Certificate of Insurance\n"
            "Vendor Name: Insurer Pharma LLC\n"
            "Expiry Date: 2030-01-01\n"
        ),
        image_blob=None,
    )
    fields = all_fields(
        {
            SDFFieldName.DOC_TYPE: provider_field(
                SDFFieldName.DOC_TYPE,
                "Certificate of Analysis",
                span="Certificate of Analysis",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.VENDOR_NAME: provider_field(
                SDFFieldName.VENDOR_NAME,
                "Insurer Pharma LLC",
                span="Vendor Name: Insurer Pharma LLC",
                page_num=1,
                confidence=0.99,
            ),
            SDFFieldName.EXPIRY_DATE: provider_field(
                SDFFieldName.EXPIRY_DATE,
                "2030-01-01",
                normalized_date="2030-01-01",
                span="Expiry Date: 2030-01-01",
                page_num=1,
                confidence=0.99,
            ),
        }
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=fields, expected_page_nums=(0, 1)),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.DOC_TYPE].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED
    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


def test_different_primary_heading_on_same_page_starts_a_new_certificate_block(tmp_db_path: str) -> None:
    page_text = (
        "Certificate of Analysis\n"
        "Vendor Name: Primary Supplier LLC\n"
        "Certificate of Quality\n"
        "Expiry Date: 2030-01-01\n"
    )
    prepare_doc(tmp_db_path, page_text=page_text)
    fields = all_fields(
        {
            SDFFieldName.DOC_TYPE: provider_field(
                SDFFieldName.DOC_TYPE,
                "Certificate of Analysis",
                span="Certificate of Analysis",
                confidence=0.99,
            ),
            SDFFieldName.VENDOR_NAME: provider_field(
                SDFFieldName.VENDOR_NAME,
                "Primary Supplier LLC",
                span="Vendor Name: Primary Supplier LLC",
                confidence=0.99,
            ),
            SDFFieldName.EXPIRY_DATE: provider_field(
                SDFFieldName.EXPIRY_DATE,
                "2030-01-01",
                normalized_date="2030-01-01",
                span="Expiry Date: 2030-01-01",
                confidence=0.99,
            ),
        }
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=fields),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.DOC_TYPE].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


def test_repeated_primary_heading_on_later_page_requires_continuation_evidence(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    insert_document(
        tmp_db_path,
        doc_id="doc-001",
        filename="two-analysis-certificates.pdf",
        file_path="C:/confidential/two-analysis-certificates.pdf",
        page_count=2,
        docling_json=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=0,
        page_text=(
            "Certificate of Analysis\n"
            "Certificate Number: COA-001\n"
            "Page 1 of 1\n"
            "Vendor Name: Primary Supplier LLC\n"
        ),
        image_blob=None,
    )
    insert_page(
        tmp_db_path,
        doc_id="doc-001",
        page_num=1,
        page_text=(
            "Certificate of Analysis\n"
            "Certificate Number: COA-002\n"
            "Page 1 of 1\n"
            "Expiry Date: 2030-01-01\n"
        ),
        image_blob=None,
    )
    fields = all_fields(
        {
            SDFFieldName.DOC_TYPE: provider_field(
                SDFFieldName.DOC_TYPE,
                "Certificate of Analysis",
                span="Certificate of Analysis",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.VENDOR_NAME: provider_field(
                SDFFieldName.VENDOR_NAME,
                "Primary Supplier LLC",
                span="Vendor Name: Primary Supplier LLC",
                page_num=0,
                confidence=0.99,
            ),
            SDFFieldName.EXPIRY_DATE: provider_field(
                SDFFieldName.EXPIRY_DATE,
                "2030-01-01",
                normalized_date="2030-01-01",
                span="Expiry Date: 2030-01-01",
                page_num=1,
                confidence=0.99,
            ),
        }
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=fields, expected_page_nums=(0, 1)),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.DOC_TYPE].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.PENDING
    assert result.record.fields[SDFFieldName.EXPIRY_DATE].review_state is ReviewState.ABSTAINED


def test_valid_primary_certificate_date_survives_email_decoy_in_same_packet(tmp_db_path: str) -> None:
    valid_span = "Certificate of Analysis\nDate of Issue: 2024-05-22"
    page_text = PAGE_TEXT + "\nFrom: buyer@example.test\nSent: 2025-04-17\n" + valid_span + "\n"
    prepare_doc(tmp_db_path, page_text=page_text)
    candidate = provider_field(
        SDFFieldName.EFFECTIVE_DATE,
        "2024-05-22",
        normalized_date="2024-05-22",
        span=valid_span,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(
            fields=all_fields(
                {
                    SDFFieldName.DOC_TYPE: provider_field(
                        SDFFieldName.DOC_TYPE,
                        "Certificate of Analysis",
                        span="Certificate of Analysis",
                        confidence=0.99,
                    ),
                    SDFFieldName.EFFECTIVE_DATE: candidate,
                }
            )
        ),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.EFFECTIVE_DATE].normalized_date == date(2024, 5, 22)


def test_nonfinite_provider_confidence_abstains(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path)
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Acme Pharma Ltd.",
        confidence=float("nan"),
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(fields=all_fields({SDFFieldName.VENDOR_NAME: candidate})),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED


@pytest.mark.parametrize("threshold", [float("nan"), -0.01, 1.01, True])
def test_invalid_confidence_threshold_fails_before_provider_call(
    tmp_db_path: str,
    threshold: float,
) -> None:
    prepare_doc(tmp_db_path)
    provider = FakeProvider(fields=all_fields())

    with pytest.raises(InvalidConfidenceThresholdError) as exc_info:
        extract_document(
            tmp_db_path,
            "doc-001",
            provider,
            low_confidence_threshold=threshold,
            run_id="run-invalid-threshold",
        )

    assert exc_info.value.__cause__ is None
    assert provider.seen_run_id is None


def test_text_provider_cannot_promote_an_empty_page_claim_to_visual_evidence(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    insert_document(
        tmp_db_path,
        doc_id="doc-001",
        filename="mixed.pdf",
        file_path="C:/confidential/mixed.pdf",
        page_count=2,
        docling_json=None,
    )
    insert_page(tmp_db_path, doc_id="doc-001", page_num=0, page_text=PAGE_TEXT, image_blob=None)
    insert_page(tmp_db_path, doc_id="doc-001", page_num=1, page_text="", image_blob=b"image")
    candidate = provider_field(
        SDFFieldName.VENDOR_NAME,
        "Fabricated Vendor LLC",
        span="Fabricated Vendor LLC",
        page_num=1,
        confidence=0.99,
    )

    result = extract_document(
        tmp_db_path,
        "doc-001",
        FakeProvider(
            fields=all_fields({SDFFieldName.VENDOR_NAME: candidate}),
            expected_page_nums=(0, 1),
        ),
        today=date(2026, 1, 1),
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state is ReviewState.ABSTAINED
