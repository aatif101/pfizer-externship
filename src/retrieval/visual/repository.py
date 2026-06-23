"""Repository contract for persisted visual-index-run state.

Mirrors ``src.retrieval.repository.save_index_run`` (INSERT ... ON CONFLICT
idempotency) and ``src.eval.repository.get_latest_retrieval_index_run_id``, but
targets the ``visual_index_runs`` table (which adds ``model_version`` /
``collection_name``). All data-bearing SQL uses parameterized placeholders. Rows
carry counts / run_id / model_version / collection_name / hashes ONLY — never
image bytes or page text (RESEARCH Pitfall 7, T-05-07).
"""
from __future__ import annotations

from src.db.schema import _connect
from src.retrieval.visual.models import VisualIndexRun


def save_visual_index_run(db_path: str, run: VisualIndexRun) -> None:
    """Insert or update one ``visual_index_runs`` metadata row.

    ``ON CONFLICT(run_id) DO UPDATE`` makes re-saving the same run idempotent
    (one row), mirroring ``repository.save_index_run``. ``built_at`` COALESCEs to
    the current UTC timestamp when the run carries ``None``.
    """
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO visual_index_runs (
                run_id, status, built_at, source_document_count, source_page_count,
                indexed_page_count, model_version, collection_name, content_hash,
                previous_content_hash, is_stale, stale_reason, error_reason
            ) VALUES (?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status = excluded.status,
                built_at = excluded.built_at,
                source_document_count = excluded.source_document_count,
                source_page_count = excluded.source_page_count,
                indexed_page_count = excluded.indexed_page_count,
                model_version = excluded.model_version,
                collection_name = excluded.collection_name,
                content_hash = excluded.content_hash,
                previous_content_hash = excluded.previous_content_hash,
                is_stale = excluded.is_stale,
                stale_reason = excluded.stale_reason,
                error_reason = excluded.error_reason
            """,
            (
                run.run_id,
                run.status,
                run.built_at,
                run.source_document_count,
                run.source_page_count,
                run.indexed_page_count,
                run.model_version,
                run.collection_name,
                run.content_hash,
                run.previous_content_hash,
                int(run.is_stale),
                run.stale_reason,
                run.error_reason,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_latest_visual_index_run_id(db_path: str) -> str | None:
    """Return the newest ``visual_index_runs.run_id``, or ``None`` when empty.

    Mirrors ``src.eval.repository.get_latest_retrieval_index_run_id`` (ORDER BY
    built_at DESC, run_id DESC LIMIT 1).
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT run_id
            FROM visual_index_runs
            ORDER BY built_at DESC, run_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row is not None else None
