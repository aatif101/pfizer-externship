"""Schema tests for additive run-scoped extraction history."""
from __future__ import annotations

import sqlite3

import pytest


HISTORY_TABLES = {
    "extraction_runs",
    "extraction_history",
    "compliance_record_history",
}

EXPECTED_INDEXES = {
    "idx_extraction_runs_started_at",
    "idx_extraction_runs_created_at",
    "idx_extraction_runs_status",
    "idx_extraction_history_run_id",
    "idx_extraction_history_doc_id",
    "idx_extraction_history_run_doc",
    "idx_extraction_history_trace_id",
    "idx_compliance_history_run_id",
    "idx_compliance_history_doc_id",
    "idx_compliance_history_run_doc",
    "idx_compliance_history_trace_id",
    "idx_compliance_history_risk",
    "idx_compliance_history_review",
}

FORBIDDEN_RAW_CONTENT_COLUMNS = {
    "prompt",
    "prompts",
    "page_text",
    "image_blob",
    "provider_payload",
    "provider_payloads",
    "file_contents",
    "file_content",
    "pdf",
    "pdf_blob",
    "secret",
    "secrets",
    "local_artifact_path",
    "artifact_path",
    "file_path",
    "docling_json",
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    }


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _connect_with_foreign_keys(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_run_history_tables_and_key_indexes_exist(tmp_db_path: str) -> None:
    """Fresh DB initialization creates the additive run history surface."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    try:
        assert HISTORY_TABLES <= _table_names(conn)
        assert EXPECTED_INDEXES <= _index_names(conn)
    finally:
        conn.close()


def test_run_history_schema_initialization_is_idempotent(tmp_db_path: str) -> None:
    """Repeated initialization must not fail or duplicate incompatible schema objects."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)
    init_db(tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    try:
        assert HISTORY_TABLES <= _table_names(conn)
        assert EXPECTED_INDEXES <= _index_names(conn)
    finally:
        conn.close()


def test_history_tables_do_not_expose_forbidden_raw_content_columns(tmp_db_path: str) -> None:
    """History tables may expose metadata, but not prompts, raw page/image payloads, or paths."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    try:
        for table_name in HISTORY_TABLES:
            columns = _column_names(conn, table_name)
            assert columns.isdisjoint(FORBIDDEN_RAW_CONTENT_COLUMNS), table_name
    finally:
        conn.close()


def test_extraction_history_requires_existing_run_and_document(tmp_db_path: str) -> None:
    """FK enforcement prevents orphaned field history rows."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)

    conn = _connect_with_foreign_keys(tmp_db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO extraction_history (run_id, doc_id, field_name, field_value)
                VALUES (?, ?, ?, ?)
                """,
                ("missing-run", "missing-doc", "vendor_name", "Acme"),
            )
            conn.commit()

        conn.execute(
            """
            INSERT INTO documents (doc_id, filename, file_path, page_count)
            VALUES (?, ?, ?, ?)
            """,
            ("doc-1", "doc.pdf", "sanitized-test-path", 1),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO extraction_history (run_id, doc_id, field_name, field_value)
                VALUES (?, ?, ?, ?)
                """,
                ("missing-run", "doc-1", "vendor_name", "Acme"),
            )
            conn.commit()
    finally:
        conn.close()


def test_compliance_history_requires_existing_run_and_document(tmp_db_path: str) -> None:
    """FK enforcement prevents orphaned compliance history rows."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)

    conn = _connect_with_foreign_keys(tmp_db_path)
    try:
        conn.execute(
            """
            INSERT INTO extraction_runs (run_id, status, document_count, field_count)
            VALUES (?, ?, ?, ?)
            """,
            ("run-1", "completed", 1, 6),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO compliance_record_history (run_id, doc_id, risk_level)
                VALUES (?, ?, ?)
                """,
                ("run-1", "missing-doc", "low"),
            )
            conn.commit()
    finally:
        conn.close()
