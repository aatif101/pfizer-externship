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
from enum import Enum

from src.db.schema import _connect
from src.extraction.models import SDFFieldName


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


__all__ = [
    "CONFIRMED_ABSENT_PREFIX",
    "DATE_FIELDS",
    "MAX_CORRECTED_VALUE_CHARS",
    "MAX_NOTE_CHARS",
    "ReviewAction",
    "ReviewInputError",
    "ReviewOutcome",
    "ReviewQueueItem",
    "list_review_queue",
]
