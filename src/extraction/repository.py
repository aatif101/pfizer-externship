"""SQLite persistence helpers for validated SDF extraction records.

Repository boundary: callers pass already-validated Pydantic models. All SQL uses
parameterized placeholders; source evidence text is persisted only in explicit
evidence columns and is never logged here.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from src.db.schema import _connect
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence


_FIELD_ORDER: tuple[SDFFieldName, ...] = tuple(SDFFieldName)
_COMPLIANCE_COLUMNS: tuple[str, ...] = (
    "doc_id",
    "doc_type",
    "vendor_name",
    "manufacturing_date",
    "effective_date",
    "revision_date",
    "expiry_date",
    "aggregate_confidence",
    "review_state",
    "needs_review",
    "trace_id",
    "run_id",
    "extracted_at",
    "risk_level",
    "risk_reason",
    "compliance_status",
    "age_days",
    "source_page",
    "source_bbox",
    "source_verbatim_span",
)


def upsert_extraction_field(db_path: str, doc_id: str, field: ExtractedField, trace_id: str | None = None) -> None:
    """Insert or update one field-level extraction row.

    Raises sqlite3.IntegrityError when ``doc_id`` does not exist, preserving the
    database FK as the source of truth for parent-document validity.
    """

    conn = _connect(db_path)
    try:
        _upsert_extraction_field(conn, doc_id, field, trace_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_extraction_record(db_path: str, record: SDFExtractionRecord) -> None:
    """Persist six field rows plus one dashboard-ready compliance row idempotently."""

    conn = _connect(db_path)
    try:
        for field_name in _FIELD_ORDER:
            _upsert_extraction_field(conn, record.doc_id, record.fields[field_name], record.trace_id)
        _upsert_compliance_record(conn, record)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_extraction_record(db_path: str, doc_id: str) -> SDFExtractionRecord | None:
    """Return a validated extraction record reconstructed from SQLite, if present."""

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        document = conn.execute(
            "SELECT doc_id, filename FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        if document is None:
            return None

        compliance = conn.execute(
            """
            SELECT trace_id, run_id, extracted_at, risk_level, risk_reason, compliance_status, age_days
            FROM compliance_records
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if compliance is None:
            return None

        rows = conn.execute(
            """
            SELECT field_name, field_value, confidence, source_page, source_bbox,
                   verbatim_span, review_state, abstention_reason, normalized_value
            FROM extractions
            WHERE doc_id = ?
            ORDER BY field_name
            """,
            (doc_id,),
        ).fetchall()
    finally:
        conn.close()

    fields = {_field_from_row(row).field_name: _field_from_row(row) for row in rows}
    if set(fields) != set(SDFFieldName):
        return None

    return SDFExtractionRecord(
        doc_id=document["doc_id"],
        filename=document["filename"],
        fields=fields,
        trace_id=compliance["trace_id"],
        run_id=compliance["run_id"],
        extracted_at=_parse_datetime(compliance["extracted_at"]),
        risk_level=compliance["risk_level"],
        risk_reason=compliance["risk_reason"],
        compliance_status=compliance["compliance_status"],
        age_days=compliance["age_days"],
    )


def list_compliance_records(db_path: str) -> list[dict[str, Any]]:
    """List dashboard-ready compliance rows in deterministic S04-friendly order."""

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            SELECT {", ".join(_COMPLIANCE_COLUMNS)}
            FROM compliance_records
            ORDER BY expiry_date IS NULL, expiry_date ASC, vendor_name ASC, doc_id ASC
            """
        ).fetchall()
        return [{column: row[column] for column in _COMPLIANCE_COLUMNS} for row in rows]
    finally:
        conn.close()


def _upsert_extraction_field(
    conn: sqlite3.Connection,
    doc_id: str,
    field: ExtractedField,
    trace_id: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO extractions (
            doc_id, field_name, field_value, confidence, source_page, source_bbox,
            verbatim_span, trace_id, needs_review, review_state, abstention_reason,
            normalized_value, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(doc_id, field_name) DO UPDATE SET
            field_value = excluded.field_value,
            confidence = excluded.confidence,
            source_page = excluded.source_page,
            source_bbox = excluded.source_bbox,
            verbatim_span = excluded.verbatim_span,
            trace_id = excluded.trace_id,
            needs_review = excluded.needs_review,
            review_state = excluded.review_state,
            abstention_reason = excluded.abstention_reason,
            normalized_value = excluded.normalized_value,
            updated_at = excluded.updated_at
        """,
        (
            doc_id,
            field.field_name.value,
            field.raw_value,
            field.confidence,
            field.evidence.page_num,
            _json_or_none(field.evidence.bbox),
            field.evidence.verbatim_span,
            trace_id,
            int(field.needs_review),
            field.review_state.value,
            field.abstention_reason,
            _scalar_to_db(field.value_for_dashboard),
        ),
    )


def _upsert_compliance_record(conn: sqlite3.Connection, record: SDFExtractionRecord) -> None:
    dashboard_values = record.dashboard_values
    evidence_field = _preferred_document_evidence(record)
    source_bbox = _json_or_none(evidence_field.evidence.bbox) if evidence_field else None

    conn.execute(
        """
        INSERT INTO compliance_records (
            doc_id, doc_type, vendor_name, manufacturing_date, effective_date,
            revision_date, expiry_date, aggregate_confidence, review_state,
            needs_review, trace_id, run_id, extracted_at, risk_level, risk_reason,
            compliance_status, age_days, source_page, source_bbox, source_verbatim_span,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(doc_id) DO UPDATE SET
            doc_type = excluded.doc_type,
            vendor_name = excluded.vendor_name,
            manufacturing_date = excluded.manufacturing_date,
            effective_date = excluded.effective_date,
            revision_date = excluded.revision_date,
            expiry_date = excluded.expiry_date,
            aggregate_confidence = excluded.aggregate_confidence,
            review_state = excluded.review_state,
            needs_review = excluded.needs_review,
            trace_id = excluded.trace_id,
            run_id = excluded.run_id,
            extracted_at = excluded.extracted_at,
            risk_level = excluded.risk_level,
            risk_reason = excluded.risk_reason,
            compliance_status = excluded.compliance_status,
            age_days = excluded.age_days,
            source_page = excluded.source_page,
            source_bbox = excluded.source_bbox,
            source_verbatim_span = excluded.source_verbatim_span,
            updated_at = excluded.updated_at
        """,
        (
            record.doc_id,
            _scalar_to_db(dashboard_values[SDFFieldName.DOC_TYPE.value]),
            _scalar_to_db(dashboard_values[SDFFieldName.VENDOR_NAME.value]),
            _scalar_to_db(dashboard_values[SDFFieldName.MANUFACTURING_DATE.value]),
            _scalar_to_db(dashboard_values[SDFFieldName.EFFECTIVE_DATE.value]),
            _scalar_to_db(dashboard_values[SDFFieldName.REVISION_DATE.value]),
            _scalar_to_db(dashboard_values[SDFFieldName.EXPIRY_DATE.value]),
            record.aggregate_confidence,
            record.dashboard_review_state,
            int(record.dashboard_needs_review),
            record.trace_id,
            record.run_id,
            record.extracted_at.isoformat(),
            record.risk_level,
            record.risk_reason,
            record.compliance_status,
            record.age_days,
            evidence_field.evidence.page_num if evidence_field else None,
            source_bbox,
            evidence_field.evidence.verbatim_span if evidence_field else None,
        ),
    )


def _field_from_row(row: sqlite3.Row) -> ExtractedField:
    field_name = SDFFieldName(row["field_name"])
    review_state = ReviewState(row["review_state"])
    return ExtractedField(
        field_name=field_name,
        raw_value=row["field_value"],
        normalized_value=row["normalized_value"],
        confidence=row["confidence"],
        evidence=SourceEvidence(
            page_num=row["source_page"],
            bbox=json.loads(row["source_bbox"]) if row["source_bbox"] is not None else None,
            verbatim_span=row["verbatim_span"],
        ),
        review_state=review_state,
        abstention_reason=row["abstention_reason"],
    )


def _preferred_document_evidence(record: SDFExtractionRecord) -> ExtractedField | None:
    expiry = record.fields[SDFFieldName.EXPIRY_DATE]
    if expiry.review_state != ReviewState.ABSTAINED:
        return expiry
    return next((field for field in record.fields.values() if field.review_state != ReviewState.ABSTAINED), None)


def _json_or_none(value: dict[str, Any] | list[Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _scalar_to_db(value: str | int | float | bool | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _parse_datetime(value: str | None) -> datetime:
    if value is None:
        raise ValueError("extracted_at is required for persisted compliance records")
    return datetime.fromisoformat(value)
