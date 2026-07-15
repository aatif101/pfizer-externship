"""SQLite persistence helpers for validated SDF extraction records.

Repository boundary: callers pass already-validated Pydantic models. All SQL uses
parameterized placeholders; source evidence text is persisted only in explicit
evidence columns and is never logged here.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from src.db.schema import _connect
from src.extraction.models import (
    ExtractedField,
    ExtractionDocumentStatus,
    ExtractionRunDocument,
    ExtractionRunStatus,
    ExtractionRunSummary,
    ReviewState,
    SDFExtractionRecord,
    SDFFieldName,
    SourceEvidence,
)


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
    "source_evidence_type",
)

_RUN_SUMMARY_COLUMNS: tuple[str, ...] = (
    "run_id",
    "status",
    "document_count",
    "field_count",
    "expected_document_count",
    "attempted_document_count",
    "succeeded_document_count",
    "failed_document_count",
    "provider",
    "requested_model",
    "resolved_model",
    "corpus_version",
    "manifest_hash",
    "trace_id",
    "started_at",
    "completed_at",
    "created_at",
    "updated_at",
)
_RUN_DOCUMENT_COLUMNS: tuple[str, ...] = (
    "run_id",
    "doc_id",
    "status",
    "attempt_count",
    "trace_id",
    "error_reason",
    "started_at",
    "completed_at",
    "updated_at",
)
_MAX_IDENTITY_LENGTH = 255
_MAX_REASON_LENGTH = 96
_MAX_TRACE_ID_LENGTH = 255
_MAX_ATTEMPTS = 1_000_000
_SAFE_REASON_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ExtractionRunError(RuntimeError):
    """Base class for safe, reason-coded extraction lifecycle failures."""

    reason_code = "extraction_run_error"

    def __init__(self, *, run_id: str | None = None, doc_id: str | None = None) -> None:
        super().__init__(self.reason_code)
        self.run_id = run_id
        self.doc_id = doc_id


class ExtractionRunConflictError(ExtractionRunError):
    """Raised before mutation when a run ID is reused with another identity."""

    reason_code = "extraction_run_identity_mismatch"


class ExtractionRunStateError(ExtractionRunError):
    """Raised for invalid or impossible lifecycle transitions."""

    def __init__(
        self,
        reason_code: str,
        *,
        run_id: str | None = None,
        doc_id: str | None = None,
    ) -> None:
        self.reason_code = reason_code
        super().__init__(run_id=run_id, doc_id=doc_id)


def _compute_extraction_manifest_hash(corpus_version: str, doc_ids: tuple[str, ...]) -> str:
    """Return the content-free identity hash for a sorted unique manifest."""

    canonical_doc_ids = tuple(sorted(set(doc_ids)))
    manifest = f"{corpus_version}\x1f" + "\x1e".join(canonical_doc_ids)
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def begin_or_resume_extraction_run(
    db_path: str,
    *,
    run_id: str,
    doc_ids: tuple[str, ...],
    provider: str,
    requested_model: str,
    corpus_version: str,
) -> ExtractionRunSummary:
    """Create one immutable manifest-bound run or validate an exact resume."""

    safe_run_id = _validate_identity(run_id, field="run_id")
    safe_provider = _validate_identity(provider, field="provider")
    safe_model = _validate_identity(requested_model, field="requested_model")
    safe_corpus = _validate_identity(corpus_version, field="corpus_version")
    canonical_doc_ids = tuple(sorted({_validate_identity(doc_id, field="doc_id") for doc_id in doc_ids}))
    if not canonical_doc_ids:
        raise ExtractionRunStateError("extraction_manifest_empty", run_id=safe_run_id)
    manifest_hash = _compute_extraction_manifest_hash(safe_corpus, canonical_doc_ids)

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ", ".join("?" for _ in canonical_doc_ids)
        existing_documents = {
            row[0]
            for row in conn.execute(
                f"SELECT doc_id FROM documents WHERE doc_id IN ({placeholders})",
                canonical_doc_ids,
            ).fetchall()
        }
        missing = tuple(doc_id for doc_id in canonical_doc_ids if doc_id not in existing_documents)
        if missing:
            raise ExtractionRunStateError("document_not_found", run_id=safe_run_id, doc_id=missing[0])

        parent = conn.execute(
            f"SELECT {', '.join(_RUN_SUMMARY_COLUMNS)} FROM extraction_runs WHERE run_id = ?",
            (safe_run_id,),
        ).fetchone()
        if parent is None:
            conn.execute(
                """
                INSERT INTO extraction_runs (
                    run_id, status, document_count, field_count,
                    expected_document_count, attempted_document_count,
                    succeeded_document_count, failed_document_count,
                    provider, requested_model, corpus_version, manifest_hash,
                    completed_at, updated_at
                ) VALUES (?, 'running', 0, 0, ?, 0, 0, 0, ?, ?, ?, ?, NULL,
                          strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                """,
                (
                    safe_run_id,
                    len(canonical_doc_ids),
                    safe_provider,
                    safe_model,
                    safe_corpus,
                    manifest_hash,
                ),
            )
            conn.executemany(
                """
                INSERT INTO extraction_run_documents (run_id, doc_id, status, attempt_count)
                VALUES (?, ?, 'pending', 0)
                """,
                ((safe_run_id, doc_id) for doc_id in canonical_doc_ids),
            )
        else:
            child_ids = tuple(
                row[0]
                for row in conn.execute(
                    """
                    SELECT doc_id FROM extraction_run_documents
                    WHERE run_id = ? ORDER BY doc_id ASC
                    """,
                    (safe_run_id,),
                ).fetchall()
            )
            identity_matches = (
                parent["manifest_hash"] == manifest_hash
                and parent["provider"] == safe_provider
                and parent["requested_model"] == safe_model
                and parent["corpus_version"] == safe_corpus
                and parent["expected_document_count"] == len(canonical_doc_ids)
                and child_ids == canonical_doc_ids
            )
            if not identity_matches:
                raise ExtractionRunConflictError(run_id=safe_run_id)

        conn.commit()
        return _load_extraction_run_summary(conn, safe_run_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_resume_candidates(db_path: str, run_id: str) -> tuple[ExtractionRunDocument, ...]:
    """Return pending, interrupted-running, and failed children in stable order."""

    safe_run_id = _validate_identity(run_id, field="run_id")
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            SELECT {', '.join(_RUN_DOCUMENT_COLUMNS)}
            FROM extraction_run_documents
            WHERE run_id = ? AND status IN ('pending', 'running', 'failed')
            ORDER BY doc_id ASC
            """,
            (safe_run_id,),
        ).fetchall()
        return tuple(_run_document_from_row(row) for row in rows)
    finally:
        conn.close()


def mark_run_document_running(db_path: str, run_id: str, doc_id: str) -> ExtractionRunDocument:
    """Claim one bounded attempt and make a candidate explicitly running."""

    safe_run_id = _validate_identity(run_id, field="run_id")
    safe_doc_id = _validate_identity(doc_id, field="doc_id")
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        current = conn.execute(
            "SELECT status, attempt_count FROM extraction_run_documents WHERE run_id = ? AND doc_id = ?",
            (safe_run_id, safe_doc_id),
        ).fetchone()
        if current is None:
            raise ExtractionRunStateError("extraction_run_document_not_found", run_id=safe_run_id, doc_id=safe_doc_id)
        if current["status"] == ExtractionDocumentStatus.COMPLETED.value:
            raise ExtractionRunStateError("extraction_run_document_completed", run_id=safe_run_id, doc_id=safe_doc_id)
        if int(current["attempt_count"]) >= _MAX_ATTEMPTS:
            raise ExtractionRunStateError("extraction_attempt_limit_reached", run_id=safe_run_id, doc_id=safe_doc_id)
        conn.execute(
            """
            UPDATE extraction_run_documents
            SET status = 'running', attempt_count = attempt_count + 1,
                trace_id = NULL, error_reason = NULL,
                started_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                completed_at = NULL,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE run_id = ? AND doc_id = ?
            """,
            (safe_run_id, safe_doc_id),
        )
        conn.execute(
            """
            UPDATE extraction_runs
            SET status = 'running', completed_at = NULL,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE run_id = ?
            """,
            (safe_run_id,),
        )
        row = conn.execute(
            f"SELECT {', '.join(_RUN_DOCUMENT_COLUMNS)} FROM extraction_run_documents WHERE run_id = ? AND doc_id = ?",
            (safe_run_id, safe_doc_id),
        ).fetchone()
        conn.commit()
        return _run_document_from_row(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_run_document_completed(
    db_path: str,
    run_id: str,
    doc_id: str,
    *,
    trace_id: str | None = None,
) -> None:
    """Persist one successful child outcome without finalizing its parent."""

    _set_run_document_terminal(
        db_path,
        run_id,
        doc_id,
        status=ExtractionDocumentStatus.COMPLETED,
        trace_id=_validate_optional_trace_id(trace_id),
        reason_code=None,
    )


def mark_run_document_failed(
    db_path: str,
    run_id: str,
    doc_id: str,
    *,
    reason_code: str,
) -> None:
    """Persist one failed child outcome using a stable bounded reason code."""

    safe_reason = _validate_reason_code(reason_code)
    _set_run_document_terminal(
        db_path,
        run_id,
        doc_id,
        status=ExtractionDocumentStatus.FAILED,
        trace_id=None,
        reason_code=safe_reason,
    )


def finalize_extraction_run(db_path: str, run_id: str) -> ExtractionRunSummary:
    """Derive parent counts and terminal status exclusively from child rows."""

    safe_run_id = _validate_identity(run_id, field="run_id")
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _finalize_extraction_run_in_connection(conn, safe_run_id)
        summary = _load_extraction_run_summary(conn, safe_run_id)
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_complete_extraction_run(db_path: str, run_id: str) -> ExtractionRunSummary | None:
    """Return a run only when its strict all-success invariant is durable."""

    safe_run_id = _validate_identity(run_id, field="run_id")
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"""
            SELECT {', '.join(_RUN_SUMMARY_COLUMNS)} FROM extraction_runs
            WHERE run_id = ? AND status = 'completed'
              AND expected_document_count > 0
              AND succeeded_document_count = expected_document_count
              AND failed_document_count = 0
            """,
            (safe_run_id,),
        ).fetchone()
        return _run_summary_from_row(row) if row is not None else None
    finally:
        conn.close()


def record_extraction_run_resolved_model(db_path: str, run_id: str, resolved_model: str | None) -> None:
    """Persist one immutable provider-resolved model identity for audit evidence.

    A response that omits its resolved model is a no-op. Once a concrete model is
    recorded, retries may repeat that same identity but may never silently replace
    it with a different one.
    """

    safe_run_id = _validate_identity(run_id, field="run_id")
    safe_model = None if resolved_model is None else _validate_identity(resolved_model, field="resolved_model")
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT resolved_model FROM extraction_runs WHERE run_id = ?",
            (safe_run_id,),
        ).fetchone()
        if row is None:
            raise ExtractionRunStateError("extraction_run_not_found", run_id=safe_run_id)
        current_model = row[0]
        if safe_model is None or current_model == safe_model:
            conn.commit()
            return
        if current_model is not None:
            raise ExtractionRunStateError("extraction_run_model_mismatch", run_id=safe_run_id)
        conn.execute(
            """
            UPDATE extraction_runs SET resolved_model = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE run_id = ?
            """,
            (safe_model, safe_run_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
        implicit_lifecycle = False
        if record.run_id is not None:
            implicit_lifecycle = _prepare_extraction_run_for_record(conn, record)

        for field_name in _FIELD_ORDER:
            field = record.fields[field_name]
            _upsert_extraction_field(conn, record.doc_id, field, record.trace_id)
            if record.run_id is not None:
                _upsert_extraction_history_field(conn, record, field)

        _upsert_compliance_record(conn, record)
        if record.run_id is not None:
            _upsert_compliance_record_history(conn, record)
            if implicit_lifecycle:
                _complete_implicit_run_document(conn, record)
                _finalize_extraction_run_in_connection(conn, record.run_id)

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
                       verbatim_span, review_state, abstention_reason, normalized_value,
                       evidence_type
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
                       verbatim_span, review_state, abstention_reason, normalized_value,
                       evidence_type
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
            f"""
            SELECT {', '.join(_RUN_SUMMARY_COLUMNS)}
            FROM extraction_runs
            ORDER BY started_at DESC, run_id ASC
            """
        ).fetchall()
        return [_run_summary_from_row(row) for row in rows]
    finally:
        conn.close()


def _set_run_document_terminal(
    db_path: str,
    run_id: str,
    doc_id: str,
    *,
    status: ExtractionDocumentStatus,
    trace_id: str | None,
    reason_code: str | None,
) -> None:
    safe_run_id = _validate_identity(run_id, field="run_id")
    safe_doc_id = _validate_identity(doc_id, field="doc_id")
    conn = _connect(db_path)
    try:
        current = conn.execute(
            "SELECT status FROM extraction_run_documents WHERE run_id = ? AND doc_id = ?",
            (safe_run_id, safe_doc_id),
        ).fetchone()
        if current is None:
            raise ExtractionRunStateError("extraction_run_document_not_found", run_id=safe_run_id, doc_id=safe_doc_id)
        if current[0] == ExtractionDocumentStatus.COMPLETED.value:
            if status is ExtractionDocumentStatus.COMPLETED:
                conn.commit()
                return
            raise ExtractionRunStateError("extraction_run_document_completed", run_id=safe_run_id, doc_id=safe_doc_id)
        conn.execute(
            """
            UPDATE extraction_run_documents
            SET status = ?, trace_id = ?, error_reason = ?,
                completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE run_id = ? AND doc_id = ?
            """,
            (status.value, trace_id, reason_code, safe_run_id, safe_doc_id),
        )
        if trace_id is not None:
            conn.execute(
                """
                UPDATE extraction_runs SET trace_id = COALESCE(trace_id, ?),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE run_id = ?
                """,
                (trace_id, safe_run_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _finalize_extraction_run_in_connection(conn: sqlite3.Connection, run_id: str) -> None:
    parent = conn.execute(
        "SELECT expected_document_count FROM extraction_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if parent is None:
        raise ExtractionRunStateError("extraction_run_not_found", run_id=run_id)
    expected = int(parent[0])
    child_counts = conn.execute(
        """
        SELECT COUNT(*) AS child_count,
               SUM(CASE WHEN attempt_count > 0 THEN 1 ELSE 0 END) AS attempted,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS succeeded,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
               SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running
        FROM extraction_run_documents
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    child_count, attempted, succeeded, failed, pending, running = (
        int(value or 0) for value in child_counts
    )
    all_children_accounted = child_count == expected and expected > 0
    if all_children_accounted and pending == 0 and running == 0 and succeeded == expected and failed == 0:
        status = ExtractionRunStatus.COMPLETED
    elif all_children_accounted and pending == 0 and running == 0 and failed == expected and succeeded == 0:
        status = ExtractionRunStatus.FAILED
    elif all_children_accounted and pending == 0 and running == 0 and succeeded > 0 and failed > 0:
        status = ExtractionRunStatus.PARTIAL
    else:
        status = ExtractionRunStatus.RUNNING

    terminal = status is not ExtractionRunStatus.RUNNING
    conn.execute(
        """
        UPDATE extraction_runs
        SET status = ?,
            document_count = (
                SELECT COUNT(DISTINCT doc_id) FROM extraction_history WHERE run_id = ?
            ),
            field_count = (
                SELECT COUNT(*) FROM extraction_history WHERE run_id = ?
            ),
            attempted_document_count = ?,
            succeeded_document_count = ?,
            failed_document_count = ?,
            completed_at = CASE
                WHEN ? THEN COALESCE(completed_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                ELSE NULL
            END,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE run_id = ?
        """,
        (
            status.value,
            run_id,
            run_id,
            attempted,
            succeeded,
            failed,
            int(terminal),
            run_id,
        ),
    )


def _load_extraction_run_summary(conn: sqlite3.Connection, run_id: str) -> ExtractionRunSummary:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f"SELECT {', '.join(_RUN_SUMMARY_COLUMNS)} FROM extraction_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ExtractionRunStateError("extraction_run_not_found", run_id=run_id)
    return _run_summary_from_row(row)


def _run_summary_from_row(row: sqlite3.Row) -> ExtractionRunSummary:
    return ExtractionRunSummary(
        run_id=row["run_id"],
        status=ExtractionRunStatus(row["status"]),
        document_count=int(row["document_count"]),
        field_count=int(row["field_count"]),
        expected_document_count=int(row["expected_document_count"]),
        attempted_document_count=int(row["attempted_document_count"]),
        succeeded_document_count=int(row["succeeded_document_count"]),
        failed_document_count=int(row["failed_document_count"]),
        provider=row["provider"],
        requested_model=row["requested_model"],
        resolved_model=row["resolved_model"],
        corpus_version=row["corpus_version"],
        manifest_hash=row["manifest_hash"],
        trace_id=row["trace_id"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _run_document_from_row(row: sqlite3.Row) -> ExtractionRunDocument:
    return ExtractionRunDocument(
        run_id=row["run_id"],
        doc_id=row["doc_id"],
        status=ExtractionDocumentStatus(row["status"]),
        attempt_count=int(row["attempt_count"]),
        trace_id=row["trace_id"],
        error_reason=row["error_reason"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
    )


def _validate_identity(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise ExtractionRunStateError(f"invalid_{field}")
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_IDENTITY_LENGTH:
        raise ExtractionRunStateError(f"invalid_{field}")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ExtractionRunStateError(f"invalid_{field}")
    return normalized


def _validate_reason_code(reason_code: str) -> str:
    if (
        not isinstance(reason_code, str)
        or len(reason_code) > _MAX_REASON_LENGTH
        or _SAFE_REASON_RE.fullmatch(reason_code) is None
    ):
        raise ExtractionRunStateError("invalid_extraction_reason_code")
    return reason_code


def _validate_optional_trace_id(trace_id: str | None) -> str | None:
    if trace_id is None:
        return None
    normalized = trace_id.strip()
    if not normalized or len(normalized) > _MAX_TRACE_ID_LENGTH:
        raise ExtractionRunStateError("invalid_trace_id")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ExtractionRunStateError("invalid_trace_id")
    return normalized


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


def _prepare_extraction_run_for_record(conn: sqlite3.Connection, record: SDFExtractionRecord) -> bool:
    """Prepare legacy direct-call lifecycle and leave managed parents untouched.

    Returns ``True`` only for an implicit (manifest-less) parent. The caller then
    completes that child after every latest/history/compliance write succeeds in
    the same transaction. A managed parent is validated for membership but its
    lifecycle remains solely under the coordinator API.
    """

    assert record.run_id is not None
    run_id = _validate_identity(record.run_id, field="run_id")
    doc_id = _validate_identity(record.doc_id, field="doc_id")
    parent = conn.execute(
        "SELECT manifest_hash FROM extraction_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if parent is not None and parent[0] is not None:
        child = conn.execute(
            "SELECT 1 FROM extraction_run_documents WHERE run_id = ? AND doc_id = ?",
            (run_id, doc_id),
        ).fetchone()
        if child is None:
            raise ExtractionRunConflictError(run_id=run_id)
        return False

    if parent is None:
        conn.execute(
            """
            INSERT INTO extraction_runs (
                run_id, status, document_count, field_count,
                expected_document_count, attempted_document_count,
                succeeded_document_count, failed_document_count,
                trace_id, started_at, completed_at, updated_at
            ) VALUES (?, 'running', 0, 0, 1, 0, 0, 0, ?, ?, NULL,
                      strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            """,
            (run_id, _validate_optional_trace_id(record.trace_id), record.extracted_at.isoformat()),
        )

    conn.execute(
        """
        INSERT INTO extraction_run_documents (
            run_id, doc_id, status, attempt_count, trace_id,
            started_at, completed_at, updated_at
        ) VALUES (?, ?, 'running', 1, NULL, ?, NULL,
                  strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(run_id, doc_id) DO UPDATE SET
            status = 'running',
            attempt_count = CASE
                WHEN extraction_run_documents.attempt_count = 0 THEN 1
                ELSE extraction_run_documents.attempt_count
            END,
            error_reason = NULL,
            completed_at = NULL,
            updated_at = excluded.updated_at
        """,
        (run_id, doc_id, record.extracted_at.isoformat()),
    )
    conn.execute(
        """
        UPDATE extraction_runs
        SET status = 'running',
            expected_document_count = (
                SELECT COUNT(*) FROM extraction_run_documents WHERE run_id = ?
            ),
            trace_id = COALESCE(?, trace_id),
            completed_at = NULL,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE run_id = ?
        """,
        (run_id, _validate_optional_trace_id(record.trace_id), run_id),
    )
    return True


def _complete_implicit_run_document(conn: sqlite3.Connection, record: SDFExtractionRecord) -> None:
    assert record.run_id is not None
    conn.execute(
        """
        UPDATE extraction_run_documents
        SET status = 'completed', trace_id = ?, error_reason = NULL,
            completed_at = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE run_id = ? AND doc_id = ?
        """,
        (
            _validate_optional_trace_id(record.trace_id),
            record.extracted_at.isoformat(),
            record.run_id,
            record.doc_id,
        ),
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
            normalized_value, evidence_type, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
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
            evidence_type = excluded.evidence_type,
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
            normalized_value, evidence_type, extracted_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
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
            evidence_type = excluded.evidence_type,
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
        field.evidence.evidence_type,
    )


def _upsert_compliance_record(conn: sqlite3.Connection, record: SDFExtractionRecord) -> None:
    conn.execute(
        """
        INSERT INTO compliance_records (
            doc_id, doc_type, vendor_name, manufacturing_date, effective_date,
            revision_date, expiry_date, aggregate_confidence, review_state,
            needs_review, trace_id, run_id, extracted_at, risk_level, risk_reason,
            compliance_status, age_days, source_page, source_bbox, source_verbatim_span,
            source_evidence_type, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
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
            source_evidence_type = excluded.source_evidence_type,
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
            source_evidence_type, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
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
            source_evidence_type = excluded.source_evidence_type,
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
        evidence_field.evidence.evidence_type if evidence_field else "text",
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
            evidence_type=row["evidence_type"] if row["evidence_type"] is not None else "text",
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
