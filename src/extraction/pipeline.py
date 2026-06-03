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
from typing import Any
from uuid import uuid4

try:
    from langfuse.decorators import langfuse_context
except Exception:  # pragma: no cover - exercised only when optional Langfuse is absent/broken
    langfuse_context = None  # type: ignore[assignment]

from src.db.queries import DocumentPage, LoadedDocumentPages, load_document_pages
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.providers import ProviderExtractionResult, ProviderFieldPayload, SDFExtractionProvider
from src.extraction.repository import upsert_extraction_record
from src.extraction.risk import compute_record_risk
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


@observe(name="sdf_extract_document")
def extract_document(
    db_path: str,
    doc_id: str,
    provider: SDFExtractionProvider,
    *,
    today: date | None = None,
    low_confidence_threshold: float = LOW_CONFIDENCE_REVIEW_THRESHOLD,
    run_id: str | None = None,
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

        provider_result = provider.extract_fields(
            document=loaded.document,
            pages=loaded.pages,
            run_id=effective_run_id,
        )
        fields = _normalize_fields(
            provider_result,
            pages=loaded.pages,
            low_confidence_threshold=low_confidence_threshold,
        )

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
    if not _span_matches_page_text(span, page.page_text or ""):
        return _abstained_field(field_name, "Provider source span was not found in the cited page text.", payload=payload)

    guard_reason = _field_value_guard_reason(field_name, payload, span)
    if guard_reason is not None:
        return _abstained_field(field_name, guard_reason, payload=payload)

    confidence = _clamp_confidence(payload.confidence)
    review_state = ReviewState.NEEDS_REVIEW if confidence < low_confidence_threshold else ReviewState.PENDING
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
