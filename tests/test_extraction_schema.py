"""Tests for Phase 2 extraction/compliance SQLite schema evolution."""
from __future__ import annotations

import sqlite3

import pytest


REQUIRED_EXTRACTION_COLUMNS = {
    "review_state",
    "abstention_reason",
    "normalized_value",
    "updated_at",
}

REQUIRED_COMPLIANCE_COLUMNS = {
    "doc_id",
    "doc_type",
    "vendor_name",
    "manufacturing_date",
    "effective_date",
    "revision_date",
    "expiry_date",
    "aggregate_confidence",
    "review_state",
    "needs_review",
    "trace_id",
    "run_id",
    "extracted_at",
    "created_at",
    "updated_at",
    "risk_level",
    "risk_reason",
    "compliance_status",
    "age_days",
    "source_page",
    "source_bbox",
    "source_verbatim_span",
}


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def index_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}


def create_phase_1_database(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE documents (
            doc_id       TEXT PRIMARY KEY,
            filename     TEXT NOT NULL,
            file_path    TEXT NOT NULL,
            page_count   INTEGER NOT NULL,
            ingested_at  TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            docling_json TEXT,
            status       TEXT DEFAULT 'pending'
        );

        CREATE TABLE pages (
            page_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id     TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            page_num   INTEGER NOT NULL,
            page_text  TEXT,
            image_blob BLOB,
            UNIQUE (doc_id, page_num)
        );

        CREATE TABLE extractions (
            extraction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id        TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            field_name    TEXT NOT NULL,
            field_value   TEXT,
            confidence    REAL,
            source_page   INTEGER,
            source_bbox   TEXT,
            verbatim_span TEXT,
            trace_id      TEXT,
            created_at    TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            needs_review  BOOLEAN DEFAULT 0,
            UNIQUE (doc_id, field_name)
        );

        INSERT INTO documents (doc_id, filename, file_path, page_count, status)
        VALUES ('doc-legacy', 'legacy.pdf', '/tmp/legacy.pdf', 1, 'ingested');
        INSERT INTO pages (doc_id, page_num, page_text)
        VALUES ('doc-legacy', 0, 'legacy page text');
        INSERT INTO extractions (
            doc_id, field_name, field_value, confidence, source_page,
            source_bbox, verbatim_span, trace_id, needs_review
        ) VALUES (
            'doc-legacy', 'vendor_name', 'Legacy Vendor', 0.82, 0,
            '{"x":1}', 'Legacy Vendor', 'trace-legacy', 0
        );
        """
    )
    conn.commit()
    conn.close()


def test_fresh_db_has_phase_2_extraction_and_compliance_schema(tmp_db_path: str) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert "compliance_records" in tables
    assert REQUIRED_EXTRACTION_COLUMNS <= table_columns(conn, "extractions")
    assert REQUIRED_COMPLIANCE_COLUMNS <= table_columns(conn, "compliance_records")

    indexes = index_names(conn)
    assert "idx_extractions_review_state" in indexes
    assert "idx_extractions_needs_review" in indexes
    assert "idx_compliance_review_state" in indexes
    assert "idx_compliance_risk_level" in indexes
    assert "idx_compliance_expiry_date" in indexes
    conn.close()


def test_phase_1_db_migration_adds_columns_and_preserves_rows(tmp_path) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    db_path = str(tmp_path / "phase1.sqlite")
    create_phase_1_database(db_path)

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    assert REQUIRED_EXTRACTION_COLUMNS <= table_columns(conn, "extractions")
    assert REQUIRED_COMPLIANCE_COLUMNS <= table_columns(conn, "compliance_records")

    row = conn.execute(
        """
        SELECT doc_id, field_name, field_value, confidence, verbatim_span, trace_id
        FROM extractions
        WHERE doc_id = ? AND field_name = ?
        """,
        ("doc-legacy", "vendor_name"),
    ).fetchone()
    assert row == ("doc-legacy", "vendor_name", "Legacy Vendor", 0.82, "Legacy Vendor", "trace-legacy")
    conn.close()


def test_init_db_is_idempotent_for_phase_2_migrations(tmp_path) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    db_path = str(tmp_path / "idempotent.sqlite")
    create_phase_1_database(db_path)

    init_db(db_path)
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    extraction_columns = [row[1] for row in conn.execute("PRAGMA table_info(extractions)")]
    conn.close()

    for column_name in REQUIRED_EXTRACTION_COLUMNS:
        assert extraction_columns.count(column_name) == 1


def test_compliance_records_fk_rejects_unknown_document(tmp_db_path: str) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO compliance_records (
                doc_id, doc_type, vendor_name, aggregate_confidence, review_state, trace_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("missing-doc", "SDF", "Vendor", 0.9, "pending", "trace-001"),
        )
        conn.commit()

    conn.close()


def test_compliance_records_cascade_when_document_deleted(tmp_db_path: str) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        INSERT INTO documents (doc_id, filename, file_path, page_count)
        VALUES (?, ?, ?, ?)
        """,
        ("doc-001", "supplier.pdf", "/tmp/supplier.pdf", 1),
    )
    conn.execute(
        """
        INSERT INTO compliance_records (
            doc_id, doc_type, vendor_name, expiry_date, aggregate_confidence,
            review_state, needs_review, trace_id, run_id, risk_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("doc-001", "SDF", "Supplier", "2026-01-01", 0.91, "pending", 0, "trace-1", "run-1", None),
    )
    conn.execute("DELETE FROM documents WHERE doc_id = ?", ("doc-001",))
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM compliance_records WHERE doc_id = ?", ("doc-001",)).fetchone()[0]
    conn.close()

    assert count == 0
