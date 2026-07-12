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


@dataclass(frozen=True)
class DocumentIdentityLookup:
    """Stored identity/completeness facts used by the ingestion boundary."""

    doc_id: str
    content_sha256: str | None
    status: str
    page_count: int
    persisted_page_count: int
    first_page_num: int | None
    last_page_num: int | None


def _upsert_document(
    conn: sqlite3.Connection,
    doc_id: str,
    filename: str,
    file_path: str,
    page_count: int,
    docling_json: Optional[str],
    *,
    content_sha256: str | None = None,
) -> None:
    """Upsert a document without replacing its parent row or cascading children."""

    conn.execute(
        """
        INSERT INTO documents (
            doc_id, filename, file_path, page_count, docling_json, status,
            content_sha256
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        ON CONFLICT(doc_id) DO UPDATE SET
            filename = excluded.filename,
            file_path = excluded.file_path,
            page_count = excluded.page_count,
            docling_json = excluded.docling_json,
            status = 'pending',
            content_sha256 = COALESCE(excluded.content_sha256, documents.content_sha256)
        """,
        (doc_id, filename, file_path, page_count, docling_json, content_sha256),
    )


def _upsert_page(
    conn: sqlite3.Connection,
    doc_id: str,
    page_num: int,
    page_text: Optional[str],
    image_blob: Optional[bytes],
) -> None:
    """Upsert one page on a caller-owned transaction."""

    conn.execute(
        """
        INSERT INTO pages (doc_id, page_num, page_text, image_blob)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(doc_id, page_num) DO UPDATE SET
            page_text = excluded.page_text,
            image_blob = excluded.image_blob
        """,
        (
            doc_id,
            page_num,
            page_text,
            sqlite3.Binary(image_blob) if image_blob is not None else None,
        ),
    )


def _mark_document_ingested(conn: sqlite3.Connection, doc_id: str) -> None:
    """Mark a document complete on a caller-owned transaction."""

    conn.execute("UPDATE documents SET status=? WHERE doc_id=?", ("ingested", doc_id))


def insert_document(
    db_path: str,
    doc_id: str,
    filename: str,
    file_path: str,
    page_count: int,
    docling_json: Optional[str],
    *,
    content_sha256: str | None = None,
) -> None:
    """Insert or update a document row. Uses ? placeholders (T-1-04)."""
    conn = _connect(db_path)
    try:
        _upsert_document(
            conn,
            doc_id,
            filename,
            file_path,
            page_count,
            docling_json,
            content_sha256=content_sha256,
        )
        conn.commit()
    finally:
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
    try:
        _upsert_page(conn, doc_id, page_num, page_text, image_blob)
        conn.commit()
    finally:
        conn.close()


def mark_document_ingested(db_path: str, doc_id: str) -> None:
    """Set status='ingested' for a document."""
    conn = _connect(db_path)
    try:
        _mark_document_ingested(conn, doc_id)
        conn.commit()
    finally:
        conn.close()


def lookup_document_identity(
    db_path: str,
    content_sha256: str,
    legacy_doc_id: str,
) -> DocumentIdentityLookup | None:
    """Find content identity first, then the exact legacy path-derived row."""

    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT
                d.doc_id,
                d.content_sha256,
                d.status,
                d.page_count,
                COUNT(p.page_id) AS persisted_page_count,
                MIN(p.page_num) AS first_page_num,
                MAX(p.page_num) AS last_page_num
            FROM documents AS d
            LEFT JOIN pages AS p ON p.doc_id = d.doc_id
            WHERE d.content_sha256 = ? OR d.doc_id = ?
            GROUP BY d.doc_id
            ORDER BY CASE WHEN d.content_sha256 = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (content_sha256, legacy_doc_id, content_sha256),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return DocumentIdentityLookup(
        doc_id=str(row[0]),
        content_sha256=row[1],
        status=str(row[2]),
        page_count=int(row[3]),
        persisted_page_count=int(row[4]),
        first_page_num=int(row[5]) if row[5] is not None else None,
        last_page_num=int(row[6]) if row[6] is not None else None,
    )


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
