"""Deterministic tests for targeted visual fallback extraction planning."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.db.queries import DocumentMetadata, DocumentPage, insert_document, insert_page
from src.db.schema import init_db
from src.eval.repository import list_extraction_usage_observations
from src.extraction.models import ExtractedField, ReviewState, SDFFieldName, SourceEvidence
from src.extraction.pipeline import (
    build_visual_fallback_request_plan,
    compute_visual_fallback_eligibility,
    extract_document,
    extract_visual_fallback_candidates,
)
from src.extraction.providers import (
    ProviderExtractionResult,
    ProviderFieldPayload,
    ProviderSourceEvidence,
    ProviderUsageMetadata,
    VisualFallbackRequest,
)
from src.extraction.repository import get_extraction_record, get_extraction_record_for_run


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


def test_extract_document_visual_fallback_fills_abstained_field_and_preserves_good_text_values(tmp_path: Path) -> None:
    db_path = str(tmp_path / "visual-fallback.db")
    prepare_visual_doc(db_path, image_blob=IMAGE_BYTES)
    text_provider = TextProvider(
        fields=all_provider_fields(
            overrides={SDFFieldName.VENDOR_NAME: None},
        )
    )
    visual_provider = VisualProvider(
        fields=(
            provider_payload(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd.", confidence=0.97),
            provider_payload(SDFFieldName.EXPIRY_DATE, "2029-12-31", normalized_date="2029-12-31", confidence=0.99),
        ),
    )

    result = extract_document(
        db_path,
        "doc-001",
        text_provider,
        visual_provider=visual_provider,
        today=date(2026, 1, 1),
        run_id="run-visual-fill",
    )

    assert text_provider.seen_pages_had_images is False
    assert visual_provider.calls == 1
    assert visual_provider.seen_request is not None
    assert visual_provider.seen_request.eligible_field_names == (SDFFieldName.VENDOR_NAME,)
    assert all(page.image_blob is not None for page in visual_provider.seen_request.pages)
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state == ReviewState.PENDING
    assert result.record.fields[SDFFieldName.VENDOR_NAME].raw_value == "Acme Pharma Ltd."
    assert result.record.fields[SDFFieldName.DOC_TYPE].raw_value == "Supplier Declaration Form"
    assert result.record.fields[SDFFieldName.EXPIRY_DATE].raw_value == "2027-01-31"

    stored = get_extraction_record(db_path, "doc-001")
    historical = get_extraction_record_for_run(db_path, "run-visual-fill", "doc-001")
    assert stored is not None
    assert historical is not None
    assert stored.fields[SDFFieldName.VENDOR_NAME].raw_value == "Acme Pharma Ltd."
    assert historical.fields[SDFFieldName.VENDOR_NAME].raw_value == "Acme Pharma Ltd."

    visual_rows = list_extraction_usage_observations(db_path, run_id="run-visual-fill", stage="visual_fallback")
    assert len(visual_rows) == 1
    visual_row = visual_rows[0]
    assert visual_row.provider == "visual-fake"
    assert visual_row.model == "visual-model-v1"
    assert visual_row.status == "complete"
    assert visual_row.input_tokens == 11
    assert visual_row.output_tokens == 7
    assert visual_row.total_tokens == 18
    assert visual_row.estimated_cost_usd == 0.0003
    assert visual_row.trace_id == "trace-visual-fake"
    assert visual_row.error_reason is None


def test_extract_document_visual_fallback_skips_with_no_images_and_records_reason(tmp_path: Path) -> None:
    db_path = str(tmp_path / "visual-no-images.db")
    prepare_visual_doc(db_path, image_blob=None)
    text_provider = TextProvider(fields=all_provider_fields(overrides={SDFFieldName.VENDOR_NAME: None}))
    visual_provider = VisualProvider(fields=(provider_payload(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd."),))

    result = extract_document(
        db_path,
        "doc-001",
        text_provider,
        visual_provider=visual_provider,
        today=date(2026, 1, 1),
        run_id="run-visual-no-images",
    )

    assert visual_provider.calls == 0
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state == ReviewState.ABSTAINED
    rows = list_extraction_usage_observations(db_path, run_id="run-visual-no-images", stage="visual_fallback")
    assert len(rows) == 1
    assert rows[0].status == "skipped"
    assert rows[0].error_reason == "missing_page_images"
    assert rows[0].provider is None
    assert rows[0].trace_id is None


def test_extract_document_visual_fallback_provider_exception_preserves_text_and_sanitizes_observation(tmp_path: Path) -> None:
    db_path = str(tmp_path / "visual-error.db")
    prepare_visual_doc(db_path, image_blob=IMAGE_BYTES)
    low_confidence_vendor = provider_payload(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd.", confidence=0.4)
    text_provider = TextProvider(fields=all_provider_fields(overrides={SDFFieldName.VENDOR_NAME: low_confidence_vendor}))
    visual_provider = RaisingRuntimeVisualProvider()

    result = extract_document(
        db_path,
        "doc-001",
        text_provider,
        visual_provider=visual_provider,
        today=date(2026, 1, 1),
        run_id="run-visual-error",
    )

    assert visual_provider.calls == 1
    vendor = result.record.fields[SDFFieldName.VENDOR_NAME]
    assert vendor.review_state == ReviewState.NEEDS_REVIEW
    assert vendor.raw_value == "Acme Pharma Ltd."
    rows = list_extraction_usage_observations(db_path, run_id="run-visual-error", stage="visual_fallback")
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_reason == "RuntimeError"
    assert "SECRET" not in repr(rows[0])
    assert "image" not in repr(rows[0]).lower()


def test_extract_document_visual_fallback_abstains_when_candidate_is_not_stronger(tmp_path: Path) -> None:
    db_path = str(tmp_path / "visual-abstained.db")
    prepare_visual_doc(db_path, image_blob=IMAGE_BYTES)
    low_confidence_vendor = provider_payload(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd.", confidence=0.4)
    text_provider = TextProvider(fields=all_provider_fields(overrides={SDFFieldName.VENDOR_NAME: low_confidence_vendor}))
    visual_provider = VisualProvider(fields=(provider_payload(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd.", confidence=0.5),))

    result = extract_document(
        db_path,
        "doc-001",
        text_provider,
        visual_provider=visual_provider,
        today=date(2026, 1, 1),
        run_id="run-visual-abstained",
    )

    assert result.record.fields[SDFFieldName.VENDOR_NAME].confidence == 0.4
    assert result.record.fields[SDFFieldName.VENDOR_NAME].review_state == ReviewState.NEEDS_REVIEW
    rows = list_extraction_usage_observations(db_path, run_id="run-visual-abstained", stage="visual_fallback")
    assert len(rows) == 1
    assert rows[0].status == "abstained"
    assert rows[0].error_reason == "no_fields_improved"


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


PAGE_TEXT = """
Supplier Declaration Form
Vendor Name: Acme Pharma Ltd.
Manufacturing Date: 2024-01-05
Effective Date: 2024-02-01
Revision Date: 2024-03-15
Expiry Date: 2027-01-31
"""


def prepare_visual_doc(db_path: str, *, image_blob: bytes | None) -> None:
    init_db(db_path)
    insert_document(
        db_path,
        doc_id="doc-001",
        filename="supplier-sdf.pdf",
        file_path="C:/confidential/supplier-sdf.pdf",
        page_count=1,
        docling_json=None,
    )
    insert_page(db_path, doc_id="doc-001", page_num=0, page_text=PAGE_TEXT, image_blob=image_blob)


def provider_payload(
    field_name: SDFFieldName,
    raw_value: str,
    *,
    normalized_value: str | None = None,
    normalized_date: str | None = None,
    confidence: float = 0.95,
) -> ProviderFieldPayload:
    return ProviderFieldPayload(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        normalized_date=normalized_date,
        confidence=confidence,
        evidence=ProviderSourceEvidence(
            page_num=0,
            verbatim_span=raw_value,
            bbox={"x": 1, "y": 2, "width": 3, "height": 4},
        ),
    )


def all_provider_fields(
    *,
    overrides: dict[SDFFieldName, ProviderFieldPayload | None] | None = None,
) -> tuple[ProviderFieldPayload, ...]:
    fields: dict[SDFFieldName, ProviderFieldPayload | None] = {
        SDFFieldName.DOC_TYPE: provider_payload(SDFFieldName.DOC_TYPE, "Supplier Declaration Form", normalized_value="SDF"),
        SDFFieldName.VENDOR_NAME: provider_payload(SDFFieldName.VENDOR_NAME, "Acme Pharma Ltd."),
        SDFFieldName.MANUFACTURING_DATE: provider_payload(
            SDFFieldName.MANUFACTURING_DATE,
            "2024-01-05",
            normalized_date="2024-01-05",
        ),
        SDFFieldName.EFFECTIVE_DATE: provider_payload(
            SDFFieldName.EFFECTIVE_DATE,
            "2024-02-01",
            normalized_date="2024-02-01",
        ),
        SDFFieldName.REVISION_DATE: provider_payload(
            SDFFieldName.REVISION_DATE,
            "2024-03-15",
            normalized_date="2024-03-15",
        ),
        SDFFieldName.EXPIRY_DATE: provider_payload(
            SDFFieldName.EXPIRY_DATE,
            "2027-01-31",
            normalized_date="2027-01-31",
        ),
    }
    if overrides:
        fields.update(overrides)
    return tuple(payload for field_name in SDFFieldName if (payload := fields[field_name]) is not None)


@dataclass
class TextProvider:
    fields: tuple[ProviderFieldPayload, ...]
    seen_pages_had_images: bool | None = None

    def extract_fields(
        self,
        *,
        document: DocumentMetadata,
        pages: tuple[DocumentPage, ...],
        run_id: str,
    ) -> ProviderExtractionResult:
        assert document.doc_id == "doc-001"
        self.seen_pages_had_images = any(page.image_blob is not None for page in pages)
        return ProviderExtractionResult(fields=self.fields, trace_id="trace-text-fake", provider_name="text-fake")


@dataclass
class VisualProvider:
    fields: tuple[ProviderFieldPayload, ...]
    calls: int = 0
    seen_request: VisualFallbackRequest | None = None

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
        return ProviderExtractionResult(
            fields=self.fields,
            trace_id="trace-visual-fake",
            provider_name="visual-fake",
            provider_model="visual-model-v1",
            usage_metadata=ProviderUsageMetadata(
                model="visual-model-from-usage",
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
                estimated_cost_usd=0.0003,
            ),
        )


@dataclass
class RaisingRuntimeVisualProvider:
    calls: int = 0

    def extract_visual_fields(
        self,
        *,
        document: DocumentMetadata,
        request: VisualFallbackRequest,
        run_id: str,
    ) -> ProviderExtractionResult:
        self.calls += 1
        raise RuntimeError("SECRET visual provider payload, prompt, page text, and image bytes must not persist")
