"""Offline SDF extraction pipeline orchestration.

The pipeline connects ingested pages to a provider, normalizes exactly six SDF
fields, verifies cited text spans against stored page text, computes conservative
risk metadata, and persists dashboard-ready rows. Diagnostics are typed and
non-secret: run IDs, trace IDs, provider names/classes, and reason codes only.
"""
from __future__ import annotations

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
from src.extraction.repository import upsert_extraction_record
from src.extraction.risk import compute_record_risk
from src.eval.repository import ExtractionUsageObservationRow, insert_extraction_usage_observation
from src.tracing import observe, safe_update_current_trace


LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.75
_PLACEHOLDER_VALUE_RE = re.compile(
    r"^(?:x{2,}(?:[-/][a-z]{3}|[-/]x{2,})*|m{3}/y{4}|a{3}n{3,}|assigned|tbd|to be determined)$",
    re.IGNORECASE,
)
_DELIVERY_DATE_RE = re.compile(r"\bdelivery\s+date\b", re.IGNORECASE)
_RETEST_DATE_RE = re.compile(r"\bretest\s+date\b", re.IGNORECASE)
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


VISUAL_FALLBACK_ELIGIBLE_REASON_CODES: dict[ReviewState, str] = {
    ReviewState.ABSTAINED: "field_abstained",
    ReviewState.NEEDS_REVIEW: "field_needs_review",
}
VISUAL_FALLBACK_SKIP_NO_ELIGIBLE_FIELDS = "no_eligible_fields"
VISUAL_FALLBACK_SKIP_MISSING_PAGE_IMAGES = "missing_page_images"
VISUAL_FALLBACK_SKIP_NOT_CONFIGURED = "not_configured"


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

    pages_with_images = tuple(page for page in pages if page.image_blob is not None)
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
    return VisualFallbackProviderResult(
        plan=plan,
        provider_result=visual_provider.extract_visual_fields(document=document, request=plan.request, run_id=run_id),
    )


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
    visual_fields = _normalize_fields(
        provider_result,
        pages=image_pages,
        low_confidence_threshold=low_confidence_threshold,
    )
    merged_fields = _merge_visual_fallback_fields(text_fields, visual_fields)
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
        elif current.review_state is ReviewState.NEEDS_REVIEW and candidate.review_state is ReviewState.PENDING:
            merged[field_name] = candidate
    return merged


def _visual_provider_error_reason(exc: BaseException) -> str:
    """Return a sanitized provider error class/reason code without exception text."""

    reason_code = getattr(exc, "reason_code", None)
    if isinstance(reason_code, str) and reason_code:
        return reason_code
    return exc.__class__.__name__


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
        loaded = load_document_pages(db_path, doc_id, include_image_bytes=False)
        if loaded is None:
            raise DocumentNotFoundError("Document metadata was not found for extraction.", run_id=effective_run_id, doc_id=doc_id)
        _validate_pages_for_extraction(loaded, run_id=effective_run_id)

        provider_started_at = perf_counter()
        provider_result = provider.extract_fields(
            document=loaded.document,
            pages=loaded.pages,
            run_id=effective_run_id,
        )
        provider_latency_ms = (perf_counter() - provider_started_at) * 1000
        fields = _normalize_fields(
            provider_result,
            pages=loaded.pages,
            low_confidence_threshold=low_confidence_threshold,
        )
        visual_outcome = _run_visual_fallback_stage(
            db_path,
            document=loaded.document,
            text_fields=fields,
            text_pages=loaded.pages,
            run_id=effective_run_id,
            visual_provider=visual_provider,
            low_confidence_threshold=low_confidence_threshold,
        )
        fields = visual_outcome.merged_fields

        record = SDFExtractionRecord(
            doc_id=loaded.document.doc_id,
            filename=loaded.document.filename,
            fields=fields,
            trace_id=provider_result.trace_id,
            run_id=effective_run_id,
            extracted_at=datetime.now(timezone.utc),
        )
        risk = compute_record_risk(record, today=today or date.today())
        record.risk_level = risk.risk_level
        record.risk_reason = risk.risk_reason
        record.compliance_status = risk.compliance_status
        record.age_days = risk.age_days

        upsert_extraction_record(db_path, record)
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
            trace_id=provider_result.trace_id,
            provider_name=provider_result.provider_name,
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
            status=status,
            latency_ms=latency_ms,
            input_tokens=usage.input_tokens if usage is not None else None,
            output_tokens=usage.output_tokens if usage is not None else None,
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
            status=outcome.status,
            latency_ms=outcome.latency_ms,
            input_tokens=usage.input_tokens if usage is not None else None,
            output_tokens=usage.output_tokens if usage is not None else None,
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
    if not any((page.page_text or "").strip() for page in loaded.pages):
        raise NoPageTextError("Document pages contain no extractable text.", run_id=run_id, doc_id=loaded.document.doc_id)


def _normalize_fields(
    provider_result: ProviderExtractionResult,
    *,
    pages: tuple[DocumentPage, ...],
    low_confidence_threshold: float,
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
        )
        for field_name in SDFFieldName
    }


def _normalize_field(
    field_name: SDFFieldName,
    payload: ProviderFieldPayload | None,
    *,
    pages: tuple[DocumentPage, ...],
    low_confidence_threshold: float,
) -> ExtractedField:
    if payload is None:
        return _abstained_field(field_name, "Provider did not return this required SDF field.")

    explicit_reason = _clean_text(payload.abstention_reason)
    if explicit_reason and not _has_payload_value(payload):
        return _abstained_field(field_name, explicit_reason, payload=payload)
    if not _has_payload_value(payload):
        return _abstained_field(field_name, "Provider returned no value for this required SDF field.", payload=payload)
    if payload.evidence is None:
        return _abstained_field(field_name, "Provider returned no source evidence for this required SDF field.", payload=payload)

    page = next((candidate for candidate in pages if candidate.page_num == payload.evidence.page_num), None)
    if page is None:
        return _abstained_field(field_name, "Provider cited a page number that was not persisted for this document.", payload=payload)
    if not _is_json_compatible(payload.evidence.bbox):
        return _abstained_field(field_name, "Provider returned a non-JSON-serializable source bounding box.", payload=payload)

    span = _clean_text(payload.evidence.verbatim_span)
    if span is None:
        return _abstained_field(field_name, "Provider returned no verbatim source span for this required SDF field.", payload=payload)

    # Tiered evidence (D027, supersedes D026):
    # - Page has stored text + span matches  -> text-grounded (evidence_type="text").
    # - Page has stored text + span no match -> abstain (verbatim grounding required).
    # - Page stored text is EMPTY            -> visual-grounded: accept the
    #   image-grounded value, evidence_type="visual", needs_review forced on.
    page_has_text = bool((page.page_text or "").strip())
    if page_has_text and not _span_matches_page_text(span, page.page_text or ""):
        return _abstained_field(field_name, "Provider source span was not found in the cited page text.", payload=payload)

    # Trap/placeholder exclusions must hold for both tiers.
    guard_reason = _field_value_guard_reason(field_name, payload, span)
    if guard_reason is not None:
        return _abstained_field(field_name, guard_reason, payload=payload)

    confidence = _clamp_confidence(payload.confidence)
    if page_has_text:
        evidence_type = "text"
        review_state = ReviewState.NEEDS_REVIEW if confidence < low_confidence_threshold else ReviewState.PENDING
    else:
        # Visual claims are page-cited but not verbatim-verified: always flag for review.
        evidence_type = "visual"
        review_state = ReviewState.NEEDS_REVIEW
    return ExtractedField(
        field_name=field_name,
        raw_value=_clean_text(payload.raw_value),
        normalized_value=payload.normalized_value,
        normalized_date=_parse_iso_date(payload.normalized_date),
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
) -> str | None:
    value_fragments = [
        _clean_text(payload.raw_value),
        _clean_text(str(payload.normalized_value)) if payload.normalized_value is not None else None,
        _clean_text(str(payload.normalized_date)) if payload.normalized_date is not None else None,
    ]
    if any(_is_placeholder_value(fragment) for fragment in value_fragments if fragment is not None):
        return "Provider returned a placeholder/redacted value rather than a real field value."

    if field_name is SDFFieldName.EFFECTIVE_DATE and _DELIVERY_DATE_RE.search(span):
        return "Provider mapped Delivery Date to effective_date, but delivery dates are not effective dates."

    if field_name is SDFFieldName.EXPIRY_DATE and _RETEST_DATE_RE.search(span):
        return "Provider mapped Retest Date to expiry_date, but retest dates are not expiry dates."

    return None


def _is_placeholder_value(value: str) -> bool:
    cleaned = _normalize_for_span_match(value)
    compact = re.sub(r"\s+", "", cleaned)
    return bool(_PLACEHOLDER_VALUE_RE.fullmatch(cleaned) or _PLACEHOLDER_VALUE_RE.fullmatch(compact))


def _span_matches_page_text(span: str, page_text: str) -> bool:
    return _normalize_for_span_match(span) in _normalize_for_span_match(page_text)


def _normalize_for_span_match(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_iso_date(value: date | str | None) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _is_json_compatible(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_compatible(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_compatible(item) for key, item in value.items())
    return False


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
