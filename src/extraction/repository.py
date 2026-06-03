"""SQLite persistence helpers for validated SDF extraction records.

Repository boundary: callers pass already-validated Pydantic models. All SQL uses
parameterized placeholders; source evidence text is persisted only in explicit
evidence columns and is never logged here.
"""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ExtractionRunSummary:
    """Bounded, dashboard-safe metadata for one extraction run."""

    run_id: str
    status: str
    document_count: int
    field_count: int
    trace_id: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str | None
    updated_at: str | None


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
    """Persist latest rows and, when run-scoped, additive history rows idempotently."""

    conn = _connect(db_path)
    try:
        if record.run_id is not None:
            _upsert_extraction_run(conn, record)

        for field_name in _FIELD_ORDER:
            field = record.fields[field_name]
            _upsert_extraction_field(conn, record.doc_id, field, record.trace_id)
            if record.run_id is not None:
                _upsert_extraction_history_field(conn, record, field)

        _upsert_compliance_record(conn, record)
        if record.run_id is not None:
            _upsert_compliance_record_history(conn, record)
            _refresh_extraction_run_counts(conn, record.run_id, record.extracted_at.isoformat())

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_extraction_record(db_path: str, doc_id: str) -> SDFExtractionRecord | None:
    """Return the latest validated extraction record reconstructed from SQLite, if present."""

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return _get_extraction_record_with_queries(
            conn,
            doc_id=doc_id,
            compliance_sql="""
                SELECT trace_id, run_id, extracted_at, risk_level, risk_reason, compliance_status, age_days
                FROM compliance_records
                WHERE doc_id = ?
            """,
            compliance_params=(doc_id,),
            fields_sql="""
                SELECT field_name, field_value, confidence, source_page, source_bbox,
                       verbatim_span, review_state, abstention_reason, normalized_value
                FROM extractions
                WHERE doc_id = ?
                ORDER BY field_name
            """,
            fields_params=(doc_id,),
        )
    finally:
        conn.close()


def get_extraction_record_for_run(db_path: str, run_id: str, doc_id: str) -> SDFExtractionRecord | None:
    """Return a validated extraction record for a specific historical run, if complete."""

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return _get_extraction_record_with_queries(
            conn,
            doc_id=doc_id,
            compliance_sql="""
                SELECT trace_id, run_id, extracted_at, risk_level, risk_reason, compliance_status, age_days
                FROM compliance_record_history
                WHERE run_id = ? AND doc_id = ?
            """,
            compliance_params=(run_id, doc_id),
            fields_sql="""
                SELECT field_name, field_value, confidence, source_page, source_bbox,
                       verbatim_span, review_state, abstention_reason, normalized_value
                FROM extraction_history
                WHERE run_id = ? AND doc_id = ?
                ORDER BY field_name
            """,
            fields_params=(run_id, doc_id),
        )
    finally:
        conn.close()


def list_compliance_records(db_path: str) -> list[dict[str, Any]]:
    """List dashboard-ready latest compliance rows in deterministic S04-friendly order."""

    return _list_compliance_records_from_table(db_path, table_name="compliance_records")


def list_compliance_records_for_run(db_path: str, run_id: str) -> list[dict[str, Any]]:
    """List dashboard-ready compliance rows for one extraction run."""

    return _list_compliance_records_from_table(db_path, table_name="compliance_record_history", run_id=run_id)


def list_extraction_run_summaries(db_path: str) -> list[ExtractionRunSummary]:
    """List bounded extraction run metadata without raw document/provider payloads."""

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT run_id, status, document_count, field_count, trace_id,
                   started_at, completed_at, created_at, updated_at
            FROM extraction_runs
            ORDER BY started_at DESC, run_id ASC
            """
        ).fetchall()
        return [
            ExtractionRunSummary(
                run_id=row["run_id"],
                status=row["status"],
                document_count=row["document_count"],
                field_count=row["field_count"],
                trace_id=row["trace_id"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()


def _get_extraction_record_with_queries(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    compliance_sql: str,
    compliance_params: tuple[Any, ...],
    fields_sql: str,
    fields_params: tuple[Any, ...],
) -> SDFExtractionRecord | None:
    document = conn.execute(
        "SELECT doc_id, filename FROM documents WHERE doc_id = ?",
        (doc_id,),
    ).fetchone()
    if document is None:
        return None

    compliance = conn.execute(compliance_sql, compliance_params).fetchone()
    if compliance is None:
        return None

    rows = conn.execute(fields_sql, fields_params).fetchall()
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


def _list_compliance_records_from_table(db_path: str, *, table_name: str, run_id: str | None = None) -> list[dict[str, Any]]:
    if table_name not in {"compliance_records", "compliance_record_history"}:
        raise ValueError(f"unsupported compliance table: {table_name}")

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where_clause = "WHERE run_id = ?" if run_id is not None else ""
        params: tuple[Any, ...] = (run_id,) if run_id is not None else ()
        rows = conn.execute(
            f"""
            SELECT {", ".join(_COMPLIANCE_COLUMNS)}
            FROM {table_name}
            {where_clause}
            ORDER BY expiry_date IS NULL, expiry_date ASC, vendor_name ASC, doc_id ASC
            """,
            params,
        ).fetchall()
        return [{column: row[column] for column in _COMPLIANCE_COLUMNS} for row in rows]
    finally:
        conn.close()


def _upsert_extraction_run(conn: sqlite3.Connection, record: SDFExtractionRecord) -> None:
    conn.execute(
        """
        INSERT INTO extraction_runs (
            run_id, status, document_count, field_count, trace_id,
            started_at, completed_at, updated_at
        ) VALUES (?, ?, 0, 0, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(run_id) DO UPDATE SET
            trace_id = excluded.trace_id,
            updated_at = excluded.updated_at
        """,
        (
            record.run_id,
            "completed",
            record.trace_id,
            record.extracted_at.isoformat(),
            record.extracted_at.isoformat(),
        ),
    )


def _refresh_extraction_run_counts(conn: sqlite3.Connection, run_id: str, completed_at: str) -> None:
    conn.execute(
        """
        UPDATE extraction_runs
        SET document_count = (
                SELECT COUNT(DISTINCT doc_id)
                FROM extraction_history
                WHERE run_id = ?
            ),
            field_count = (
                SELECT COUNT(*)
                FROM extraction_history
                WHERE run_id = ?
            ),
            status = 'completed',
            completed_at = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE run_id = ?
        """,
        (run_id, run_id, completed_at, run_id),
    )


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
        _field_params(doc_id=doc_id, field=field, trace_id=trace_id),
    )


def _upsert_extraction_history_field(conn: sqlite3.Connection, record: SDFExtractionRecord, field: ExtractedField) -> None:
    conn.execute(
        """
        INSERT INTO extraction_history (
            run_id, doc_id, field_name, field_value, confidence, source_page, source_bbox,
            verbatim_span, trace_id, needs_review, review_state, abstention_reason,
            normalized_value, extracted_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(run_id, doc_id, field_name) DO UPDATE SET
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
            extracted_at = excluded.extracted_at,
            updated_at = excluded.updated_at
        """,
        (
            record.run_id,
            *_field_params(doc_id=record.doc_id, field=field, trace_id=record.trace_id),
            record.extracted_at.isoformat(),
        ),
    )


def _field_params(*, doc_id: str, field: ExtractedField, trace_id: str | None) -> tuple[Any, ...]:
    return (
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
    )


def _upsert_compliance_record(conn: sqlite3.Connection, record: SDFExtractionRecord) -> None:
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
        _compliance_params(record),
    )


def _upsert_compliance_record_history(conn: sqlite3.Connection, record: SDFExtractionRecord) -> None:
    conn.execute(
        """
        INSERT INTO compliance_record_history (
            run_id, doc_id, doc_type, vendor_name, manufacturing_date, effective_date,
            revision_date, expiry_date, aggregate_confidence, review_state,
            needs_review, trace_id, extracted_at, risk_level, risk_reason,
            compliance_status, age_days, source_page, source_bbox, source_verbatim_span,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(run_id, doc_id) DO UPDATE SET
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
        _compliance_history_params(record),
    )


def _compliance_params(record: SDFExtractionRecord) -> tuple[Any, ...]:
    common = _compliance_common_params(record)
    return (*common[:11], record.run_id, *common[11:])


def _compliance_history_params(record: SDFExtractionRecord) -> tuple[Any, ...]:
    return (record.run_id, *_compliance_common_params(record))


def _compliance_common_params(record: SDFExtractionRecord) -> tuple[Any, ...]:
    dashboard_values = record.dashboard_values
    evidence_field = _preferred_document_evidence(record)
    source_bbox = _json_or_none(evidence_field.evidence.bbox) if evidence_field else None

    return (
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
        record.extracted_at.isoformat(),
        record.risk_level,
        record.risk_reason,
        record.compliance_status,
        record.age_days,
        evidence_field.evidence.page_num if evidence_field else None,
        source_bbox,
        evidence_field.evidence.verbatim_span if evidence_field else None,
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
