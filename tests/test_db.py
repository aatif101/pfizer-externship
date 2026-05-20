"""Tests for src/db/schema.py — schema creation and FK enforcement."""
from __future__ import annotations

import sqlite3

import pytest


def test_schema_exists(tmp_db_path: str) -> None:
    """INGEST SC-4: SQLite schema must have core ingestion, extraction, compliance, and eval tables."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "documents" in tables, "documents table missing"
    assert "pages" in tables, "pages table missing"
    assert "extractions" in tables, "extractions table missing"
    assert "compliance_records" in tables, "compliance_records table missing"
    assert "evaluations" in tables, "evaluations table missing"


def test_fk_enforcement(tmp_db_path: str) -> None:
    """FK enforcement must prevent inserting a page for a non-existent doc_id."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO pages (doc_id, page_num) VALUES (?, ?)",
            ("nonexistent_doc_id", 0),
        )
        conn.commit()
    conn.close()


def test_parameterized_queries_only(tmp_db_path: str) -> None:
    """Security: filenames with SQL metacharacters must not cause query errors."""
    from src.db.schema import init_db  # noqa: PLC0415
    from src.db.queries import insert_document  # noqa: PLC0415

    init_db(tmp_db_path)
    # filename contains SQL injection attempt — must be stored safely via parameterized query
    malicious_filename = "'; DROP TABLE documents; --"
    insert_document(
        db_path=tmp_db_path,
        doc_id="test_doc_001",
        filename=malicious_filename,
        file_path="/tmp/test.pdf",
        page_count=1,
        docling_json=None,
    )
    conn = sqlite3.connect(tmp_db_path)
    row = conn.execute("SELECT filename FROM documents WHERE doc_id='test_doc_001'").fetchone()
    conn.close()
    assert row is not None, "Document not inserted"
    assert row[0] == malicious_filename, "Filename was corrupted or injection succeeded"