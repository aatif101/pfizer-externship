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
from src.extraction.pipeline import DocumentNotFoundError, NoPagesError, NoPageTextError, extract_document
from src.extraction.providers import ProviderExtractionResult, ProviderFieldPayload, ProviderSourceEvidence
from src.extraction.repository import get_extraction_record, list_compliance_records


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

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        assert document.doc_id == "doc-001"
        assert [page.page_num for page in pages] == [0]
        self.seen_run_id = run_id
        return ProviderExtractionResult(fields=self.fields, trace_id=self.trace_id, provider_name=self.provider_name)


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
        assert fragment not in metadata_repr


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
    assert result.diagnostics.needs_review is False
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
    assert compliance["doc_type"] == "SDF"
    assert compliance["vendor_name"] == "Acme Pharma Ltd."
    assert compliance["manufacturing_date"] == "2024-01-05"
    assert compliance["expiry_date"] == "2027-01-31"
    assert compliance["risk_level"] == "amber"
    assert compliance["compliance_status"] == "needs_review"
    assert compliance["run_id"] == "run-offline-001"
    assert compliance["trace_id"] == "trace-fake-001"
    assert compliance["source_page"] == 0
    assert compliance["source_verbatim_span"] == "2027-01-31"


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
        "needs_review": False,
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

    with pytest.raises(RuntimeError, match="SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR"):
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-provider-error")

    assert provider.seen_run_id == "run-provider-error"
    metadata = trace_metadata(fake_context)[0]
    assert metadata == {
        "boundary": "extraction",
        "status": "error",
        "run_id": "run-provider-error",
        "doc_id": "doc-001",
        "error_class": "RuntimeError",
    }
    assert_extraction_trace_metadata_is_safe(metadata)


def test_extract_document_validation_failure_trace_metadata_is_sanitized(monkeypatch: Any, tmp_db_path: str) -> None:
    from src.extraction import pipeline

    prepare_doc(tmp_db_path)
    fake_context = FakeTraceContext(updates=[])
    monkeypatch.setattr(pipeline, "langfuse_context", fake_context)

    with pytest.raises(AttributeError):
        extract_document(tmp_db_path, "doc-001", MalformedProvider(), run_id="run-malformed-provider")  # type: ignore[arg-type]

    metadata = trace_metadata(fake_context)[0]
    assert metadata == {
        "boundary": "extraction",
        "status": "error",
        "run_id": "run-malformed-provider",
        "doc_id": "doc-001",
        "error_class": "AttributeError",
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

    with pytest.raises(RuntimeError, match="SECRET_PROVIDER_PAYLOAD_SHOULD_NOT_APPEAR"):
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


    prepare_doc(tmp_db_path, include_page=False)
    provider = FakeProvider(fields=all_fields())

    with pytest.raises(NoPagesError) as exc_info:
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-no-pages")

    assert exc_info.value.reason_code == "no_pages"
    assert exc_info.value.run_id == "run-no-pages"
    assert provider.seen_run_id is None


def test_empty_page_text_returns_typed_failure_without_provider_call(tmp_db_path: str) -> None:
    prepare_doc(tmp_db_path, page_text="   ")
    provider = FakeProvider(fields=all_fields())

    with pytest.raises(NoPageTextError) as exc_info:
        extract_document(tmp_db_path, "doc-001", provider, run_id="run-empty-text")

    assert exc_info.value.reason_code == "no_page_text"
    assert exc_info.value.run_id == "run-empty-text"
    assert provider.seen_run_id is None
