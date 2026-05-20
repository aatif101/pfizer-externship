"""Read/write helpers for the compliance database.

Security: ALL SQL statements use parameterized ? placeholders.
Never use f-strings or % formatting with SQL (T-1-04).
"""
from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from src.db.schema import _connect


@dataclass(frozen=True)
class DocumentMetadata:
    """Typed document metadata loaded from the ingestion database."""

    doc_id: str
    filename: str
    file_path: str
    page_count: int
    status: str


@dataclass(frozen=True)
class DocumentPage:
    """Typed ingested page payload with 0-indexed page numbers preserved."""

    doc_id: str
    page_num: int
    page_text: str | None
    image_blob: bytes | None = None


@dataclass(frozen=True)
class LoadedDocumentPages:
    """Document metadata plus ordered ingested pages for extraction."""

    document: DocumentMetadata
    pages: tuple[DocumentPage, ...]


def insert_document(
    db_path: str,
    doc_id: str,
    filename: str,
    file_path: str,
    page_count: int,
    docling_json: Optional[str],
) -> None:
    """Insert or replace a document row. Uses ? placeholders (T-1-04)."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO documents "
        "(doc_id, filename, file_path, page_count, docling_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (doc_id, filename, file_path, page_count, docling_json),
    )
    conn.commit()
    conn.close()


def insert_page(
    db_path: str,
    doc_id: str,
    page_num: int,
    page_text: Optional[str],
    image_blob: Optional[bytes],
) -> None:
    """Insert or replace a page row with text and PNG BLOB (D-02)."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO pages (doc_id, page_num, page_text, image_blob) "
        "VALUES (?, ?, ?, ?)",
        (doc_id, page_num, page_text, sqlite3.Binary(image_blob) if image_blob else None),
    )
    conn.commit()
    conn.close()


def mark_document_ingested(db_path: str, doc_id: str) -> None:
    """Set status='ingested' for a document."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE documents SET status=? WHERE doc_id=?",
        ("ingested", doc_id),
    )
    conn.commit()
    conn.close()


def mark_document_error(db_path: str, doc_id: str, error_msg: str) -> None:
    """Set status='error' for a document. error_msg stored in docling_json field."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE documents SET status=?, docling_json=? WHERE doc_id=?",
        ("error", error_msg, doc_id),
    )
    conn.commit()
    conn.close()


def get_page_image(db_path: str, doc_id: str, page_num: int) -> Optional[Image.Image]:
    """Retrieve a stored PNG BLOB and return as PIL Image, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT image_blob FROM pages WHERE doc_id=? AND page_num=?",
        (doc_id, page_num),
    ).fetchone()
    conn.close()
    if row and row[0]:
        return Image.open(io.BytesIO(bytes(row[0])))
    return None


def load_document_pages(db_path: str, doc_id: str, *, include_image_bytes: bool = False) -> LoadedDocumentPages | None:
    """Load document metadata and ordered pages for extraction.

    Page numbers are returned exactly as persisted by ingestion, including the
    0-indexed numbering contract. The optional image blobs are off by default to
    avoid moving large payloads through the offline text-extraction path.
    """

    conn = _connect(db_path)
    try:
        document_row = conn.execute(
            """
            SELECT doc_id, filename, file_path, page_count, status
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document_row is None:
            return None

        if include_image_bytes:
            page_rows = conn.execute(
                """
                SELECT doc_id, page_num, page_text, image_blob
                FROM pages
                WHERE doc_id = ?
                ORDER BY page_num ASC
                """,
                (doc_id,),
            ).fetchall()
        else:
            page_rows = conn.execute(
                """
                SELECT doc_id, page_num, page_text, NULL
                FROM pages
                WHERE doc_id = ?
                ORDER BY page_num ASC
                """,
                (doc_id,),
            ).fetchall()
    finally:
        conn.close()

    document = DocumentMetadata(
        doc_id=document_row[0],
        filename=document_row[1],
        file_path=document_row[2],
        page_count=document_row[3],
        status=document_row[4],
    )
    pages = tuple(
        DocumentPage(
            doc_id=row[0],
            page_num=row[1],
            page_text=row[2],
            image_blob=bytes(row[3]) if row[3] is not None else None,
        )
        for row in page_rows
    )
    return LoadedDocumentPages(document=document, pages=pages)


def list_documents(db_path: str) -> list[dict]:
    """Return all document rows as dicts for Streamlit display."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT doc_id, filename, file_path, page_count, ingested_at, status "
        "FROM documents ORDER BY ingested_at DESC"
    ).fetchall()
    conn.close()
    columns = ["doc_id", "filename", "file_path", "page_count", "ingested_at", "status"]
    return [dict(zip(columns, row)) for row in rows]