"""Evaluation repository helpers.

Goals:
- Streamlit rerun-safe (INSERT OR IGNORE / upsert semantics)
- Offline-safe: no provider/LLM imports
- Only parameterized SQL

This module builds on the canonical evaluation schema introduced in
`src/db/schema.py` (eval_runs + eval_metrics + gold_* tables).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from src.db.schema import _connect


@dataclass(frozen=True)
class EvalRunRow:
    run_id: str
    eval_type: str
    status: str
    created_at: str | None
    completed_at: str | None
    pipeline_label: str | None
    params_json: str | None
    error_reason: str | None


@dataclass(frozen=True)
class EvalMetricRow:
    run_id: str
    metric_name: str
    metric_value: float | None
    scope_type: str | None
    scope_id: str | None
    created_at: str | None


def create_eval_run(
    db_path: str,
    run_id: str,
    eval_type: str,
    pipeline_label: str | None,
    params: dict[str, Any] | None,
) -> None:
    """Create an eval run row if it doesn't exist.

    Uses INSERT OR IGNORE to avoid Streamlit rerun duplication.
    """

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO eval_runs (
                run_id, eval_type, status, pipeline_label, params_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, eval_type, "running", pipeline_label, json.dumps(params or {}, sort_keys=True)),
        )
        conn.commit()
    finally:
        conn.close()


def mark_eval_run_complete(db_path: str, run_id: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE eval_runs
            SET status = ?, completed_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                error_reason = NULL
            WHERE run_id = ?
            """,
            ("complete", run_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_eval_run_error(db_path: str, run_id: str, error_reason: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE eval_runs
            SET status = ?, completed_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                error_reason = ?
            WHERE run_id = ?
            """,
            ("error", error_reason, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_eval_metric_uniqueness(conn: sqlite3.Connection) -> None:
    """Ensure a unique index exists for metric upserts.

    The base schema shipped in T01 does not include a UNIQUE constraint on
    (run_id, metric_name, scope_type, scope_id). To keep migrations simple and
    allow deterministic upserts, we create a unique index if missing.

    This is idempotent and safe to call on every upsert.
    """

    # SQLite UNIQUE indexes treat NULL values as distinct, so two rows with
    # scope_type/scope_id NULL would still duplicate. Use COALESCE() to map
    # NULL -> '' so the uniqueness key behaves as expected for "global" metrics.
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_metrics_dedupe
        ON eval_metrics(run_id, metric_name, COALESCE(scope_type, ''), COALESCE(scope_id, ''))
        """
    )


def upsert_eval_metric(
    db_path: str,
    run_id: str,
    metric_name: str,
    metric_value: float | None,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> None:
    """Insert or update a metric row keyed by (run_id, metric_name, scope_*).

    Designed to be safe under Streamlit reruns: repeated calls with the same
    key overwrite metric_value rather than duplicating rows.
    """

    conn = _connect(db_path)
    try:
        _ensure_eval_metric_uniqueness(conn)
        conn.execute(
            """
            INSERT INTO eval_metrics (run_id, metric_name, metric_value, scope_type, scope_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id, metric_name, COALESCE(scope_type, ''), COALESCE(scope_id, ''))
            DO UPDATE SET metric_value = excluded.metric_value
            """,
            (run_id, metric_name, metric_value, scope_type, scope_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_eval_runs(db_path: str, limit: int = 50) -> list[EvalRunRow]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT run_id, eval_type, status, created_at, completed_at, pipeline_label, params_json, error_reason
            FROM eval_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return [
        EvalRunRow(
            run_id=row[0],
            eval_type=row[1],
            status=row[2],
            created_at=row[3],
            completed_at=row[4],
            pipeline_label=row[5],
            params_json=row[6],
            error_reason=row[7],
        )
        for row in rows
    ]


def list_eval_metrics(db_path: str, run_id: str) -> list[EvalMetricRow]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT run_id, metric_name, metric_value, scope_type, scope_id, created_at
            FROM eval_metrics
            WHERE run_id = ?
            ORDER BY metric_name ASC, scope_type ASC, scope_id ASC
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    return [
        EvalMetricRow(
            run_id=row[0],
            metric_name=row[1],
            metric_value=row[2],
            scope_type=row[3],
            scope_id=row[4],
            created_at=row[5],
        )
        for row in rows
    ]


def list_gold_extraction_labels(db_path: str) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT doc_id, field_name, expected_value, normalized_value, source_page, created_at
            FROM gold_extraction_labels
            ORDER BY doc_id ASC, field_name ASC
            """
        ).fetchall()
    finally:
        conn.close()

    columns = ["doc_id", "field_name", "expected_value", "normalized_value", "source_page", "created_at"]
    return [dict(zip(columns, row)) for row in rows]


def list_gold_retrieval_queries(db_path: str) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT query_id, query_text, notes, created_at
            FROM gold_retrieval_queries
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    columns = ["query_id", "query_text", "notes", "created_at"]
    return [dict(zip(columns, row)) for row in rows]


def list_gold_retrieval_targets(db_path: str, query_id: str) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT query_id, doc_id, page_num, created_at
            FROM gold_retrieval_targets
            WHERE query_id = ?
            ORDER BY doc_id ASC, page_num ASC
            """,
            (query_id,),
        ).fetchall()
    finally:
        conn.close()

    columns = ["query_id", "doc_id", "page_num", "created_at"]
    return [dict(zip(columns, row)) for row in rows]
