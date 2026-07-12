"""Database write orchestration for the ingestion pipeline.

Wraps queries.py functions with Langfuse @observe spans (D-04).
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from src.tracing import observe, safe_update_current_trace
from src.db.queries import (
    _mark_document_ingested,
    _upsert_document,
    _upsert_page,
)
from src.db.schema import _connect

_STORAGE_TRACE_METADATA_KEYS = frozenset(
    {"boundary", "status", "filename", "page_count", "image_count", "error_class"}
)


def _trace_storage(metadata: dict[str, object]) -> None:
    """Best-effort storage trace update with a strict metadata allowlist."""
    safe_update_current_trace(
        tags=["phase1", "storage"],
        metadata=metadata,
        allowed_metadata_keys=_STORAGE_TRACE_METADATA_KEYS,
    )


@observe(name="write_to_db")
def write_document_to_db(
    db_path: str,
    doc_id: str,
    filename: str,
    file_path: str,
    page_count: int,
    docling_json: Optional[str],
    page_texts: dict[int, str],
    png_blobs: list[bytes],
    *,
    content_sha256: str | None = None,
) -> None:
    """Atomically replace one complete document snapshot in SQLite."""
    image_count = len(png_blobs)
    if page_count < 0:
        raise ValueError("page count must be non-negative")
    if image_count != page_count:
        raise ValueError("page image count mismatch")

    _trace_storage(
        {
            "boundary": "storage",
            "status": "started",
            "filename": filename,
            "page_count": page_count,
            "image_count": image_count,
        }
    )

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN")
        _upsert_document(
            conn,
            doc_id,
            filename,
            file_path,
            page_count,
            docling_json,
            content_sha256=content_sha256,
        )

        # OCR is derived from the page image/text snapshot.  Invalidate it in
        # this transaction so rollback restores the previous derived state.
        conn.execute("DELETE FROM page_ocr_texts WHERE doc_id = ?", (doc_id,))
        for page_num in range(page_count):
            _upsert_page(
                conn,
                doc_id,
                page_num,
                page_texts.get(page_num, ""),
                png_blobs[page_num],
            )

        conn.execute("DELETE FROM pages WHERE doc_id = ? AND page_num >= ?", (doc_id, page_count))
        _mark_document_ingested(conn, doc_id)
        conn.commit()
        _trace_storage(
            {
                "boundary": "storage",
                "status": "completed",
                "filename": filename,
                "page_count": page_count,
                "image_count": image_count,
            }
        )
        logger.info(f"DB write complete: {filename} ({page_count} pages, {image_count} images)")
    except Exception as exc:
        conn.rollback()
        _trace_storage(
            {
                "boundary": "storage",
                "status": "failed",
                "filename": filename,
                "page_count": page_count,
                "image_count": image_count,
                "error_class": type(exc).__name__,
            }
        )
        raise
    finally:
        conn.close()
