"""Human-in-the-loop (HITL) review repository for extracted SDF fields.

Repository boundary (mirrors ``src/extraction/repository.py``): every SQL statement
is parameterized. Field values, corrected values, reviewer notes, and verbatim spans
are persisted only in explicit columns and are never logged or traced.

Reviews update only the *latest* tables (``extractions``, ``compliance_records``)
and append one row to the ``extraction_reviews`` audit table. Run-scoped history
tables are never written here, so human values cannot leak into model
extraction F1 (Phase 7 benchmark integrity).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from src.db.schema import _connect
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.repository import (
    _get_extraction_record_with_queries,
    _upsert_compliance_record,
    _upsert_extraction_field,
)
from src.extraction.risk import compute_record_risk
from src.tracing import observe, safe_update_current_trace

# Injectable test seams: tests monkeypatch both symbols. langfuse_context=None
# means "resolve the live v3 client lazily inside src.tracing".
_LANGFUSE_AVAILABLE: bool = True
langfuse_context: Any | None = None

# Values, notes, reviewer identity, and verbatim spans are deliberately absent.
_REVIEW_TRACE_ALLOWED_KEYS = frozenset(
    {
        "boundary",
        "doc_id",
        "field_name",
        "action",
        "previous_review_state",
        "review_id",
        "error_class",
    }
)


class ReviewAction(str, Enum):
    """Reviewer actions accepted by ``apply_field_review``."""

    APPROVE = "approve"
    CORRECT = "correct"
    CONFIRM_ABSENT = "confirm_absent"


class ReviewInputError(ValueError):
    """Typed, bounded review rejection. Only ``reason_code`` crosses UI/trace boundaries.

    Reason codes: unknown_field, unknown_action, record_not_found,
    approve_requires_value, value_required, value_too_long, note_too_long,
    source_page_required, source_page_out_of_range, invalid_date.
    """

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


CONFIRMED_ABSENT_PREFIX = "Reviewer confirmed:"
MAX_CORRECTED_VALUE_CHARS = 200
MAX_NOTE_CHARS = 1000
DATE_FIELDS: frozenset[SDFFieldName] = frozenset(
    {
        SDFFieldName.MANUFACTURING_DATE,
        SDFFieldName.EFFECTIVE_DATE,
        SDFFieldName.REVISION_DATE,
        SDFFieldName.EXPIRY_DATE,
    }
)
DEFAULT_REVIEWER = "demo-reviewer"
CONFIRMED_ABSENT_REASON = f"{CONFIRMED_ABSENT_PREFIX} field not present in document"
_MIN_REVIEW_YEAR = 1900
_MAX_REVIEW_YEAR = 2100


@dataclass(frozen=True)
class ReviewQueueItem:
    """One extracted field awaiting human review (dashboard-safe DTO)."""

    doc_id: str
    filename: str
    field_name: str
    current_value: str | None
    confidence: float
    source_page: int | None  # 0-indexed
    verbatim_span: str | None
    evidence_type: str
    review_state: str
    abstention_reason: str | None


@dataclass(frozen=True)
class ReviewOutcome:
    """Result of one applied review action."""

    review_id: int
    doc_id: str
    field_name: str
    action: str
    new_review_state: str
    risk_level: str | None
    compliance_needs_review: bool


_REVIEW_QUEUE_SQL = """
    SELECT e.doc_id, d.filename, e.field_name, e.field_value, e.normalized_value,
           e.confidence, e.source_page, e.verbatim_span, e.evidence_type,
           e.review_state, e.abstention_reason
    FROM extractions AS e
    JOIN documents AS d ON d.doc_id = e.doc_id
    WHERE (
            e.review_state IN ('needs_review', 'abstained')
            OR (e.confidence < ? AND COALESCE(e.review_state, '') <> 'reviewed')
          )
      AND COALESCE(e.abstention_reason, '') NOT LIKE 'Reviewer confirmed:%'
    ORDER BY e.confidence ASC, d.filename ASC, e.field_name ASC
"""


def list_review_queue(db_path: str, *, threshold: float) -> list[ReviewQueueItem]:
    """Return fields that need a human decision, lowest confidence first.

    Selected: ``needs_review`` or ``abstained`` fields, plus any not-yet-reviewed
    field whose confidence is below ``threshold``. Reviewer-confirmed-absent fields
    (abstention_reason prefixed ``Reviewer confirmed:``) are excluded. A later
    re-extraction overwrites abstention_reason, so such a field re-enters the queue
    naturally.
    """

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(_REVIEW_QUEUE_SQL, (float(threshold),)).fetchall()
    finally:
        conn.close()
    return [_queue_item_from_row(row) for row in rows]


def _queue_item_from_row(row: sqlite3.Row) -> ReviewQueueItem:
    current_value = row["normalized_value"] if row["normalized_value"] is not None else row["field_value"]
    return ReviewQueueItem(
        doc_id=row["doc_id"],
        filename=row["filename"],
        field_name=row["field_name"],
        current_value=current_value,
        confidence=float(row["confidence"]) if row["confidence"] is not None else 0.0,
        source_page=row["source_page"],
        verbatim_span=row["verbatim_span"],
        evidence_type=row["evidence_type"] if row["evidence_type"] is not None else "text",
        review_state=row["review_state"] if row["review_state"] is not None else "pending",
        abstention_reason=row["abstention_reason"],
    )



# Same-connection read of the latest record (mirrors get_extraction_record) so the
# read-modify-write happens inside the review's own IMMEDIATE transaction.
_LATEST_COMPLIANCE_SQL = """
    SELECT trace_id, run_id, extracted_at, risk_level, risk_reason, compliance_status, age_days
    FROM compliance_records
    WHERE doc_id = ?
"""
_LATEST_FIELDS_SQL = """
    SELECT field_name, field_value, confidence, source_page, source_bbox,
           verbatim_span, review_state, abstention_reason, normalized_value,
           evidence_type
    FROM extractions
    WHERE doc_id = ?
    ORDER BY field_name
"""
_PAGE_COUNT_SQL = "SELECT page_count FROM documents WHERE doc_id = ?"
_INSERT_REVIEW_SQL = """
    INSERT INTO extraction_reviews (
        doc_id, field_name, action, previous_value, new_value, previous_confidence,
        previous_review_state, source_page, reviewer, note, run_id, trace_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_CLEAR_FIELD_NEEDS_REVIEW_SQL = "UPDATE extractions SET needs_review = 0 WHERE doc_id = ? AND field_name = ?"
_UPDATE_DOCUMENT_REVIEW_SQL = "UPDATE compliance_records SET needs_review = ?, review_state = ? WHERE doc_id = ?"


@dataclass(frozen=True)
class _ValidatedReview:
    field_name: SDFFieldName
    action: ReviewAction
    corrected_value: str | None
    corrected_date: date | None
    source_page: int | None
    note: str | None
    reviewer: str


@observe(name="hitl.review", capture_input=False, capture_output=False)
def apply_field_review(
    db_path: str,
    *,
    doc_id: str,
    field_name: str | SDFFieldName,
    action: str | ReviewAction,
    corrected_value: str | None = None,
    source_page: int | None = None,
    note: str | None = None,
    reviewer: str = DEFAULT_REVIEWER,
    today: date | None = None,
    trace_id: str | None = None,
) -> ReviewOutcome:
    """Apply one reviewer decision to the latest extraction/compliance rows.

    Actions:
    - ``approve``: keep the value, mark the field reviewed (confidence 1.0). Not
      allowed on abstained fields (there is no value to approve).
    - ``correct``: replace the value with reviewer text (dates normalized to ISO),
      evidence_type ``human`` citing ``source_page`` (0-indexed), reviewed.
    - ``confirm_absent``: keep the field abstained with a ``Reviewer confirmed:``
      reason; it leaves the queue and counts as resolved for the document.

    Input is validated before any write (``ReviewInputError`` with a bounded
    ``reason_code``). The audit insert, the ``extractions`` update, the risk
    recompute, and the ``compliance_records`` update share one transaction and
    are rolled back together on any failure. This function never writes the
    run-history tables.
    """

    try:
        validated = _validate_review_request(
            field_name=field_name,
            action=action,
            corrected_value=corrected_value,
            source_page=source_page,
            note=note,
            reviewer=reviewer,
        )
        outcome, previous_review_state = _apply_validated_review(
            db_path,
            doc_id=doc_id,
            request=validated,
            today=today or date.today(),
            trace_id=trace_id,
        )
    except Exception as exc:
        _safe_update_trace_metadata(
            {
                "boundary": "hitl.review",
                "doc_id": doc_id,
                "field_name": _known_field_name(field_name),
                "action": _known_action(action),
                "error_class": _error_class(exc),
            }
        )
        raise

    _safe_update_trace_metadata(
        {
            "boundary": "hitl.review",
            "doc_id": outcome.doc_id,
            "field_name": outcome.field_name,
            "action": outcome.action,
            "previous_review_state": previous_review_state,
            "review_id": outcome.review_id,
        }
    )
    return outcome


def _validate_review_request(
    *,
    field_name: str | SDFFieldName,
    action: str | ReviewAction,
    corrected_value: str | None,
    source_page: int | None,
    note: str | None,
    reviewer: str,
) -> _ValidatedReview:
    try:
        parsed_field = SDFFieldName(field_name)
    except ValueError:
        raise ReviewInputError("unknown_field") from None
    try:
        parsed_action = ReviewAction(action)
    except ValueError:
        raise ReviewInputError("unknown_action") from None

    clean_note = _strip_or_none(note)
    if clean_note is not None and len(clean_note) > MAX_NOTE_CHARS:
        raise ReviewInputError("note_too_long")
    clean_reviewer = _strip_or_none(reviewer) or DEFAULT_REVIEWER

    clean_value: str | None = None
    corrected_date: date | None = None
    page: int | None = None
    if parsed_action == ReviewAction.CORRECT:
        clean_value = _strip_or_none(corrected_value)
        if clean_value is None:
            raise ReviewInputError("value_required")
        if len(clean_value) > MAX_CORRECTED_VALUE_CHARS:
            raise ReviewInputError("value_too_long")
        if source_page is None or isinstance(source_page, bool) or not isinstance(source_page, int) or source_page < 0:
            raise ReviewInputError("source_page_required")
        page = source_page
        if parsed_field in DATE_FIELDS:
            corrected_date = _parse_review_date(clean_value)

    return _ValidatedReview(
        field_name=parsed_field,
        action=parsed_action,
        corrected_value=clean_value,
        corrected_date=corrected_date,
        source_page=page,
        note=clean_note,
        reviewer=clean_reviewer,
    )


def _parse_review_date(value: str) -> date:
    """Parse a reviewer-entered date strictly; raise ``invalid_date`` on any doubt.

    ISO ``YYYY-MM-DD`` is taken as-is. Other formats (for example ``01-JAN-2024``)
    go through dateutil (month-first). Partial dates such as ``2024-05`` are
    rejected: dateutil would silently invent the missing day/month/year, which is
    unacceptable for a compliance date. Detection parses twice against two
    different defaults; any difference means a component was missing.
    """

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        from dateutil import parser as date_parser  # lazy: only needed for non-ISO input

        try:
            first = date_parser.parse(value, dayfirst=False, default=datetime(2000, 1, 1))
            second = date_parser.parse(value, dayfirst=False, default=datetime(2001, 2, 2))
        except (ValueError, OverflowError, TypeError):
            raise ReviewInputError("invalid_date") from None
        if first.date() != second.date():
            raise ReviewInputError("invalid_date")
        parsed = first.date()
    if not _MIN_REVIEW_YEAR <= parsed.year <= _MAX_REVIEW_YEAR:
        raise ReviewInputError("invalid_date")
    return parsed


def _apply_validated_review(
    db_path: str,
    *,
    doc_id: str,
    request: _ValidatedReview,
    today: date,
    trace_id: str | None,
) -> tuple[ReviewOutcome, str]:
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # IMMEDIATE takes the write lock before the read, so concurrent reviews of
        # the same document serialize and never recompute risk from a stale record.
        conn.execute("BEGIN IMMEDIATE")
        record = _get_extraction_record_with_queries(
            conn,
            doc_id=doc_id,
            compliance_sql=_LATEST_COMPLIANCE_SQL,
            compliance_params=(doc_id,),
            fields_sql=_LATEST_FIELDS_SQL,
            fields_params=(doc_id,),
        )
        if record is None:
            raise ReviewInputError("record_not_found")

        if request.source_page is not None:
            page_row = conn.execute(_PAGE_COUNT_SQL, (doc_id,)).fetchone()
            if page_row is None or request.source_page >= int(page_row["page_count"]):
                raise ReviewInputError("source_page_out_of_range")

        previous = record.fields[request.field_name]
        new_field = _reviewed_field(previous, request)

        cursor = conn.execute(
            _INSERT_REVIEW_SQL,
            (
                doc_id,
                request.field_name.value,
                request.action.value,
                _scalar_to_text(previous.value_for_dashboard),
                _scalar_to_text(new_field.value_for_dashboard),
                previous.confidence,
                previous.review_state.value,
                new_field.evidence.page_num,
                request.reviewer,
                request.note,
                record.run_id,
                trace_id,
            ),
        )
        review_id = int(cursor.lastrowid)

        # Keep the extraction trace link on the latest row; the review trace lives
        # on the audit row.
        _upsert_extraction_field(conn, doc_id, new_field, record.trace_id)
        if request.action == ReviewAction.CONFIRM_ABSENT:
            conn.execute(_CLEAR_FIELD_NEEDS_REVIEW_SQL, (doc_id, request.field_name.value))

        fields = dict(record.fields)
        fields[request.field_name] = new_field
        updated = record.model_copy(update={"fields": fields})
        risk = compute_record_risk(updated, today=today)
        updated = updated.model_copy(
            update={
                "risk_level": risk.risk_level,
                "risk_reason": risk.risk_reason,
                "compliance_status": risk.compliance_status,
                "age_days": risk.age_days,
            }
        )
        _upsert_compliance_record(conn, updated)

        unresolved = any(_is_unresolved(field) for field in fields.values())
        document_review_state = _document_review_state(fields.values(), unresolved=unresolved)
        conn.execute(_UPDATE_DOCUMENT_REVIEW_SQL, (int(unresolved), document_review_state, doc_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    outcome = ReviewOutcome(
        review_id=review_id,
        doc_id=doc_id,
        field_name=request.field_name.value,
        action=request.action.value,
        new_review_state=new_field.review_state.value,
        risk_level=updated.risk_level,
        compliance_needs_review=unresolved,
    )
    return outcome, previous.review_state.value


def _reviewed_field(previous: ExtractedField, request: _ValidatedReview) -> ExtractedField:
    if request.action == ReviewAction.APPROVE:
        if previous.review_state == ReviewState.ABSTAINED:
            raise ReviewInputError("approve_requires_value")
        payload = previous.model_dump(exclude={"needs_review", "value_for_dashboard"})
        payload.update({"review_state": ReviewState.REVIEWED, "confidence": 1.0})
        return ExtractedField.model_validate(payload)

    if request.action == ReviewAction.CORRECT:
        value = request.corrected_value
        normalized: str | None = request.corrected_date.isoformat() if request.corrected_date else value
        return ExtractedField(
            field_name=request.field_name,
            raw_value=value,
            normalized_value=normalized,
            normalized_date=request.corrected_date,
            confidence=1.0,
            evidence=SourceEvidence(
                page_num=request.source_page,
                verbatim_span=value,
                evidence_type="human",
            ),
            review_state=ReviewState.REVIEWED,
            abstention_reason=None,
        )

    return ExtractedField(
        field_name=request.field_name,
        confidence=previous.confidence,
        evidence=previous.evidence,
        review_state=ReviewState.ABSTAINED,
        abstention_reason=CONFIRMED_ABSENT_REASON,
    )


def _is_confirmed_absent(field: ExtractedField) -> bool:
    return field.review_state == ReviewState.ABSTAINED and (field.abstention_reason or "").startswith(
        CONFIRMED_ABSENT_PREFIX
    )


def _is_unresolved(field: ExtractedField) -> bool:
    if field.review_state == ReviewState.NEEDS_REVIEW:
        return True
    return field.review_state == ReviewState.ABSTAINED and not _is_confirmed_absent(field)


def _document_review_state(fields: Any, *, unresolved: bool) -> str:
    if unresolved:
        return ReviewState.NEEDS_REVIEW.value
    if all(field.review_state == ReviewState.REVIEWED or _is_confirmed_absent(field) for field in fields):
        return ReviewState.REVIEWED.value
    return ReviewState.PENDING.value


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _scalar_to_text(value: str | int | float | bool | None) -> str | None:
    return None if value is None else str(value)


def _known_field_name(field_name: str | SDFFieldName) -> str | None:
    try:
        return SDFFieldName(field_name).value
    except ValueError:
        return None


def _known_action(action: str | ReviewAction) -> str | None:
    try:
        return ReviewAction(action).value
    except ValueError:
        return None


def _error_class(exc: BaseException) -> str:
    reason_code = getattr(exc, "reason_code", None)
    if isinstance(reason_code, str) and reason_code:
        return reason_code
    return exc.__class__.__name__


def _safe_update_trace_metadata(metadata: dict[str, Any]) -> None:
    """Attach allowlisted review diagnostics; never values, notes, or reviewer text."""

    if not _LANGFUSE_AVAILABLE:
        return
    safe_update_current_trace(
        tags=["hitl", "review"],
        metadata={key: value for key, value in metadata.items() if value is not None},
        allowed_metadata_keys=_REVIEW_TRACE_ALLOWED_KEYS,
        context=langfuse_context,
    )


__all__ = [
    "CONFIRMED_ABSENT_PREFIX",
    "DATE_FIELDS",
    "MAX_CORRECTED_VALUE_CHARS",
    "MAX_NOTE_CHARS",
    "ReviewAction",
    "ReviewInputError",
    "ReviewOutcome",
    "ReviewQueueItem",
    "apply_field_review",
    "list_review_queue",
]
