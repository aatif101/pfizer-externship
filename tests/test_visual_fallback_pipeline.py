"""Deterministic tests for targeted visual fallback extraction planning."""
from __future__ import annotations

from dataclasses import dataclass

from src.db.queries import DocumentMetadata, DocumentPage
from src.extraction.models import ExtractedField, ReviewState, SDFFieldName, SourceEvidence
from src.extraction.pipeline import (
    build_visual_fallback_request_plan,
    compute_visual_fallback_eligibility,
    extract_visual_fallback_candidates,
)
from src.extraction.providers import ProviderExtractionResult, VisualFallbackRequest


SECRET_FIELD_VALUE = "Acme Pharma Ltd."
SECRET_SPAN = "Vendor Name: Acme Pharma Ltd."
SECRET_PAGE_TEXT = "Supplier Declaration Form\nVendor Name: Acme Pharma Ltd."
IMAGE_BYTES = b"\x89PNG\r\n\x1a\nvisual-test-image"


def pending_field(field_name: SDFFieldName, *, confidence: float = 0.91) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        raw_value=SECRET_FIELD_VALUE,
        confidence=confidence,
        evidence=SourceEvidence(page_num=0, verbatim_span=SECRET_SPAN, bbox={"x": 1, "y": 2}),
        review_state=ReviewState.PENDING,
    )


def needs_review_field(field_name: SDFFieldName) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        raw_value=SECRET_FIELD_VALUE,
        confidence=0.32,
        evidence=SourceEvidence(page_num=0, verbatim_span=SECRET_SPAN, bbox={"x": 1, "y": 2}),
        review_state=ReviewState.NEEDS_REVIEW,
    )


def abstained_field(field_name: SDFFieldName) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        confidence=0.0,
        evidence=SourceEvidence(page_num=0),
        review_state=ReviewState.ABSTAINED,
        abstention_reason="Provider returned no source evidence for this required SDF field.",
    )


def all_pending_fields() -> dict[SDFFieldName, ExtractedField]:
    return {field_name: pending_field(field_name) for field_name in SDFFieldName}


def test_visual_fallback_eligibility_includes_only_abstained_and_needs_review_fields() -> None:
    fields = all_pending_fields()
    fields[SDFFieldName.VENDOR_NAME] = abstained_field(SDFFieldName.VENDOR_NAME)
    fields[SDFFieldName.EXPIRY_DATE] = needs_review_field(SDFFieldName.EXPIRY_DATE)

    eligibility = compute_visual_fallback_eligibility(fields)

    assert eligibility == {
        SDFFieldName.VENDOR_NAME: "field_abstained",
        SDFFieldName.EXPIRY_DATE: "field_needs_review",
    }
    assert SDFFieldName.DOC_TYPE not in eligibility
    assert SDFFieldName.MANUFACTURING_DATE not in eligibility


def test_visual_fallback_reason_codes_are_bounded_and_do_not_include_values_or_spans() -> None:
    fields = all_pending_fields()
    fields[SDFFieldName.VENDOR_NAME] = abstained_field(SDFFieldName.VENDOR_NAME)
    fields[SDFFieldName.EXPIRY_DATE] = needs_review_field(SDFFieldName.EXPIRY_DATE)

    reason_repr = repr(compute_visual_fallback_eligibility(fields))

    assert "field_abstained" in reason_repr
    assert "field_needs_review" in reason_repr
    assert SECRET_FIELD_VALUE not in reason_repr
    assert SECRET_SPAN not in reason_repr
    assert "Provider returned no source evidence" not in reason_repr


def test_visual_fallback_request_selects_only_image_backed_pages_and_eligible_field_names() -> None:
    fields = all_pending_fields()
    fields[SDFFieldName.VENDOR_NAME] = abstained_field(SDFFieldName.VENDOR_NAME)
    fields[SDFFieldName.REVISION_DATE] = needs_review_field(SDFFieldName.REVISION_DATE)
    pages = (
        DocumentPage(doc_id="doc-001", page_num=0, page_text=SECRET_PAGE_TEXT, image_blob=None),
        DocumentPage(doc_id="doc-001", page_num=1, page_text="Revision Date: 2024-03-15", image_blob=IMAGE_BYTES),
    )

    plan = build_visual_fallback_request_plan(fields, pages)

    assert plan.status == "ready"
    assert plan.reason_code is None
    assert plan.request is not None
    assert plan.request.eligible_field_names == (SDFFieldName.VENDOR_NAME, SDFFieldName.REVISION_DATE)
    assert plan.request.reason_codes == {
        SDFFieldName.VENDOR_NAME: "field_abstained",
        SDFFieldName.REVISION_DATE: "field_needs_review",
    }
    assert [page.page_num for page in plan.request.pages] == [1]
    assert all(page.image_blob is not None for page in plan.request.pages)


def test_visual_fallback_plan_skips_with_no_eligible_fields_and_no_provider_invocation() -> None:
    provider = ExplodingVisualProvider()

    outcome = extract_visual_fallback_candidates(
        document=document_metadata(),
        fields=all_pending_fields(),
        pages=(DocumentPage(doc_id="doc-001", page_num=0, page_text=SECRET_PAGE_TEXT, image_blob=IMAGE_BYTES),),
        run_id="run-visual-empty",
        visual_provider=provider,
    )

    assert outcome.plan.status == "skipped"
    assert outcome.plan.reason_code == "no_eligible_fields"
    assert outcome.provider_result is None
    assert provider.calls == 0


def test_visual_fallback_plan_skips_when_eligible_fields_have_no_page_images() -> None:
    fields = all_pending_fields()
    fields[SDFFieldName.VENDOR_NAME] = abstained_field(SDFFieldName.VENDOR_NAME)

    plan = build_visual_fallback_request_plan(
        fields,
        (DocumentPage(doc_id="doc-001", page_num=0, page_text=SECRET_PAGE_TEXT, image_blob=None),),
    )

    assert plan.status == "skipped"
    assert plan.reason_code == "missing_page_images"
    assert plan.request is None


def test_visual_fallback_plan_skips_when_provider_is_not_configured() -> None:
    fields = all_pending_fields()
    fields[SDFFieldName.VENDOR_NAME] = abstained_field(SDFFieldName.VENDOR_NAME)

    outcome = extract_visual_fallback_candidates(
        document=document_metadata(),
        fields=fields,
        pages=(DocumentPage(doc_id="doc-001", page_num=0, page_text=SECRET_PAGE_TEXT, image_blob=IMAGE_BYTES),),
        run_id="run-visual-unconfigured",
        visual_provider=None,
    )

    assert outcome.plan.status == "skipped"
    assert outcome.plan.reason_code == "not_configured"
    assert outcome.provider_result is None


def test_visual_fallback_provider_receives_bounded_request_when_configured() -> None:
    fields = all_pending_fields()
    fields[SDFFieldName.EXPIRY_DATE] = needs_review_field(SDFFieldName.EXPIRY_DATE)
    provider = RecordingVisualProvider()

    outcome = extract_visual_fallback_candidates(
        document=document_metadata(),
        fields=fields,
        pages=(DocumentPage(doc_id="doc-001", page_num=0, page_text=SECRET_PAGE_TEXT, image_blob=IMAGE_BYTES),),
        run_id="run-visual-ready",
        visual_provider=provider,
    )

    assert outcome.plan.status == "ready"
    assert outcome.provider_result == ProviderExtractionResult(fields=(), trace_id="trace-visual")
    assert provider.calls == 1
    assert provider.seen_run_id == "run-visual-ready"
    assert provider.seen_request is not None
    assert provider.seen_request.eligible_field_names == (SDFFieldName.EXPIRY_DATE,)
    assert provider.seen_request.reason_codes == {SDFFieldName.EXPIRY_DATE: "field_needs_review"}
    assert SECRET_PAGE_TEXT in (provider.seen_request.pages[0].page_text or "")
    assert SECRET_FIELD_VALUE not in repr(provider.seen_request.reason_codes)


def document_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        doc_id="doc-001",
        filename="supplier-sdf.pdf",
        file_path="C:/confidential/supplier-sdf.pdf",
        page_count=1,
        status="ingested",
    )


@dataclass
class ExplodingVisualProvider:
    calls: int = 0

    def extract_visual_fields(
        self,
        *,
        document: DocumentMetadata,
        request: VisualFallbackRequest,
        run_id: str,
    ) -> ProviderExtractionResult:
        self.calls += 1
        raise AssertionError("visual provider should not be called for skipped fallback")


@dataclass
class RecordingVisualProvider:
    calls: int = 0
    seen_request: VisualFallbackRequest | None = None
    seen_run_id: str | None = None

    def extract_visual_fields(
        self,
        *,
        document: DocumentMetadata,
        request: VisualFallbackRequest,
        run_id: str,
    ) -> ProviderExtractionResult:
        assert document.doc_id == "doc-001"
        self.calls += 1
        self.seen_request = request
        self.seen_run_id = run_id
        return ProviderExtractionResult(fields=(), trace_id="trace-visual")
