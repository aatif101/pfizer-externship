"""Offline SDF extraction pipeline orchestration.

The pipeline connects ingested pages to a provider, normalizes exactly six SDF
fields, verifies cited text spans against stored page text, computes conservative
risk metadata, and persists dashboard-ready rows. Diagnostics are typed and
non-secret: run IDs, trace IDs, provider names/classes, and reason codes only.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any, Mapping
from uuid import uuid4

# Injectable test seam: tests monkeypatch pipeline.langfuse_context. None means
# "resolve the live v3 client lazily inside src.tracing" (context=None fallback).
langfuse_context: Any | None = None

from src.db.queries import DocumentMetadata, DocumentPage, LoadedDocumentPages, load_document_pages
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.providers import (
    ProviderExtractionResult,
    ProviderFieldPayload,
    SDFExtractionProvider,
    SDFVisualFallbackProvider,
    VisualFallbackProviderResult,
    VisualFallbackRequest,
    VisualFallbackRequestPlan,
)
from src.extraction.repository import record_extraction_run_resolved_model, upsert_extraction_record
from src.extraction.risk import compute_record_risk
from src.eval.repository import ExtractionUsageObservationRow, insert_extraction_usage_observation
from src.tracing import observe, safe_update_current_trace


LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.75
PROVIDER_ABSTENTION_REASON = "Provider abstained from this required SDF field."
_PLACEHOLDER_VALUE_RE = re.compile(
    r"^(?:x{2,}(?:[-/][a-z]{3}|[-/]x{2,})*|m{3}/y{4}|a{3}n{3,}|assigned|tbd|to be determined)$",
    re.IGNORECASE,
)
_DELIVERY_DATE_RE = re.compile(r"\bdelivery\s+date\b", re.IGNORECASE)
_RETEST_DATE_RE = re.compile(r"\bretest\s+date\b", re.IGNORECASE)
_MAX_SOURCE_SPAN_LENGTH = 500
_DATE_FIELDS = frozenset(
    {
        SDFFieldName.MANUFACTURING_DATE,
        SDFFieldName.EFFECTIVE_DATE,
        SDFFieldName.REVISION_DATE,
        SDFFieldName.EXPIRY_DATE,
    }
)
_NOT_APPLICABLE_DATE_MARKERS = frozenset({"n/a", "n.a.", "na", "not applicable"})
_PRIMARY_CERTIFICATE_RE = re.compile(
    r"\b(?:certificate\s+of\s+(?:analysis|quality|compliance|conformance|conformity)|"
    r"(?:quality|product|material)\s+certificate|supplier\s+declaration\s+form|"
    r"(?:custom\s+)?specification(?:\s+[A-Z0-9_-]+)?|product\s+data\s+sheet)\b",
    re.IGNORECASE,
)
_NONPRIMARY_HEADING_RE = re.compile(
    r"(?:^\s*(?:from|sent|received|subject)\s*:|\bsent\s+via\s+email\b|"
    r"\bemail\s+(?:cover|message|signature)\b|\bsafety\s+data\s+sheet\b|"
    r"\b(?:certificate\s+of\s+(?:processing|dosimetry)|(?:processing|dosimetry)\s+certificate)\b|"
    r"\bprocessing\s+record\b|\b(?:internal\s+)?calibration\s+report\b|"
    r"\b(?:release\s+)?template\b|\bhandwritten\s+(?:note|date)\b|"
    r"\bunrelated\s+attachment\b)",
    re.IGNORECASE,
)
_NONPRIMARY_ALIAS_HEADING_RE = re.compile(
    r"^\s*(?:SDS|EMAIL|DOSIMETRY\s+(?:RECORD|RUN)|PROCESSING\s+(?:RECORD|RUN)|"
    r"(?:COMMERCIAL\s+)?INVOICE|PACKING\s+(?:LIST|SLIP)|COVER\s+LETTER|TRANSMITTAL|"
    r"SHIPPING\s+(?:RECORD|DOCUMENT|MANIFEST)|BILL\s+OF\s+LADING|PURCHASE\s+ORDER|"
    r"DELIVERY\s+NOTE|TECHNICAL\s+DATA\s+SHEET)"
    r"\s*(?:[:#\-].*)?$",
    re.IGNORECASE,
)
_GENERIC_DOCUMENT_HEADING_RE = re.compile(
    r"^(?:CERTIFICATE\s+OF\s+[A-Z0-9][A-Z0-9 /&(),.\-]{1,78}|"
    r"[A-Z0-9][A-Z0-9 /&(),.\-]{1,78}\b(?:LIST|INVOICE|LETTER|RECORD|REPORT|MANIFEST|"
    r"ORDER|NOTE|RECEIPT|SHEET|FORM|CERTIFICATE))\s*$",
    re.IGNORECASE,
)
_HEADING_PROSE_RE = re.compile(
    r"\b(?:attached|attachment|please|review|enclosed|following|sent|email|example|mentions?)\b",
    re.IGNORECASE,
)
_NONPRIMARY_TITLE_MODIFIER_RE = re.compile(
    r"\b(?:template|draft|example|sample|blank|reference|superseded|obsolete|"
    r"changes?|change\s+history|instructions?|cover\s+sheet)\b",
    re.IGNORECASE,
)
_SPECIFICATION_TITLE_PREFIX_RE = re.compile(r"^(?:custom\s+)?specification\b", re.IGNORECASE)
_PACKET_TRAP_RE = re.compile(
    r"(?:\bfrom\s*:|\bsent\s*:|\breceived\s*:|\bsubject\s*:|\bemail\b|"
    r"\bsafety\s+data\s+sheet\b|\bSDS\b|\bprocessing\s+record\b|"
    r"\btemplate(?:\s+release)?\b|\bhandwritten\s+(?:note|date)\b|"
    r"\bunrelated\s+attachment\b|\battachment\s+date\b)",
    re.IGNORECASE,
)
_TARGET_DATE_LABELS: dict[SDFFieldName, re.Pattern[str]] = {
    SDFFieldName.MANUFACTURING_DATE: re.compile(
        r"\b(?:(?:manufactur(?:e|ing|ed)|production)\s+date|date\s+of\s+manufacture|"
        r"product\s+manufactured|mfg\.?\s*date)\b",
        re.IGNORECASE,
    ),
    SDFFieldName.EFFECTIVE_DATE: re.compile(
        r"\b(?:effective\s+date|approved\s+on|issue\s+date|date\s+of\s+issue)\b",
        re.IGNORECASE,
    ),
    SDFFieldName.REVISION_DATE: re.compile(
        r"\b(?:revision\s+date|revised\s+on|last\s+revised)\b",
        re.IGNORECASE,
    ),
    SDFFieldName.EXPIRY_DATE: re.compile(
        r"\b(?:expiry|expiration)\s+date\b",
        re.IGNORECASE,
    ),
}
_NEGATED_DATE_LABEL_RE = re.compile(
    r"\b(?:not|non)[ -]+(?:manufacturing|manufactured|production|mfg\.?|effective|"
    r"approved|issue|revision|revised|expiry|expiration)\s+(?:on|date)\b",
    re.IGNORECASE,
)
_NONCURRENT_DATE_MODIFIER_RE = re.compile(
    r"\b(?:previous|prior|original|proposed|draft|planned|expected|estimated|tentative|target|"
    r"scheduled|anticipated|approximate|forecast(?:ed)?|projected|indicative|next|future|"
    r"superseded|obsolete)\s*$",
    re.IGNORECASE,
)
_VENDOR_LABEL_RE = re.compile(
    r"^\s*(?:(?:vendor|supplier|manufacturer)(?:\s+name)?|manufactured\s+by|issued\s+by|"
    r"company\s+name|name\s+of\s+(?:the\s+)?(?:vendor|supplier|manufacturer)|"
    r"supplier\s*/\s*manufacturer)\s*(?:[:\-]\s*|\s+)(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_VENDOR_HEADER_LABEL_RE = re.compile(
    r"^\s*(?:(?:vendor|supplier|manufacturer)(?:\s+name)?|manufactured\s+by|issued\s+by|"
    r"company\s+name|name\s+of\s+(?:the\s+)?(?:vendor|supplier|manufacturer)|"
    r"supplier\s*/\s*manufacturer)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
_VENDOR_ATTRIBUTE_VALUE_RE = re.compile(
    r"^(?:address|contact|email|e-mail|phone|telephone|fax|id|identifier|code|number|no\.?|"
    r"lot|batch|account|website|url)\b\s*[:#\-]?",
    re.IGNORECASE,
)
_VENDOR_DECOY_LABEL_RE = re.compile(
    r"\b(?:product|material|item|trade|brand)(?:\s+(?:name|description|code|number))?\s*[:\-]|"
    r"\b(?:approved|prepared|reviewed|authorized|signed)\s+by\b|"
    r"\b(?:signature|signatory|lot|batch)(?:\s+(?:number|no\.?|code))?\s*[:\-]",
    re.IGNORECASE,
)
_VENDOR_TABLE_DECOY_HEADER_RE = re.compile(
    r"^\s*(?:(?:product|material|item|trade|brand)(?:\s+(?:name|description|code|number))?|"
    r"cas(?:\s+(?:number|no\.?))?|(?:lot|batch|catalog|part)(?:\s+(?:number|no\.?|code))?|"
    r"(?:approved|prepared|reviewed|authorized|signed)\s+by|signature|signatory|title)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
_MANUFACTURING_RELATION_RE = re.compile(
    r"\b(?:manufactured|produced|assembled|supplied|issued)\s+(?:by|at|in)\b|"
    r"\bin\s+(?:an?\s+)?[^\n]{1,120}\s+(?:facility|plant|site)\b",
    re.IGNORECASE,
)
_ADDRESS_OR_CONTACT_RE = re.compile(
    r"(?:\b\d{1,6}\s+[A-Za-z0-9][^\n]{1,80}\b(?:street|st\.?|road|rd\.?|avenue|ave\.?|"
    r"boulevard|blvd\.?|drive|dr\.?|lane|ln\.?|way)\b|\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b|"
    r"\b(?:www\.|https?://|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b)",
    re.IGNORECASE,
)
_DOC_TYPE_LABEL_RE = re.compile(
    r"^\s*(?:document|certificate|form)\s+type\s*[:\-]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_MONTH_NUMBERS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_EXTRACTION_TRACE_ALLOWED_KEYS = frozenset(
    {
        "boundary",
        "status",
        "run_id",
        "doc_id",
        "trace_id",
        "provider_name",
        "page_count",
        "review_state",
        "needs_review",
        "reason_code",
        "error_class",
    }
)


class ExtractionPipelineError(RuntimeError):
    """Base class for typed extraction failures that should not expose secrets."""

    reason_code = "extraction_failed"

    def __init__(self, message: str, *, run_id: str | None = None, doc_id: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.doc_id = doc_id


class DocumentNotFoundError(ExtractionPipelineError):
    """Raised when the requested document metadata row does not exist."""

    reason_code = "document_not_found"


class NoPagesError(ExtractionPipelineError):
    """Raised when a document has no persisted pages to send to the provider."""

    reason_code = "no_pages"


class NoPageTextError(ExtractionPipelineError):
    """Raised when all persisted pages have empty text."""

    reason_code = "no_page_text"


class ProviderInvocationError(ExtractionPipelineError):
    """Raised when an arbitrary provider failure is reduced to a safe boundary error."""

    reason_code = "provider_invocation_failed"


class ProviderOutputError(ExtractionPipelineError):
    """Raised when a provider violates its provider-neutral result contract."""

    reason_code = "provider_output_invalid"


class InvalidConfidenceThresholdError(ExtractionPipelineError):
    """Raised before provider work for an invalid review threshold."""

    reason_code = "invalid_confidence_threshold"


@dataclass(frozen=True)
class ExtractionDiagnostics:
    """Non-secret run diagnostics for logs, traces, or tests."""

    run_id: str
    doc_id: str
    trace_id: str | None
    provider_name: str | None
    page_count: int
    review_state: str
    needs_review: bool


@dataclass(frozen=True)
class ExtractionPipelineResult:
    """Result returned after a successful persisted extraction run."""

    record: SDFExtractionRecord
    diagnostics: ExtractionDiagnostics


@dataclass(frozen=True)
class _PacketSectionState:
    """Deterministic primary-subdocument identity while scanning a PDF packet."""

    active_primary_block: int | None = None
    next_primary_block: int = 0


VISUAL_FALLBACK_ELIGIBLE_REASON_CODES: dict[ReviewState, str] = {
    ReviewState.ABSTAINED: "field_abstained",
    ReviewState.NEEDS_REVIEW: "field_needs_review",
}
VISUAL_FALLBACK_SKIP_NO_ELIGIBLE_FIELDS = "no_eligible_fields"
VISUAL_FALLBACK_SKIP_MISSING_PAGE_IMAGES = "missing_page_images"
VISUAL_FALLBACK_SKIP_NOT_CONFIGURED = "not_configured"
_VISUAL_PROVIDER_REASON_CODES = frozenset(
    {
        "extraction_configuration_error",
        "extraction_provider_error",
        "extraction_validation_error",
    }
)


def compute_visual_fallback_eligibility(
    fields: Mapping[SDFFieldName, ExtractedField],
) -> dict[SDFFieldName, str]:
    """Return bounded field-level reason codes for fields eligible for visual fallback.

    Eligibility is intentionally narrow: only normalized text fields that are
    ``ABSTAINED`` or ``NEEDS_REVIEW`` may enter visual fallback. Good grounded
    ``PENDING`` values are excluded so a later visual provider cannot overwrite
    them through the targeted fallback seam.
    """

    eligibility: dict[SDFFieldName, str] = {}
    for field_name in SDFFieldName:
        field = fields.get(field_name)
        if field is None:
            continue
        reason_code = VISUAL_FALLBACK_ELIGIBLE_REASON_CODES.get(field.review_state)
        if reason_code is not None:
            eligibility[field_name] = reason_code
    return eligibility


def build_visual_fallback_request_plan(
    fields: Mapping[SDFFieldName, ExtractedField],
    pages: tuple[DocumentPage, ...],
) -> VisualFallbackRequestPlan:
    """Build a sanitized targeted visual fallback request, or a bounded skip plan.

    The ready request contains only eligible field names, selected pages whose
    ``image_blob`` is populated, and generic reason codes. It must not be used as
    a persistence/logging DTO for image bytes; downstream usage observations
    should persist only the returned status/reason code.
    """

    eligibility = compute_visual_fallback_eligibility(fields)
    if not eligibility:
        return VisualFallbackRequestPlan(status="skipped", reason_code=VISUAL_FALLBACK_SKIP_NO_ELIGIBLE_FIELDS)

    pages_with_images = tuple(page for page in pages if page.image_blob)
    if not pages_with_images:
        return VisualFallbackRequestPlan(status="skipped", reason_code=VISUAL_FALLBACK_SKIP_MISSING_PAGE_IMAGES)

    eligible_field_names = tuple(field_name for field_name in SDFFieldName if field_name in eligibility)
    request = VisualFallbackRequest(
        eligible_field_names=eligible_field_names,
        pages=pages_with_images,
        reason_codes={field_name: eligibility[field_name] for field_name in eligible_field_names},
    )
    return VisualFallbackRequestPlan(status="ready", request=request)


def extract_visual_fallback_candidates(
    *,
    document: DocumentMetadata,
    fields: Mapping[SDFFieldName, ExtractedField],
    pages: tuple[DocumentPage, ...],
    run_id: str,
    visual_provider: SDFVisualFallbackProvider | None,
) -> VisualFallbackProviderResult:
    """Invoke visual fallback only when configured and eligible.

    This helper establishes the no-op contract for orchestration: no provider is
    called when there are no eligible fields, when images are unavailable, or when
    no visual provider is configured. All skip reasons are bounded generic codes.
    """

    plan = build_visual_fallback_request_plan(fields, pages)
    if plan.request is None:
        return VisualFallbackProviderResult(plan=plan)
    if visual_provider is None:
        return VisualFallbackProviderResult(
            plan=VisualFallbackRequestPlan(status="skipped", reason_code=VISUAL_FALLBACK_SKIP_NOT_CONFIGURED)
        )
    try:
        provider_result = visual_provider.extract_visual_fields(document=document, request=plan.request, run_id=run_id)
    except Exception:
        return VisualFallbackProviderResult(
            plan=VisualFallbackRequestPlan(status="error", reason_code="visual_provider_error")
        )
    return VisualFallbackProviderResult(plan=plan, provider_result=provider_result)


@dataclass(frozen=True)
class _VisualFallbackStageOutcome:
    """Internal visual fallback stage result; safe fields only except transient normalized candidates."""

    merged_fields: dict[SDFFieldName, ExtractedField]
    status: str
    reason_code: str | None = None
    provider_result: ProviderExtractionResult | None = None
    latency_ms: float | None = None


def _run_visual_fallback_stage(
    db_path: str,
    *,
    document: DocumentMetadata,
    text_fields: dict[SDFFieldName, ExtractedField],
    text_pages: tuple[DocumentPage, ...],
    run_id: str,
    visual_provider: SDFVisualFallbackProvider | None,
    low_confidence_threshold: float,
) -> _VisualFallbackStageOutcome:
    """Run targeted visual fallback and merge only eligible improvements.

    Image bytes are loaded only after a visual provider is configured and text
    normalization produced at least one eligible field. Provider exceptions are
    converted into a bounded error outcome so visual fallback cannot overwrite or
    block the text extraction result.
    """

    if visual_provider is None:
        return _VisualFallbackStageOutcome(
            merged_fields=dict(text_fields),
            status="skipped",
            reason_code=VISUAL_FALLBACK_SKIP_NOT_CONFIGURED,
        )

    eligibility = compute_visual_fallback_eligibility(text_fields)
    if not eligibility:
        return _VisualFallbackStageOutcome(
            merged_fields=dict(text_fields),
            status="skipped",
            reason_code=VISUAL_FALLBACK_SKIP_NO_ELIGIBLE_FIELDS,
        )

    loaded_with_images = load_document_pages(db_path, document.doc_id, include_image_bytes=True)
    image_pages = loaded_with_images.pages if loaded_with_images is not None else text_pages
    plan = build_visual_fallback_request_plan(text_fields, image_pages)
    if plan.request is None:
        return _VisualFallbackStageOutcome(
            merged_fields=dict(text_fields),
            status="skipped",
            reason_code=plan.reason_code,
        )

    started_at = perf_counter()
    try:
        provider_result = visual_provider.extract_visual_fields(document=document, request=plan.request, run_id=run_id)
    except Exception as exc:
        return _VisualFallbackStageOutcome(
            merged_fields=dict(text_fields),
            status="error",
            reason_code=_visual_provider_error_reason(exc),
            latency_ms=(perf_counter() - started_at) * 1000,
        )

    latency_ms = (perf_counter() - started_at) * 1000
    try:
        visual_fields = _normalize_fields(
            provider_result,
            pages=plan.request.pages,
            low_confidence_threshold=low_confidence_threshold,
            visual_claims=True,
        )
    except Exception:  # noqa: BLE001 - malformed visual output must fail closed.
        return _VisualFallbackStageOutcome(
            merged_fields=dict(text_fields),
            status="error",
            reason_code="visual_provider_output_invalid",
            provider_result=None,
            latency_ms=latency_ms,
        )
    merged_fields = _merge_visual_fallback_fields(
        text_fields,
        visual_fields,
    )
    status = "complete" if merged_fields != text_fields else "abstained"
    reason_code = None if status == "complete" else "no_fields_improved"
    return _VisualFallbackStageOutcome(
        merged_fields=merged_fields,
        status=status,
        reason_code=reason_code,
        provider_result=provider_result,
        latency_ms=latency_ms,
    )


def _merge_visual_fallback_fields(
    text_fields: Mapping[SDFFieldName, ExtractedField],
    visual_fields: Mapping[SDFFieldName, ExtractedField],
) -> dict[SDFFieldName, ExtractedField]:
    """Merge visual candidates without allowing broad overwrite behavior."""

    merged = dict(text_fields)
    eligibility = compute_visual_fallback_eligibility(text_fields)
    for field_name in eligibility:
        current = text_fields[field_name]
        candidate = visual_fields.get(field_name)
        if candidate is None or candidate.review_state is ReviewState.ABSTAINED:
            continue
        if current.review_state is ReviewState.ABSTAINED:
            merged[field_name] = candidate
    return merged


def _visual_provider_error_reason(exc: BaseException) -> str:
    """Return a sanitized provider error class/reason code without exception text."""

    reason_code = getattr(exc, "reason_code", None)
    if reason_code in _VISUAL_PROVIDER_REASON_CODES:
        return reason_code
    return "visual_provider_error"


@observe(name="sdf_extract_document")
def extract_document(
    db_path: str,
    doc_id: str,
    provider: SDFExtractionProvider,
    *,
    today: date | None = None,
    low_confidence_threshold: float = LOW_CONFIDENCE_REVIEW_THRESHOLD,
    run_id: str | None = None,
    visual_provider: SDFVisualFallbackProvider | None = None,
) -> ExtractionPipelineResult:
    """Extract and persist one document's six-field SDF record.

    The provider sees only typed document/page inputs and a generated run ID. Full
    page text and raw provider payloads are never logged or returned in
    diagnostics by this orchestration layer.
    """

    effective_run_id = run_id or f"sdf-{uuid4().hex}"
    try:
        safe_threshold = _validated_confidence_threshold(
            low_confidence_threshold,
            run_id=effective_run_id,
            doc_id=doc_id,
        )
        loaded = load_document_pages(db_path, doc_id, include_image_bytes=False)
        if loaded is None:
            raise DocumentNotFoundError("Document metadata was not found for extraction.", run_id=effective_run_id, doc_id=doc_id)
        _validate_pages_for_extraction(loaded, run_id=effective_run_id)

        page_text_available = any((page.page_text or "").strip() for page in loaded.pages)
        provider_result: ProviderExtractionResult | None = None
        provider_latency_ms: float | None = None
        if page_text_available:
            provider_started_at = perf_counter()
            try:
                provider_result = provider.extract_fields(
                    document=loaded.document,
                    pages=loaded.pages,
                    run_id=effective_run_id,
                )
            except Exception:
                raise ProviderInvocationError(
                    "Extraction provider invocation failed.",
                    run_id=effective_run_id,
                    doc_id=loaded.document.doc_id,
                ) from None
            provider_latency_ms = (perf_counter() - provider_started_at) * 1000
            try:
                fields = _normalize_fields(
                    provider_result,
                    pages=loaded.pages,
                    low_confidence_threshold=safe_threshold,
                    visual_claims=False,
                )
            except Exception:
                raise ProviderOutputError(
                    "Extraction provider output violated the result contract.",
                    run_id=effective_run_id,
                    doc_id=loaded.document.doc_id,
                ) from None
        else:
            if visual_provider is None:
                raise NoPageTextError(
                    "Document pages contain no extractable text.",
                    run_id=effective_run_id,
                    doc_id=loaded.document.doc_id,
                )
            fields = {
                field_name: _abstained_field(
                    field_name,
                    "Stored page text is empty; image-backed extraction is required.",
                )
                for field_name in SDFFieldName
            }
        visual_outcome = _run_visual_fallback_stage(
            db_path,
            document=loaded.document,
            text_fields=fields,
            text_pages=loaded.pages,
            run_id=effective_run_id,
            visual_provider=visual_provider,
            low_confidence_threshold=safe_threshold,
        )
        fields = _enforce_single_primary_block(visual_outcome.merged_fields, pages=loaded.pages)

        successful_provider_result = provider_result or visual_outcome.provider_result
        record = SDFExtractionRecord(
            doc_id=loaded.document.doc_id,
            filename=loaded.document.filename,
            fields=fields,
            trace_id=successful_provider_result.trace_id if successful_provider_result is not None else None,
            run_id=effective_run_id,
            extracted_at=datetime.now(timezone.utc),
        )
        risk = compute_record_risk(record, today=today or date.today())
        record.risk_level = risk.risk_level
        record.risk_reason = risk.risk_reason
        record.compliance_status = risk.compliance_status
        record.age_days = risk.age_days

        upsert_extraction_record(db_path, record)
        audit_usage = successful_provider_result.usage_metadata if successful_provider_result is not None else None
        record_extraction_run_resolved_model(
            db_path,
            effective_run_id,
            audit_usage.resolved_model if audit_usage is not None else None,
        )
        if provider_result is not None and provider_latency_ms is not None:
            _insert_text_usage_observation(
                db_path,
                record=record,
                provider_result=provider_result,
                latency_ms=provider_latency_ms,
            )
        _insert_visual_fallback_usage_observation(
            db_path,
            record=record,
            outcome=visual_outcome,
        )

        diagnostics = ExtractionDiagnostics(
            run_id=effective_run_id,
            doc_id=loaded.document.doc_id,
            trace_id=successful_provider_result.trace_id if successful_provider_result is not None else None,
            provider_name=successful_provider_result.provider_name if successful_provider_result is not None else None,
            page_count=len(loaded.pages),
            review_state=record.dashboard_review_state,
            needs_review=record.dashboard_needs_review,
        )
        _update_extraction_trace_metadata(
            {
                "boundary": "extraction",
                "status": "completed",
                "run_id": diagnostics.run_id,
                "doc_id": diagnostics.doc_id,
                "trace_id": diagnostics.trace_id,
                "provider_name": diagnostics.provider_name,
                "page_count": diagnostics.page_count,
                "review_state": diagnostics.review_state,
                "needs_review": diagnostics.needs_review,
            }
        )
        return ExtractionPipelineResult(record=record, diagnostics=diagnostics)
    except Exception as exc:
        _update_extraction_trace_metadata(_error_trace_metadata(exc, run_id=effective_run_id, doc_id=doc_id))
        raise


def _update_extraction_trace_metadata(metadata: dict[str, Any]) -> None:
    """Attach whitelisted extraction diagnostics without affecting pipeline behavior.

    The allowlist intentionally excludes exception messages, provider payloads,
    field values, normalized values, verbatim spans, prompts, raw responses, page
    text, file paths, image bytes, Docling JSON, and secrets.
    """

    safe_update_current_trace(
        tags=["extraction"],
        metadata=metadata,
        allowed_metadata_keys=_EXTRACTION_TRACE_ALLOWED_KEYS,
        context=langfuse_context,
    )


def _error_trace_metadata(exc: BaseException, *, run_id: str, doc_id: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "boundary": "extraction",
        "status": "error",
        "run_id": getattr(exc, "run_id", None) or run_id,
        "doc_id": getattr(exc, "doc_id", None) or doc_id,
        "error_class": exc.__class__.__name__,
    }
    if isinstance(exc, ExtractionPipelineError):
        metadata["reason_code"] = exc.reason_code
    return metadata


def _insert_text_usage_observation(
    db_path: str,
    *,
    record: SDFExtractionRecord,
    provider_result: ProviderExtractionResult,
    latency_ms: float,
) -> None:
    usage = provider_result.usage_metadata
    provider_model = provider_result.provider_model or (usage.model if usage is not None else None)
    status = _usage_observation_status(record)
    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id=record.run_id or "",
            doc_id=record.doc_id,
            stage="text_extraction",
            provider=provider_result.provider_name,
            model=provider_model,
            requested_model=usage.requested_model if usage is not None else None,
            resolved_model=usage.resolved_model if usage is not None else None,
            pricing_model=usage.pricing_model if usage is not None else None,
            status=status,
            latency_ms=latency_ms,
            input_tokens=usage.input_tokens if usage is not None else None,
            output_tokens=usage.output_tokens if usage is not None else None,
            thought_tokens=usage.thought_tokens if usage is not None else None,
            total_tokens=usage.total_tokens if usage is not None else None,
            estimated_cost_usd=usage.estimated_cost_usd if usage is not None else None,
            trace_id=provider_result.trace_id,
            error_reason=_usage_observation_error_reason(status),
        ),
    )


def _insert_visual_fallback_usage_observation(
    db_path: str,
    *,
    record: SDFExtractionRecord,
    outcome: _VisualFallbackStageOutcome,
) -> None:
    provider_result = outcome.provider_result
    usage = provider_result.usage_metadata if provider_result is not None else None
    provider_model = None
    if provider_result is not None:
        provider_model = provider_result.provider_model or (usage.model if usage is not None else None)
    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id=record.run_id or "",
            doc_id=record.doc_id,
            stage="visual_fallback",
            provider=provider_result.provider_name if provider_result is not None else None,
            model=provider_model,
            requested_model=usage.requested_model if usage is not None else None,
            resolved_model=usage.resolved_model if usage is not None else None,
            pricing_model=usage.pricing_model if usage is not None else None,
            status=outcome.status,
            latency_ms=outcome.latency_ms,
            input_tokens=usage.input_tokens if usage is not None else None,
            output_tokens=usage.output_tokens if usage is not None else None,
            thought_tokens=usage.thought_tokens if usage is not None else None,
            total_tokens=usage.total_tokens if usage is not None else None,
            estimated_cost_usd=usage.estimated_cost_usd if usage is not None else None,
            trace_id=provider_result.trace_id if provider_result is not None else None,
            error_reason=outcome.reason_code,
        ),
    )


def _usage_observation_status(record: SDFExtractionRecord) -> str:
    review_states = [field.review_state for field in record.fields.values()]
    if review_states and all(state is ReviewState.ABSTAINED for state in review_states):
        return "abstained"
    if record.dashboard_needs_review:
        return "needs_review"
    return "complete"


def _usage_observation_error_reason(status: str) -> str | None:
    if status == "abstained":
        return "all_fields_abstained"
    if status == "needs_review":
        return "fields_need_review"
    return None


def _validate_pages_for_extraction(loaded: LoadedDocumentPages, *, run_id: str) -> None:
    if not loaded.pages:
        raise NoPagesError("Document has no persisted pages for extraction.", run_id=run_id, doc_id=loaded.document.doc_id)


def _normalize_fields(
    provider_result: ProviderExtractionResult,
    *,
    pages: tuple[DocumentPage, ...],
    low_confidence_threshold: float,
    visual_claims: bool = False,
) -> dict[SDFFieldName, ExtractedField]:
    provider_fields: dict[SDFFieldName, ProviderFieldPayload] = {}
    for payload in provider_result.fields:
        try:
            field_name = SDFFieldName(payload.field_name)
        except ValueError:
            continue
        provider_fields.setdefault(field_name, payload)

    return {
        field_name: _normalize_field(
            field_name,
            provider_fields.get(field_name),
            pages=pages,
            low_confidence_threshold=low_confidence_threshold,
            visual_claim=visual_claims,
        )
        for field_name in SDFFieldName
    }


def _normalize_field(
    field_name: SDFFieldName,
    payload: ProviderFieldPayload | None,
    *,
    pages: tuple[DocumentPage, ...],
    low_confidence_threshold: float,
    visual_claim: bool,
) -> ExtractedField:
    if payload is None:
        return _abstained_field(field_name, "Provider did not return this required SDF field.")

    explicit_reason = _clean_text(payload.abstention_reason)
    if explicit_reason and not _has_payload_value(payload):
        return _abstained_field(
            field_name,
            PROVIDER_ABSTENTION_REASON,
            payload=payload,
        )
    if not _has_payload_value(payload):
        return _abstained_field(field_name, "Provider returned no value for this required SDF field.", payload=payload)
    if payload.evidence is None:
        return _abstained_field(field_name, "Provider returned no source evidence for this required SDF field.", payload=payload)

    page = next((candidate for candidate in pages if candidate.page_num == payload.evidence.page_num), None)
    if page is None:
        return _abstained_field(field_name, "Provider cited a page number that was not persisted for this document.", payload=payload)
    if not _is_json_compatible(payload.evidence.bbox):
        return _abstained_field(field_name, "Provider returned a non-JSON-serializable source bounding box.", payload=payload)

    provider_span = payload.evidence.verbatim_span
    if (
        not isinstance(provider_span, str)
        or not provider_span.strip()
        or provider_span != provider_span.strip()
        or len(provider_span) > _MAX_SOURCE_SPAN_LENGTH
    ):
        return _abstained_field(field_name, "Provider returned no verbatim source span for this required SDF field.", payload=payload)

    page_has_text = bool((page.page_text or "").strip())
    visual_region_claim = False
    if page_has_text:
        span = _literal_source_span(provider_span, page.page_text or "")
        if span is None:
            if (
                not visual_claim
                or field_name is not SDFFieldName.VENDOR_NAME
                or page.image_blob is None
                or not _has_bounded_visual_region(payload.evidence.bbox)
            ):
                return _abstained_field(
                    field_name,
                    "Provider source span was not found in the cited page text.",
                    payload=payload,
                )
            # Supplier logos and image headers are often omitted by PDF text/OCR.
            # A finite page region preserves inspectable image evidence, but the
            # candidate remains visual-only and can never bypass human review.
            span = provider_span
            visual_region_claim = True
    else:
        if not visual_claim or page.image_blob is None:
            return _abstained_field(
                field_name,
                "Empty-text evidence requires an image-backed visual claim.",
                payload=payload,
            )
        span = provider_span

    visual_evidence_claim = not page_has_text or visual_region_claim
    guard_reason = _field_value_guard_reason(
        field_name,
        payload,
        span,
        pages=pages,
        page_num=page.page_num,
        page_text=page.page_text or "",
        visual_region_claim=visual_evidence_claim,
    )
    if guard_reason is not None:
        return _abstained_field(field_name, guard_reason, payload=payload)

    raw_value = _clean_text(payload.raw_value)
    if raw_value is None or raw_value not in span:
        return _abstained_field(
            field_name,
            "Provider raw value was not literally supported by its source span.",
            payload=payload,
        )
    if page_has_text and not visual_region_claim and span == raw_value and (page.page_text or "").count(span) > 1:
        return _abstained_field(
            field_name,
            "Provider value-only evidence was ambiguous within the cited page.",
            payload=payload,
        )

    normalized_date: date | None = None
    # Provider normalization is never a source of truth. Non-date fields retain
    # the exact printed value; date fields are normalized locally below.
    normalized_value = raw_value
    if field_name in _DATE_FIELDS:
        marker = raw_value.casefold()
        if marker in _NOT_APPLICABLE_DATE_MARKERS:
            if field_name is not SDFFieldName.EXPIRY_DATE:
                return _abstained_field(
                    field_name,
                    "Not-applicable markers are supported only for expiry_date.",
                    payload=payload,
                )
            normalized_value = "N/A"
        else:
            parsed_date, partial_month = _parse_allowlisted_date(raw_value)
            if parsed_date is None and partial_month is None:
                return _abstained_field(
                    field_name,
                    "Provider date did not match an allowlisted unambiguous format.",
                    payload=payload,
                )
            if parsed_date is not None:
                normalized_date = parsed_date
                normalized_value = normalized_date.isoformat()
            else:
                normalized_value = partial_month

    confidence = _clamp_confidence(payload.confidence)
    if confidence is None:
        return _abstained_field(
            field_name,
            "Provider confidence was not a finite value from zero through one.",
            payload=payload,
        )
    evidence_type = "visual" if not page_has_text or visual_region_claim else "text"
    if evidence_type == "visual" or normalized_date is None and field_name in _DATE_FIELDS and normalized_value != "N/A":
        review_state = ReviewState.NEEDS_REVIEW
    else:
        review_state = ReviewState.NEEDS_REVIEW if confidence < low_confidence_threshold else ReviewState.PENDING
    return ExtractedField(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        normalized_date=normalized_date,
        confidence=confidence,
        evidence=SourceEvidence(
            page_num=payload.evidence.page_num,
            bbox=payload.evidence.bbox,
            verbatim_span=span,
            evidence_type=evidence_type,
        ),
        review_state=review_state,
    )


def _abstained_field(
    field_name: SDFFieldName,
    reason: str,
    *,
    payload: ProviderFieldPayload | None = None,
) -> ExtractedField:
    page_num = 0
    bbox = None
    if payload is not None and payload.evidence is not None and payload.evidence.page_num >= 0:
        page_num = payload.evidence.page_num
        bbox = payload.evidence.bbox if _is_json_compatible(payload.evidence.bbox) else None
    return ExtractedField(
        field_name=field_name,
        raw_value=None,
        normalized_value=None,
        normalized_date=None,
        confidence=0.0,
        evidence=SourceEvidence(page_num=page_num, bbox=bbox),
        review_state=ReviewState.ABSTAINED,
        abstention_reason=reason,
    )


def _has_payload_value(payload: ProviderFieldPayload) -> bool:
    return any(
        value is not None and (not isinstance(value, str) or bool(value.strip()))
        for value in (payload.raw_value, payload.normalized_value, payload.normalized_date)
    )


def _field_value_guard_reason(
    field_name: SDFFieldName,
    payload: ProviderFieldPayload,
    span: str,
    *,
    pages: tuple[DocumentPage, ...],
    page_num: int,
    page_text: str,
    visual_region_claim: bool,
) -> str | None:
    raw_value = _clean_text(payload.raw_value)
    if raw_value is not None and _is_placeholder_value(raw_value):
        return "Provider returned a placeholder/redacted value rather than a real field value."

    claim_line = _claim_line_context(span, page_text, raw_value=raw_value)

    if any((page.page_text or "").strip() for page in pages) and not _claim_is_in_primary_scope(
        pages,
        page_num=page_num,
        span=span,
        raw_value=raw_value,
        visual_region_claim=visual_region_claim,
    ):
        return "Provider field evidence was not scoped to the primary product or material document."

    if field_name is SDFFieldName.VENDOR_NAME:
        if not _vendor_candidate_is_supported(
            raw_value,
            span=span,
            claim_line=claim_line,
            page_text=page_text,
            visual_region_claim=visual_region_claim,
        ):
            return "Provider vendor_name was not the complete printed supplier value."

    if field_name is SDFFieldName.DOC_TYPE:
        labeled_value = _line_labeled_value(claim_line, _DOC_TYPE_LABEL_RE)
        printed_value = labeled_value if labeled_value is not None else claim_line.strip()
        if raw_value != printed_value or _PRIMARY_CERTIFICATE_RE.search(raw_value or "") is None:
            return "Provider doc_type was not the complete printed primary-document type."

    if field_name is SDFFieldName.EFFECTIVE_DATE and (
        _DELIVERY_DATE_RE.search(claim_line) or _DELIVERY_DATE_RE.search(span)
    ):
        return "Provider mapped Delivery Date to effective_date, but delivery dates are not effective dates."

    if field_name is SDFFieldName.EXPIRY_DATE and (
        _RETEST_DATE_RE.search(claim_line) or _RETEST_DATE_RE.search(span)
    ):
        return "Provider mapped Retest Date to expiry_date, but retest dates are not expiry dates."

    if field_name in _DATE_FIELDS:
        if _NEGATED_DATE_LABEL_RE.search(claim_line) or _NEGATED_DATE_LABEL_RE.search(span):
            return "Provider cited a negated date label rather than the target certificate field."
        if _PACKET_TRAP_RE.search(claim_line) or _PACKET_TRAP_RE.search(span):
            return "Provider cited an excluded packet date rather than primary-certificate evidence."
        if not page_text.strip():
            return None
        target_label = _TARGET_DATE_LABELS[field_name]
        if target_label.search(claim_line):
            if _target_label_has_noncurrent_modifier(claim_line, target_label):
                return "Provider cited a non-current or proposed date rather than the active certificate field."
            if not _value_follows_target_label(claim_line, raw_value or "", target_label):
                return "Provider date value was not bound to its target label on the claim line."
        else:
            preceding_lines = _preceding_nonblank_claim_lines(page_text, span=span, raw_value=raw_value or "")
            preceding_line = preceding_lines[0] if preceding_lines else None
            if (
                preceding_line is None
                or not _is_bare_target_label(preceding_line, target_label)
                or not _is_bare_value_line(claim_line, raw_value or "")
            ):
                return "Provider date evidence did not bind the value to the required certificate field label."

    return None


def _is_placeholder_value(value: str) -> bool:
    cleaned = _normalize_for_span_match(value)
    compact = re.sub(r"\s+", "", cleaned)
    return bool(_PLACEHOLDER_VALUE_RE.fullmatch(cleaned) or _PLACEHOLDER_VALUE_RE.fullmatch(compact))


def _literal_source_span(provider_span: str, page_text: str) -> str | None:
    """Return the exact persisted-page slice supporting a provider claim."""

    index = page_text.find(provider_span)
    return None if index < 0 else page_text[index : index + len(provider_span)]


def _claim_line_context(span: str, page_text: str, *, raw_value: str | None) -> str:
    """Return the exact line containing the claimed value occurrence.

    Trap labels on that line win over valid labels elsewhere in a nearby block.
    This prevents a value-only citation from borrowing certificate semantics from
    an adjacent Effective/Expiry line.
    """

    span_index = page_text.find(span)
    if span_index < 0:
        return span
    value_offset = span.find(raw_value) if raw_value else -1
    claim_index = span_index + (value_offset if value_offset >= 0 else 0)
    line_start = page_text.rfind("\n", 0, claim_index) + 1
    line_end = page_text.find("\n", claim_index)
    if line_end < 0:
        line_end = len(page_text)
    return page_text[line_start:line_end]


def _claim_is_in_primary_scope(
    pages: tuple[DocumentPage, ...],
    *,
    page_num: int,
    span: str,
    raw_value: str | None,
    visual_region_claim: bool,
) -> bool:
    """Resolve packet section ownership across ordered page boundaries.

    Primary and excluded markers are recognized only as strong heading lines.
    Inline prose mentioning an attachment cannot reopen primary scope, while a
    continuation page inherits the latest strong section heading from earlier
    pages. A mixed-content visual logo has no text offset, so it is accepted only
    when the cited page ends in unambiguous primary scope.
    """

    return (
        _claim_primary_block_id(
            pages,
            page_num=page_num,
            span=span,
            raw_value=raw_value,
            visual_region_claim=visual_region_claim,
        )
        is not None
    )


def _claim_primary_block_id(
    pages: tuple[DocumentPage, ...],
    *,
    page_num: int,
    span: str,
    raw_value: str | None,
    visual_region_claim: bool,
) -> int | None:
    section_state = _PacketSectionState()
    for page in sorted(pages, key=lambda candidate: candidate.page_num):
        page_text = page.page_text or ""
        if page.page_num != page_num:
            section_state = _scan_section_state(page_text, initial=section_state)
            continue

        if visual_region_claim:
            section_state = _scan_section_state(page_text, initial=section_state)
            return section_state.active_primary_block

        span_index = page_text.find(span)
        if span_index < 0:
            return None
        value_offset = span.find(raw_value) if raw_value else -1
        claim_index = span_index + (value_offset if value_offset >= 0 else 0)
        section_state = _scan_section_state(
            page_text,
            initial=section_state,
            through_offset=claim_index,
        )
        return section_state.active_primary_block
    return None


def _enforce_single_primary_block(
    fields: Mapping[SDFFieldName, ExtractedField],
    *,
    pages: tuple[DocumentPage, ...],
) -> dict[SDFFieldName, ExtractedField]:
    """Reject cross-certificate field mixing after text/visual merge."""

    blocks: dict[SDFFieldName, int] = {}
    pages_by_number = {page.page_num: page for page in pages}
    for field_name, field in fields.items():
        if field.review_state is ReviewState.ABSTAINED or not field.evidence.verbatim_span:
            continue
        source_page = pages_by_number.get(field.evidence.page_num)
        if source_page is None:
            continue
        page_text = source_page.page_text or ""
        visual_without_text_offset = field.evidence.evidence_type == "visual" and (
            not page_text.strip() or field.evidence.verbatim_span not in page_text
        )
        block_id = _claim_primary_block_id(
            pages,
            page_num=field.evidence.page_num,
            span=field.evidence.verbatim_span,
            raw_value=field.raw_value,
            visual_region_claim=visual_without_text_offset,
        )
        if block_id is not None:
            blocks[field_name] = block_id

    unique_blocks = set(blocks.values())
    if len(unique_blocks) <= 1:
        return dict(fields)

    selected_block = blocks.get(SDFFieldName.DOC_TYPE)
    if selected_block is None:
        counts = {block_id: list(blocks.values()).count(block_id) for block_id in unique_blocks}
        selected_block = min(unique_blocks, key=lambda block_id: (-counts[block_id], block_id))

    consistent = dict(fields)
    for field_name, block_id in blocks.items():
        if block_id == selected_block:
            continue
        field = fields[field_name]
        consistent[field_name] = ExtractedField(
            field_name=field_name,
            raw_value=None,
            normalized_value=None,
            normalized_date=None,
            confidence=0.0,
            evidence=SourceEvidence(page_num=field.evidence.page_num, bbox=field.evidence.bbox),
            review_state=ReviewState.ABSTAINED,
            abstention_reason="Field evidence belonged to a different primary certificate block.",
        )
    return consistent


def _scan_section_state(
    page_text: str,
    *,
    initial: _PacketSectionState,
    through_offset: int | None = None,
) -> _PacketSectionState:
    state = initial
    cursor = 0
    for line_with_ending in page_text.splitlines(keepends=True):
        if through_offset is not None and cursor > through_offset:
            break
        line = line_with_ending.rstrip("\r\n")
        if _is_nonprimary_heading_line(line):
            state = _PacketSectionState(
                active_primary_block=None,
                next_primary_block=state.next_primary_block,
            )
        else:
            primary_title = _primary_heading_identity(line)
            if primary_title is not None:
                state = _PacketSectionState(
                    active_primary_block=state.next_primary_block,
                    next_primary_block=state.next_primary_block + 1,
                )
        cursor += len(line_with_ending)
    return state


def _is_nonprimary_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_primary_heading_line(stripped):
        return False
    return bool(
        _NONPRIMARY_ALIAS_HEADING_RE.fullmatch(stripped)
        or _NONPRIMARY_HEADING_RE.search(stripped)
        or _GENERIC_DOCUMENT_HEADING_RE.fullmatch(stripped)
    )


def _is_primary_heading_line(line: str) -> bool:
    return _primary_heading_identity(line) is not None


def _primary_heading_identity(line: str) -> str | None:
    candidate = line.strip()
    labeled_value = _line_labeled_value(candidate, _DOC_TYPE_LABEL_RE)
    if labeled_value is not None:
        candidate = labeled_value
    if len(candidate) > 160:
        return None
    if _NONPRIMARY_TITLE_MODIFIER_RE.search(candidate):
        return None
    specification_match = _SPECIFICATION_TITLE_PREFIX_RE.match(candidate)
    if specification_match is not None:
        suffix = candidate[specification_match.end() :].strip(" \t:#-")
        if not suffix:
            return _normalize_for_span_match(candidate)
        identifier_match = re.fullmatch(
            r"(?:(?:no\.?|number|id)\s*[:#-]?\s*)?([A-Z0-9][A-Z0-9_-]{1,31})",
            suffix,
        )
        if identifier_match is None:
            return None
        identifier = identifier_match.group(1)
        if not any(character.isdigit() for character in identifier) and identifier != identifier.upper():
            return None
        return _normalize_for_span_match(candidate)
    match = _PRIMARY_CERTIFICATE_RE.match(candidate)
    if match is None:
        return None
    suffix = candidate[match.end() :].strip()
    if not suffix:
        return _normalize_for_span_match(candidate)
    if len(suffix) > 80 or _HEADING_PROSE_RE.search(suffix):
        return None
    return _normalize_for_span_match(candidate) if len(suffix.split()) <= 8 else None


def _vendor_candidate_is_supported(
    raw_value: str | None,
    *,
    span: str,
    claim_line: str,
    page_text: str,
    visual_region_claim: bool,
) -> bool:
    if raw_value is None or _vendor_decoy_label_present(claim_line) or _vendor_decoy_label_present(span):
        return False

    labeled_value = _line_labeled_value(claim_line, _VENDOR_LABEL_RE)
    if labeled_value is not None:
        return raw_value == labeled_value and _VENDOR_ATTRIBUTE_VALUE_RE.search(labeled_value) is None

    if _MANUFACTURING_RELATION_RE.search(claim_line):
        return _vendor_is_bound_to_manufacturing_context(raw_value, claim_line)

    for preceding_line in _preceding_nonblank_claim_lines(page_text, span=span, raw_value=raw_value):
        if _VENDOR_HEADER_LABEL_RE.fullmatch(preceding_line):
            return raw_value == claim_line.strip()
        if _vendor_decoy_label_present(preceding_line):
            return False

    # OCR-missed logo/header evidence is allowed only through the narrow visual
    # branch: it is image-backed, bbox-cited, primary-page scoped, and forced to
    # needs_review by the caller.
    if visual_region_claim:
        return raw_value in span

    if raw_value not in claim_line:
        return False
    return _is_bounded_header_identity(raw_value, claim_line=claim_line, page_text=page_text)


def _preceding_nonblank_claim_lines(
    page_text: str,
    *,
    span: str,
    raw_value: str,
) -> tuple[str, ...]:
    span_index = page_text.find(span)
    if span_index < 0:
        return ()
    value_offset = span.find(raw_value)
    claim_index = span_index + (value_offset if value_offset >= 0 else 0)
    line_start = page_text.rfind("\n", 0, claim_index) + 1
    preceding: list[str] = []
    for line in reversed(page_text[:line_start].splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_primary_heading_line(stripped) or _is_nonprimary_heading_line(stripped):
            break
        preceding.append(stripped)
        if _VENDOR_HEADER_LABEL_RE.fullmatch(stripped):
            break
    return tuple(preceding)


def _vendor_decoy_label_present(value: str) -> bool:
    return bool(_VENDOR_DECOY_LABEL_RE.search(value) or _VENDOR_TABLE_DECOY_HEADER_RE.fullmatch(value.strip()))


def _vendor_is_bound_to_manufacturing_context(raw_value: str, line: str) -> bool:
    escaped_value = re.escape(raw_value)
    return bool(
        re.search(
            rf"\b(?:manufactured|produced|assembled|supplied|issued)\s+(?:by|at)\s+{escaped_value}"
            rf"(?=\s*(?:$|[,;|()]|\b(?:facility|plant|site)\b))",
            line,
            re.IGNORECASE,
        )
        or re.search(
            rf"\bin\s+(?:an?\s+)?{escaped_value}\s+(?:facility|plant|site)\b",
            line,
            re.IGNORECASE,
        )
    )


def _is_bare_target_label(line: str, target_label: re.Pattern[str]) -> bool:
    match = target_label.search(line)
    if match is None:
        return False
    return not line[: match.start()].strip(" \t:-") and not line[match.end() :].strip(" \t:-")


def _is_bare_value_line(line: str, raw_value: str) -> bool:
    if not raw_value:
        return False
    value_index = line.find(raw_value)
    if value_index < 0:
        return False
    remainder = line[:value_index] + line[value_index + len(raw_value) :]
    return not remainder.strip(" \t:|-–—()[]")


def _value_follows_target_label(line: str, raw_value: str, target_label: re.Pattern[str]) -> bool:
    if not raw_value:
        return False
    label_match = target_label.search(line)
    if label_match is None:
        return False
    value_index = line.find(raw_value, label_match.end())
    if value_index < 0:
        return False
    separator = line[label_match.end() : value_index]
    return bool(
        re.fullmatch(
            r"\s*(?:[:\-–—]\s*)?(?:\([DMY./\-\s]+\)\s*)?(?:[:\-–—]\s*)?",
            separator,
            re.IGNORECASE,
        )
    )


def _target_label_has_noncurrent_modifier(line: str, target_label: re.Pattern[str]) -> bool:
    match = target_label.search(line)
    return match is not None and bool(_NONCURRENT_DATE_MODIFIER_RE.search(line[: match.start()]))


def _is_bounded_header_identity(raw_value: str, *, claim_line: str, page_text: str) -> bool:
    """Allow an unlabeled brand only when a nearby address proves header identity."""

    if raw_value != claim_line.strip():
        return False
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    try:
        claim_line_index = lines.index(claim_line.strip())
    except ValueError:
        return False

    heading_indexes = [index for index, line in enumerate(lines[: claim_line_index + 1]) if _is_primary_heading_line(line)]
    if not heading_indexes or claim_line_index - heading_indexes[-1] > 5:
        return False
    nearby = "\n".join(lines[claim_line_index + 1 : claim_line_index + 4])
    return bool(_ADDRESS_OR_CONTACT_RE.search(nearby))


def _has_bounded_visual_region(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    coordinates: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        candidate = value.get(key)
        if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
            return False
        number = float(candidate)
        if not math.isfinite(number):
            return False
        coordinates[key] = number
    return coordinates["x"] >= 0 and coordinates["y"] >= 0 and coordinates["width"] > 0 and coordinates["height"] > 0


def _line_labeled_value(line: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.fullmatch(line)
    return match.group("value").strip() if match is not None else None


def _normalize_for_span_match(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_allowlisted_date(value: str) -> tuple[date | None, str | None]:
    stripped = value.strip()

    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", stripped)
    if match:
        return _safe_date(*map(int, match.groups())), None

    match = re.fullmatch(r"(\d{4})([-/.])(\d{2})\2(\d{2})", stripped)
    if match:
        year_text, _, month_text, day_text = match.groups()
        return _safe_date(int(year_text), int(month_text), int(day_text)), None

    match = re.fullmatch(r"(\d{4})-(\d{2})", stripped)
    if match:
        year, month = map(int, match.groups())
        return (None, stripped) if _safe_date(year, month, 1) is not None else (None, None)

    match = re.fullmatch(r"(\d{1,2})/(\d{4})", stripped)
    if match:
        month, year = map(int, match.groups())
        return (None, f"{year:04d}-{month:02d}") if _safe_date(year, month, 1) is not None else (None, None)

    match = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{4})", stripped)
    if match:
        month_text, year_text = match.groups()
        month = _MONTH_NUMBERS.get(month_text.casefold())
        year = int(year_text)
        return (None, f"{year:04d}-{month:02d}") if _safe_date(year, month, 1) is not None else (None, None)

    match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", stripped)
    if match:
        return _safe_date(*map(int, match.groups())), None

    match = re.fullmatch(r"(\d{1,2})([/\.])(\d{1,2})\2(\d{4})", stripped)
    if match:
        first, _, second, year_text = match.groups()
        first_number, second_number, year = int(first), int(second), int(year_text)
        if first_number > 12 >= second_number:
            return _safe_date(year, second_number, first_number), None
        if second_number > 12 >= first_number:
            return _safe_date(year, first_number, second_number), None
        return None, None

    match = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3,9})-(\d{4})", stripped)
    if match:
        day_text, month_text, year_text = match.groups()
        return _safe_date(int(year_text), _MONTH_NUMBERS.get(month_text.casefold()), int(day_text)), None

    match = re.fullmatch(r"(\d{1,2})([A-Za-z]{3,9})(\d{4})", stripped)
    if match:
        day_text, month_text, year_text = match.groups()
        return _safe_date(int(year_text), _MONTH_NUMBERS.get(month_text.casefold()), int(day_text)), None

    match = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})", stripped)
    if match:
        month_text, day_text, year_text = match.groups()
        return _safe_date(int(year_text), _MONTH_NUMBERS.get(month_text.casefold()), int(day_text)), None

    return None, None


def _safe_date(year: int, month: int | None, day: int) -> date | None:
    if month is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _is_json_compatible(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_compatible(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_compatible(item) for key, item in value.items())
    return False


def _clamp_confidence(value: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        return None
    return numeric


def _validated_confidence_threshold(value: float, *, run_id: str, doc_id: str) -> float:
    threshold = _clamp_confidence(value)
    if threshold is None:
        raise InvalidConfidenceThresholdError(
            "Confidence review threshold must be a finite value from zero through one.",
            run_id=run_id,
            doc_id=doc_id,
        )
    return threshold
