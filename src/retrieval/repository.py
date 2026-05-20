"""Repository contract for persisted retrieval index state.

All data-bearing SQL uses parameterized placeholders. Raw page text is accepted
only through ``PageIndexInput`` and is never returned from this module; callers
receive hashes, lengths, run metadata, and 1-indexed display page numbers.
"""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable

from src.db.schema import _connect
from src.retrieval.models import (
    CorpusFingerprint,
    PageIndexInput,
    RetrievalIndexPageRecord,
    RetrievalIndexRun,
    RetrievalIndexStatus,
)


_SAFE_RUN_COLUMNS = (
    "run_id",
    "status",
    "built_at",
    "source_document_count",
    "source_page_count",
    "indexed_page_count",
    "content_hash",
    "previous_content_hash",
    "is_stale",
    "stale_reason",
    "error_reason",
)

_SAFE_PAGE_COLUMNS = (
    "doc_id",
    "page_num",
    "display_page_num",
    "filename",
    "text_sha256",
    "text_length",
    "snippet",
    "run_id",
    "indexed_at",
)


def compute_corpus_fingerprint(db_path: str) -> CorpusFingerprint:
    """Compute a deterministic fingerprint from ingested documents and pages.

    The hash includes doc IDs, filenames, page numbers, and page text content so
    changed source text marks an index stale. Image blobs and docling JSON are
    intentionally excluded to keep this lightweight and text-index scoped.
    """

    conn = _connect(db_path)
    try:
        doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        page_count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        rows = conn.execute(
            """
            SELECT d.doc_id, d.filename, p.page_num, COALESCE(p.page_text, '')
            FROM documents d
            JOIN pages p ON p.doc_id = d.doc_id
            ORDER BY d.doc_id ASC, p.page_num ASC
            """
        ).fetchall()
    finally:
        conn.close()

    digest = hashlib.sha256()
    for doc_id, filename, page_num, page_text in rows:
        digest.update(str(doc_id).encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(str(filename).encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(str(page_num).encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(str(page_text).encode("utf-8"))
        digest.update(b"\x1e")

    return CorpusFingerprint(document_count=doc_count, page_count=page_count, content_hash=digest.hexdigest())


def save_index_run(db_path: str, run: RetrievalIndexRun) -> None:
    """Insert or replace one retrieval index run metadata row."""

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO retrieval_index_runs (
                run_id, status, built_at, source_document_count, source_page_count,
                indexed_page_count, content_hash, previous_content_hash, is_stale,
                stale_reason, error_reason
            ) VALUES (?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')), ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status = excluded.status,
                built_at = excluded.built_at,
                source_document_count = excluded.source_document_count,
                source_page_count = excluded.source_page_count,
                indexed_page_count = excluded.indexed_page_count,
                content_hash = excluded.content_hash,
                previous_content_hash = excluded.previous_content_hash,
                is_stale = excluded.is_stale,
                stale_reason = excluded.stale_reason,
                error_reason = excluded.error_reason
            """,
            (
                run.run_id,
                run.status.value,
                run.built_at,
                run.source_document_count,
                run.source_page_count,
                run.indexed_page_count,
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


def save_index_run_with_pages(
    db_path: str,
    run: RetrievalIndexRun,
    pages: Iterable[PageIndexInput],
    *,
    snippets: dict[tuple[str, int], str] | None = None,
) -> list[RetrievalIndexPageRecord]:
    """Persist run metadata and current page index rows atomically.

    The page table represents the current inspectable index state. Existing page
    rows are cleared inside the same transaction before writing the new run's
    rows so failed builds cannot leave a half-updated index behind.
    """

    page_inputs = list(pages)
    snippets = snippets or {}
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        fts_enabled = _fts_table_exists(conn)
        _insert_index_run(conn, run)
        conn.execute("DELETE FROM retrieval_index_pages")
        if fts_enabled:
            conn.execute("DELETE FROM retrieval_index_page_fts")

        for page in page_inputs:
            _upsert_page_index_record(conn, run.run_id, page, snippets.get((page.doc_id, page.page_num), ""), fts_enabled)

        conn.commit()
        return _list_page_index_records(conn, run_id=run.run_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def load_latest_index_run(db_path: str) -> RetrievalIndexRun | None:
    """Return the latest persisted retrieval index run, if any."""

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"""
            SELECT {', '.join(_SAFE_RUN_COLUMNS)}
            FROM retrieval_index_runs
            ORDER BY built_at DESC, run_id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()

    return _run_from_row(row) if row is not None else None


def upsert_page_index_records(
    db_path: str, run_id: str, pages: Iterable[PageIndexInput], *, snippets: dict[tuple[str, int], str] | None = None
) -> list[RetrievalIndexPageRecord]:
    """Upsert page-level index metadata and optional FTS rows for one run.

    ``page_num`` remains the persisted 0-indexed ingestion value. The returned
    DTO exposes ``display_page_num`` as 1-indexed for later citation surfaces.
    """

    page_inputs = list(pages)
    snippets = snippets or {}
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        fts_enabled = _fts_table_exists(conn)
        records: list[RetrievalIndexPageRecord] = []
        for page in page_inputs:
            safe_text = page.page_text or ""
            text_hash = hashlib.sha256(safe_text.encode("utf-8")).hexdigest()
            conn.execute(
                """
                INSERT INTO retrieval_index_pages (
                    doc_id, page_num, display_page_num, filename, text_sha256,
                    text_length, snippet, run_id, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                ON CONFLICT(doc_id, page_num) DO UPDATE SET
                    display_page_num = excluded.display_page_num,
                    filename = excluded.filename,
                    text_sha256 = excluded.text_sha256,
                    text_length = excluded.text_length,
                    snippet = excluded.snippet,
                    run_id = excluded.run_id,
                    indexed_at = excluded.indexed_at
                """,
                (
                    page.doc_id,
                    page.page_num,
                    page.page_num + 1,
                    page.filename,
                    text_hash,
                    len(safe_text),
                    snippets.get((page.doc_id, page.page_num), ""),
                    run_id,
                ),
            )
            if fts_enabled:
                conn.execute(
                    "DELETE FROM retrieval_index_page_fts WHERE doc_id = ? AND page_num = ?",
                    (page.doc_id, page.page_num),
                )
                conn.execute(
                    "INSERT INTO retrieval_index_page_fts (doc_id, page_num, page_text) VALUES (?, ?, ?)",
                    (page.doc_id, page.page_num, safe_text),
                )

        conn.commit()
        for page in page_inputs:
            row = conn.execute(
                f"""
                SELECT {', '.join(_SAFE_PAGE_COLUMNS)}
                FROM retrieval_index_pages
                WHERE doc_id = ? AND page_num = ?
                """,
                (page.doc_id, page.page_num),
            ).fetchone()
            records.append(_page_from_row(row))
        return records
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_page_index_records(db_path: str, run_id: str | None = None) -> list[RetrievalIndexPageRecord]:
    """List persisted page metadata in deterministic citation order."""

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if run_id is None:
            rows = conn.execute(
                f"""
                SELECT {', '.join(_SAFE_PAGE_COLUMNS)}
                FROM retrieval_index_pages
                ORDER BY doc_id ASC, page_num ASC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT {', '.join(_SAFE_PAGE_COLUMNS)}
                FROM retrieval_index_pages
                WHERE run_id = ?
                ORDER BY doc_id ASC, page_num ASC
                """,
                (run_id,),
            ).fetchall()
    finally:
        conn.close()

    return [_page_from_row(row) for row in rows]


def retrieval_fts_available(db_path: str) -> bool:
    """Return whether the optional retrieval FTS5 table exists."""

    conn = _connect(db_path)
    try:
        return _fts_table_exists(conn)
    finally:
        conn.close()


def _insert_index_run(conn: sqlite3.Connection, run: RetrievalIndexRun) -> None:
    conn.execute(
        """
        INSERT INTO retrieval_index_runs (
            run_id, status, built_at, source_document_count, source_page_count,
            indexed_page_count, content_hash, previous_content_hash, is_stale,
            stale_reason, error_reason
        ) VALUES (?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')), ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            status = excluded.status,
            built_at = excluded.built_at,
            source_document_count = excluded.source_document_count,
            source_page_count = excluded.source_page_count,
            indexed_page_count = excluded.indexed_page_count,
            content_hash = excluded.content_hash,
            previous_content_hash = excluded.previous_content_hash,
            is_stale = excluded.is_stale,
            stale_reason = excluded.stale_reason,
            error_reason = excluded.error_reason
        """,
        (
            run.run_id,
            run.status.value,
            run.built_at,
            run.source_document_count,
            run.source_page_count,
            run.indexed_page_count,
            run.content_hash,
            run.previous_content_hash,
            int(run.is_stale),
            run.stale_reason,
            run.error_reason,
        ),
    )


def _upsert_page_index_record(
    conn: sqlite3.Connection, run_id: str, page: PageIndexInput, snippet: str, fts_enabled: bool
) -> None:
    safe_text = page.page_text or ""
    text_hash = hashlib.sha256(safe_text.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO retrieval_index_pages (
            doc_id, page_num, display_page_num, filename, text_sha256,
            text_length, snippet, run_id, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(doc_id, page_num) DO UPDATE SET
            display_page_num = excluded.display_page_num,
            filename = excluded.filename,
            text_sha256 = excluded.text_sha256,
            text_length = excluded.text_length,
            snippet = excluded.snippet,
            run_id = excluded.run_id,
            indexed_at = excluded.indexed_at
        """,
        (
            page.doc_id,
            page.page_num,
            page.page_num + 1,
            page.filename,
            text_hash,
            len(safe_text),
            snippet,
            run_id,
        ),
    )
    if fts_enabled:
        conn.execute(
            "DELETE FROM retrieval_index_page_fts WHERE doc_id = ? AND page_num = ?",
            (page.doc_id, page.page_num),
        )
        conn.execute(
            "INSERT INTO retrieval_index_page_fts (doc_id, page_num, page_text) VALUES (?, ?, ?)",
            (page.doc_id, page.page_num, safe_text),
        )


def _list_page_index_records(conn: sqlite3.Connection, run_id: str | None = None) -> list[RetrievalIndexPageRecord]:
    if run_id is None:
        rows = conn.execute(
            f"""
            SELECT {', '.join(_SAFE_PAGE_COLUMNS)}
            FROM retrieval_index_pages
            ORDER BY doc_id ASC, page_num ASC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT {', '.join(_SAFE_PAGE_COLUMNS)}
            FROM retrieval_index_pages
            WHERE run_id = ?
            ORDER BY doc_id ASC, page_num ASC
            """,
            (run_id,),
        ).fetchall()
    return [_page_from_row(row) for row in rows]


def _fts_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
        ("table", "retrieval_index_page_fts"),
    ).fetchone()
    return row is not None


def _run_from_row(row: sqlite3.Row) -> RetrievalIndexRun:
    return RetrievalIndexRun(
        run_id=row["run_id"],
        status=RetrievalIndexStatus(row["status"]),
        built_at=row["built_at"],
        source_document_count=row["source_document_count"],
        source_page_count=row["source_page_count"],
        indexed_page_count=row["indexed_page_count"],
        content_hash=row["content_hash"],
        previous_content_hash=row["previous_content_hash"],
        is_stale=bool(row["is_stale"]),
        stale_reason=row["stale_reason"],
        error_reason=row["error_reason"],
    )


def _page_from_row(row: sqlite3.Row) -> RetrievalIndexPageRecord:
    return RetrievalIndexPageRecord(
        doc_id=row["doc_id"],
        page_num=row["page_num"],
        display_page_num=row["display_page_num"],
        filename=row["filename"],
        text_sha256=row["text_sha256"],
        text_length=row["text_length"],
        snippet=row["snippet"],
        run_id=row["run_id"],
        indexed_at=row["indexed_at"],
    )
