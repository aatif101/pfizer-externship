"""Database write orchestration for the ingestion pipeline.

Wraps queries.py functions with Langfuse @observe spans (D-04).
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from src.tracing import observe, safe_update_current_trace
from src.db.queries import insert_document, insert_page, mark_document_ingested

_STORAGE_TRACE_METADATA_KEYS = frozenset(
    {"boundary", "status", "doc_id", "filename", "page_count", "image_count", "error_class"}
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
) -> None:
    """Write document header and all page rows to SQLite (D-02: BLOBs in DB)."""
    image_count = len(png_blobs)
    _trace_storage(
        {
            "boundary": "storage",
            "status": "started",
            "doc_id": doc_id,
            "filename": filename,
            "page_count": page_count,
            "image_count": image_count,
        }
    )

    try:
        insert_document(
            db_path=db_path,
            doc_id=doc_id,
            filename=filename,
            file_path=file_path,
            page_count=page_count,
            docling_json=docling_json,
        )

        for page_num in range(page_count):
            blob = png_blobs[page_num] if page_num < len(png_blobs) else None
            text = page_texts.get(page_num, page_texts.get(page_num + 1, ""))
            insert_page(
                db_path=db_path,
                doc_id=doc_id,
                page_num=page_num,
                page_text=text,
                image_blob=blob,
            )

        mark_document_ingested(db_path=db_path, doc_id=doc_id)
        _trace_storage(
            {
                "boundary": "storage",
                "status": "completed",
                "doc_id": doc_id,
                "filename": filename,
                "page_count": page_count,
                "image_count": image_count,
            }
        )
        logger.info(f"DB write complete: {filename} ({page_count} pages, {image_count} images)")
    except Exception as exc:
        _trace_storage(
            {
                "boundary": "storage",
                "status": "failed",
                "doc_id": doc_id,
                "filename": filename,
                "page_count": page_count,
                "image_count": image_count,
                "error_class": type(exc).__name__,
            }
        )
        raise