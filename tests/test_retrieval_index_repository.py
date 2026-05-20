"""Tests for retrieval index schema and repository contract."""
from __future__ import annotations

import hashlib
import sqlite3

from src.db.queries import insert_document, insert_page
from src.db.schema import init_db
from src.retrieval.models import PageIndexInput, RetrievalIndexRun, RetrievalIndexStatus
from src.retrieval.repository import (
    compute_corpus_fingerprint,
    list_page_index_records,
    load_latest_index_run,
    retrieval_fts_available,
    save_index_run,
    upsert_page_index_records,
)


def _seed_document_with_pages(tmp_db_path: str, filename: str = "sdf.pdf") -> None:
    insert_document(
        db_path=tmp_db_path,
        doc_id="doc-1",
        filename=filename,
        file_path=f"/tmp/{filename}",
        page_count=2,
        docling_json=None,
    )
    insert_page(tmp_db_path, "doc-1", 0, "Certificate page zero", None)
    insert_page(tmp_db_path, "doc-1", 1, "Supplier page one", None)


def test_retrieval_index_schema_exists_and_init_is_idempotent(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    init_db(tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    }
    indexes = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name").fetchall()
    }
    conn.close()

    assert "retrieval_index_runs" in tables
    assert "retrieval_index_pages" in tables
    assert "idx_retrieval_runs_status" in indexes
    assert "idx_retrieval_pages_run_id" in indexes


def test_store_and_load_latest_index_run_metadata(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    save_index_run(
        tmp_db_path,
        RetrievalIndexRun(
            run_id="run-001",
            status=RetrievalIndexStatus.BUILT,
            built_at="2026-01-01T00:00:00Z",
            source_document_count=3,
            source_page_count=7,
            indexed_page_count=6,
            content_hash="current-hash",
            previous_content_hash="previous-hash",
            is_stale=False,
            stale_reason=None,
            error_reason=None,
        ),
    )

    latest = load_latest_index_run(tmp_db_path)

    assert latest is not None
    assert latest.run_id == "run-001"
    assert latest.status is RetrievalIndexStatus.BUILT
    assert latest.source_document_count == 3
    assert latest.source_page_count == 7
    assert latest.indexed_page_count == 6
    assert latest.content_hash == "current-hash"
    assert latest.previous_content_hash == "previous-hash"
    assert latest.is_stale is False


def test_upsert_and_list_page_index_records_hide_raw_text(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_document_with_pages(tmp_db_path)
    save_index_run(
        tmp_db_path,
        RetrievalIndexRun(
            run_id="run-001",
            status=RetrievalIndexStatus.BUILT,
            built_at=None,
            source_document_count=1,
            source_page_count=2,
            indexed_page_count=2,
            content_hash="hash",
        ),
    )

    records = upsert_page_index_records(
        tmp_db_path,
        "run-001",
        [
            PageIndexInput("doc-1", 0, "sdf.pdf", "Certificate page zero"),
            PageIndexInput("doc-1", 1, "sdf.pdf", "Supplier page one"),
        ],
    )
    listed = list_page_index_records(tmp_db_path, run_id="run-001")

    assert records == listed
    assert [record.page_num for record in listed] == [0, 1]
    assert [record.display_page_num for record in listed] == [1, 2]
    assert listed[0].text_sha256 == hashlib.sha256(b"Certificate page zero").hexdigest()
    assert listed[0].text_length == len("Certificate page zero")
    assert all(not hasattr(record, "page_text") for record in listed)


def test_upserting_page_records_is_idempotent_and_updates_hash(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_document_with_pages(tmp_db_path)
    save_index_run(
        tmp_db_path,
        RetrievalIndexRun(
            run_id="run-001",
            status=RetrievalIndexStatus.BUILT,
            built_at=None,
            source_document_count=1,
            source_page_count=2,
            indexed_page_count=1,
            content_hash="hash",
        ),
    )

    upsert_page_index_records(tmp_db_path, "run-001", [PageIndexInput("doc-1", 0, "sdf.pdf", "old")])
    upsert_page_index_records(tmp_db_path, "run-001", [PageIndexInput("doc-1", 0, "sdf.pdf", "new")])

    listed = list_page_index_records(tmp_db_path)
    assert len(listed) == 1
    assert listed[0].text_sha256 == hashlib.sha256(b"new").hexdigest()
    assert listed[0].text_length == 3


def test_corpus_fingerprint_tracks_documents_pages_and_text(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_document_with_pages(tmp_db_path)

    fingerprint = compute_corpus_fingerprint(tmp_db_path)

    assert fingerprint.document_count == 1
    assert fingerprint.page_count == 2
    assert len(fingerprint.content_hash) == 64


def test_sql_metacharacters_are_stored_safely_without_raw_text_leak(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    malicious_filename = "sdf'); DROP TABLE retrieval_index_runs; --.pdf"
    malicious_text = "alpha'); DROP TABLE documents; -- beta"
    _seed_document_with_pages(tmp_db_path, filename=malicious_filename)
    save_index_run(
        tmp_db_path,
        RetrievalIndexRun(
            run_id="run-001",
            status=RetrievalIndexStatus.BUILT,
            built_at=None,
            source_document_count=1,
            source_page_count=2,
            indexed_page_count=1,
            content_hash="hash",
        ),
    )

    [record] = upsert_page_index_records(
        tmp_db_path,
        "run-001",
        [PageIndexInput("doc-1", 0, malicious_filename, malicious_text)],
    )

    assert record.filename == malicious_filename
    assert record.text_sha256 == hashlib.sha256(malicious_text.encode("utf-8")).hexdigest()
    assert not hasattr(record, "page_text")

    conn = sqlite3.connect(tmp_db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM retrieval_index_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM retrieval_index_pages").fetchone()[0] == 1
    finally:
        conn.close()


def test_optional_fts_table_is_hidden_behind_repository(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_document_with_pages(tmp_db_path)
    save_index_run(
        tmp_db_path,
        RetrievalIndexRun(
            run_id="run-001",
            status=RetrievalIndexStatus.BUILT,
            built_at=None,
            source_document_count=1,
            source_page_count=2,
            indexed_page_count=1,
            content_hash="hash",
        ),
    )

    upsert_page_index_records(tmp_db_path, "run-001", [PageIndexInput("doc-1", 0, "sdf.pdf", "needle text")])

    if retrieval_fts_available(tmp_db_path):
        conn = sqlite3.connect(tmp_db_path)
        try:
            row = conn.execute(
                "SELECT doc_id, page_num FROM retrieval_index_page_fts WHERE retrieval_index_page_fts MATCH ?",
                ("needle",),
            ).fetchone()
            assert row == ("doc-1", 0)
        finally:
            conn.close()
