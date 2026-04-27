"""Database write orchestration for the ingestion pipeline.

Wraps queries.py functions with Langfuse @observe spans (D-04).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from loguru import logger

try:
    from langfuse.decorators import observe, langfuse_context
    _LANGFUSE_AVAILABLE = True
except ImportError:
    _LANGFUSE_AVAILABLE = False
    # Provide no-op fallback if langfuse is not installed
    def observe(name=None, **kwargs):  # type: ignore[misc]
        def decorator(fn):
            return fn
        return decorator

from src.db.queries import insert_document, insert_page, mark_document_ingested, mark_document_error


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
    if _LANGFUSE_AVAILABLE:
        langfuse_context.update_current_trace(
            metadata={"doc_id": doc_id, "page_count": page_count},
        )

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
    logger.info(f"DB write complete: {filename} ({page_count} pages, {len(png_blobs)} images)")