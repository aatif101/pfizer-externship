"""Schema tests for additive run-scoped extraction history."""
from __future__ import annotations

import sqlite3

import pytest


HISTORY_TABLES = {
    "extraction_runs",
    "extraction_run_documents",
    "extraction_history",
    "compliance_record_history",
}

RUN_PROVENANCE_COLUMNS = {
    "expected_document_count",
    "attempted_document_count",
    "succeeded_document_count",
    "failed_document_count",
    "provider",
    "requested_model",
    "resolved_model",
    "corpus_version",
    "manifest_hash",
}

RUN_DOCUMENT_COLUMNS = {
    "run_id",
    "doc_id",
    "status",
    "attempt_count",
    "trace_id",
    "error_reason",
    "started_at",
    "completed_at",
    "updated_at",
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
    "idx_extraction_run_documents_status",
    "idx_extraction_runs_manifest_hash",
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


def _create_pre_lifecycle_database(db_path: str) -> None:
    """Create the exact history/usage surface that predates run lifecycle columns."""

    conn = _connect_with_foreign_keys(db_path)
    conn.executescript(
        """
        CREATE TABLE documents (
            doc_id TEXT PRIMARY KEY, filename TEXT NOT NULL, file_path TEXT NOT NULL,
            page_count INTEGER NOT NULL, status TEXT DEFAULT 'pending'
        );
        CREATE TABLE extraction_runs (
            run_id TEXT PRIMARY KEY, status TEXT NOT NULL,
            document_count INTEGER NOT NULL DEFAULT 0,
            field_count INTEGER NOT NULL DEFAULT 0,
            trace_id TEXT, started_at TIMESTAMP, completed_at TIMESTAMP,
            created_at TIMESTAMP, updated_at TIMESTAMP
        );
        CREATE TABLE extraction_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            field_name TEXT NOT NULL, field_value TEXT, confidence REAL,
            source_page INTEGER, source_bbox TEXT, verbatim_span TEXT, trace_id TEXT,
            created_at TIMESTAMP, needs_review BOOLEAN DEFAULT 0, review_state TEXT,
            abstention_reason TEXT, normalized_value TEXT, evidence_type TEXT,
            extracted_at TIMESTAMP, updated_at TIMESTAMP,
            UNIQUE(run_id, doc_id, field_name)
        );
        CREATE TABLE compliance_record_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            doc_type TEXT, vendor_name TEXT, manufacturing_date TEXT,
            effective_date TEXT, revision_date TEXT, expiry_date TEXT,
            aggregate_confidence REAL, review_state TEXT, needs_review BOOLEAN DEFAULT 0,
            trace_id TEXT, extracted_at TIMESTAMP, created_at TIMESTAMP, updated_at TIMESTAMP,
            risk_level TEXT, risk_reason TEXT, compliance_status TEXT, age_days INTEGER,
            source_page INTEGER, source_bbox TEXT, source_verbatim_span TEXT,
            source_evidence_type TEXT, UNIQUE(run_id, doc_id)
        );
        CREATE TABLE extraction_usage_observations (
            observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            stage TEXT NOT NULL, provider TEXT, model TEXT, status TEXT NOT NULL,
            latency_ms REAL, input_tokens INTEGER, output_tokens INTEGER,
            total_tokens INTEGER, estimated_cost_usd REAL, trace_id TEXT,
            error_reason TEXT, created_at TIMESTAMP
        );
        INSERT INTO documents (doc_id, filename, file_path, page_count, status)
        VALUES ('doc-legacy', 'legacy.pdf', 'bounded-legacy-path', 1, 'ingested');
        INSERT INTO extraction_runs (
            run_id, status, document_count, field_count, trace_id,
            started_at, completed_at, created_at
        ) VALUES (
            'run-legacy', 'completed', 1, 6, 'trace-legacy',
            '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z', '2026-01-01T00:00:00Z'
        );
        INSERT INTO extraction_runs (
            run_id, status, document_count, field_count, started_at, created_at
        ) VALUES (
            'run-empty', 'running', 0, 0,
            '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z'
        );
        INSERT INTO extraction_history (
            run_id, doc_id, field_name, field_value, confidence, source_page,
            source_bbox, verbatim_span, trace_id, review_state, normalized_value,
            evidence_type, extracted_at
        ) VALUES
            ('run-legacy','doc-legacy','doc_type','Certificate',0.9,0,'{"x":1}','Certificate','trace-legacy','pending','Certificate','text','2026-01-01T00:01:00Z'),
            ('run-legacy','doc-legacy','vendor_name','Legacy Vendor',0.9,0,'{"x":2}','Legacy Vendor','trace-legacy','pending','Legacy Vendor','text','2026-01-01T00:01:00Z'),
            ('run-legacy','doc-legacy','manufacturing_date','2024-01-01',0.9,0,NULL,'2024-01-01','trace-legacy','pending','2024-01-01','text','2026-01-01T00:01:00Z'),
            ('run-legacy','doc-legacy','effective_date','2024-02-01',0.9,0,NULL,'2024-02-01','trace-legacy','pending','2024-02-01','text','2026-01-01T00:01:00Z'),
            ('run-legacy','doc-legacy','revision_date','2024-03-01',0.9,0,NULL,'2024-03-01','trace-legacy','pending','2024-03-01','text','2026-01-01T00:01:00Z'),
            ('run-legacy','doc-legacy','expiry_date','2027-01-01',0.9,0,NULL,'2027-01-01','trace-legacy','pending','2027-01-01','text','2026-01-01T00:01:00Z');
        INSERT INTO compliance_record_history (
            run_id, doc_id, doc_type, vendor_name, expiry_date,
            aggregate_confidence, review_state, trace_id, risk_level,
            source_page, source_bbox, source_verbatim_span, source_evidence_type
        ) VALUES (
            'run-legacy','doc-legacy','Certificate','Legacy Vendor','2027-01-01',
            0.9,'pending','trace-legacy','green',0,'{"x":1}','Certificate','text'
        );
        INSERT INTO extraction_usage_observations (
            run_id, doc_id, stage, provider, model, status, input_tokens,
            output_tokens, total_tokens, estimated_cost_usd, trace_id
        ) VALUES (
            'run-legacy','doc-legacy','text','gemini','gemini-2.5-flash',
            'completed',100,20,120,0.0001,'trace-legacy'
        );
        """
    )
    conn.commit()
    conn.close()


def test_run_history_tables_and_key_indexes_exist(tmp_db_path: str) -> None:
    """Fresh DB initialization creates the additive run history surface."""
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    try:
        assert HISTORY_TABLES <= _table_names(conn)
        assert EXPECTED_INDEXES <= _index_names(conn)
        assert RUN_PROVENANCE_COLUMNS <= _column_names(conn, "extraction_runs")
        assert RUN_DOCUMENT_COLUMNS <= _column_names(conn, "extraction_run_documents")
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


def test_pre_lifecycle_history_migrates_twice_without_data_loss_or_duplicate_children(tmp_path) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    db_path = str(tmp_path / "pre-lifecycle.sqlite")
    _create_pre_lifecycle_database(db_path)
    init_db(db_path)
    init_db(db_path)

    conn = _connect_with_foreign_keys(db_path)
    try:
        fields = conn.execute(
            """
            SELECT field_name, field_value, source_page, source_bbox, verbatim_span
            FROM extraction_history WHERE run_id = ? AND doc_id = ? ORDER BY field_name
            """,
            ("run-legacy", "doc-legacy"),
        ).fetchall()
        compliance = conn.execute(
            """
            SELECT vendor_name, expiry_date, risk_level, source_bbox, source_verbatim_span
            FROM compliance_record_history WHERE run_id = ? AND doc_id = ?
            """,
            ("run-legacy", "doc-legacy"),
        ).fetchone()
        child_rows = conn.execute(
            """
            SELECT run_id, doc_id, status, attempt_count, trace_id
            FROM extraction_run_documents
            """
        ).fetchall()
        parent = conn.execute(
            """
            SELECT status, document_count, field_count, expected_document_count,
                   attempted_document_count, succeeded_document_count, failed_document_count
            FROM extraction_runs WHERE run_id = ?
            """,
            ("run-legacy",),
        ).fetchone()
        empty_parent = conn.execute(
            """
            SELECT status, expected_document_count, attempted_document_count,
                   succeeded_document_count, failed_document_count, completed_at
            FROM extraction_runs WHERE run_id = ?
            """,
            ("run-empty",),
        ).fetchone()
        usage = conn.execute(
            """
            SELECT model, input_tokens, output_tokens, total_tokens,
                   requested_model, resolved_model, pricing_model, thought_tokens
            FROM extraction_usage_observations
            """
        ).fetchone()
        foreign_key_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()

    assert len(fields) == 6
    assert ("vendor_name", "Legacy Vendor", 0, '{"x":2}', "Legacy Vendor") in fields
    assert compliance == ("Legacy Vendor", "2027-01-01", "green", '{"x":1}', "Certificate")
    assert child_rows == [("run-legacy", "doc-legacy", "completed", 1, "trace-legacy")]
    assert parent == ("completed", 1, 6, 1, 1, 1, 0)
    assert empty_parent == ("running", 0, 0, 0, 0, None)
    assert usage == ("gemini-2.5-flash", 100, 20, 120, None, None, None, None)
    assert foreign_key_violations == []


def test_run_document_foreign_keys_reject_orphans_and_cascade(tmp_db_path: str) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)
    conn = _connect_with_foreign_keys(tmp_db_path)
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, file_path, page_count) VALUES (?, ?, ?, ?)",
            ("doc-1", "doc.pdf", "bounded-path", 1),
        )
        conn.execute(
            "INSERT INTO extraction_runs (run_id, status) VALUES (?, ?)",
            ("run-1", "running"),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO extraction_run_documents (run_id, doc_id) VALUES (?, ?)",
                ("missing-run", "doc-1"),
            )
        conn.rollback()

        conn.execute(
            "INSERT INTO extraction_run_documents (run_id, doc_id) VALUES (?, ?)",
            ("run-1", "doc-1"),
        )
        conn.execute("DELETE FROM documents WHERE doc_id = ?", ("doc-1",))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM extraction_run_documents").fetchone()[0] == 0
    finally:
        conn.close()


def test_lifecycle_schema_rejects_negative_counts_and_unknown_child_status(tmp_db_path: str) -> None:
    from src.db.schema import init_db  # noqa: PLC0415

    init_db(tmp_db_path)
    conn = _connect_with_foreign_keys(tmp_db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO extraction_runs (run_id, status, expected_document_count) VALUES (?, ?, ?)",
                ("run-negative", "running", -1),
            )
        conn.rollback()
        conn.execute(
            "INSERT INTO documents (doc_id, filename, file_path, page_count) VALUES (?, ?, ?, ?)",
            ("doc-1", "doc.pdf", "bounded-path", 1),
        )
        conn.execute("INSERT INTO extraction_runs (run_id, status) VALUES (?, ?)", ("run-1", "running"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO extraction_run_documents (run_id, doc_id, status, attempt_count)
                VALUES (?, ?, ?, ?)
                """,
                ("run-1", "doc-1", "unknown", 0),
            )
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
