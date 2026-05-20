"""SQLite schema for the Pfizer SDF compliance database.

D-01: Three separate tables with FK relationships.
D-02: image_blob BLOB column stores 150 DPI PNGs directly in SQLite.
"""
from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    page_count   INTEGER NOT NULL,
    ingested_at  TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    docling_json TEXT,
    status       TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS pages (
    page_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    page_num   INTEGER NOT NULL,
    page_text  TEXT,
    image_blob BLOB,
    UNIQUE (doc_id, page_num)
);

CREATE TABLE IF NOT EXISTS extractions (
    extraction_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id            TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    field_name        TEXT NOT NULL,
    field_value       TEXT,
    confidence        REAL,
    source_page       INTEGER,
    source_bbox       TEXT,
    verbatim_span     TEXT,
    trace_id          TEXT,
    created_at        TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    needs_review      BOOLEAN DEFAULT 0,
    review_state      TEXT,
    abstention_reason TEXT,
    normalized_value  TEXT,
    updated_at        TIMESTAMP,
    UNIQUE (doc_id, field_name)
);

CREATE TABLE IF NOT EXISTS compliance_records (
    doc_id                  TEXT PRIMARY KEY REFERENCES documents(doc_id) ON DELETE CASCADE,
    doc_type                TEXT,
    vendor_name             TEXT,
    manufacturing_date      TEXT,
    effective_date          TEXT,
    revision_date           TEXT,
    expiry_date             TEXT,
    aggregate_confidence    REAL,
    review_state            TEXT,
    needs_review            BOOLEAN DEFAULT 0,
    trace_id                TEXT,
    run_id                  TEXT,
    extracted_at            TIMESTAMP,
    created_at              TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at              TIMESTAMP,
    risk_level              TEXT,
    risk_reason             TEXT,
    compliance_status       TEXT,
    age_days                INTEGER,
    source_page             INTEGER,
    source_bbox             TEXT,
    source_verbatim_span    TEXT
);

CREATE TABLE IF NOT EXISTS evaluations (
    eval_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    pipeline_label TEXT NOT NULL,
    metric_name    TEXT NOT NULL,
    metric_value   REAL,
    doc_id         TEXT,
    created_at     TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS retrieval_index_runs (
    run_id                  TEXT PRIMARY KEY,
    status                  TEXT NOT NULL,
    built_at                TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source_document_count   INTEGER NOT NULL DEFAULT 0,
    source_page_count       INTEGER NOT NULL DEFAULT 0,
    indexed_page_count      INTEGER NOT NULL DEFAULT 0,
    content_hash            TEXT,
    previous_content_hash   TEXT,
    is_stale                BOOLEAN NOT NULL DEFAULT 0,
    stale_reason            TEXT,
    error_reason            TEXT
);

CREATE TABLE IF NOT EXISTS retrieval_index_pages (
    doc_id             TEXT NOT NULL,
    page_num           INTEGER NOT NULL,
    display_page_num   INTEGER NOT NULL,
    filename           TEXT NOT NULL,
    text_sha256        TEXT NOT NULL,
    text_length        INTEGER NOT NULL,
    snippet            TEXT NOT NULL DEFAULT '',
    run_id             TEXT NOT NULL REFERENCES retrieval_index_runs(run_id) ON DELETE CASCADE,
    indexed_at         TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (doc_id, page_num),
    FOREIGN KEY (doc_id, page_num) REFERENCES pages(doc_id, page_num) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pages_doc_id                 ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_extractions_doc_id           ON extractions(doc_id);
CREATE INDEX IF NOT EXISTS idx_extractions_trace_id         ON extractions(trace_id);
CREATE INDEX IF NOT EXISTS idx_compliance_review_state      ON compliance_records(review_state);
CREATE INDEX IF NOT EXISTS idx_compliance_needs_review      ON compliance_records(needs_review);
CREATE INDEX IF NOT EXISTS idx_compliance_risk_level        ON compliance_records(risk_level);
CREATE INDEX IF NOT EXISTS idx_compliance_vendor_name       ON compliance_records(vendor_name);
CREATE INDEX IF NOT EXISTS idx_compliance_expiry_date       ON compliance_records(expiry_date);
CREATE INDEX IF NOT EXISTS idx_compliance_trace_id          ON compliance_records(trace_id);
CREATE INDEX IF NOT EXISTS idx_compliance_run_id            ON compliance_records(run_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_run_id           ON evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_runs_built_at      ON retrieval_index_runs(built_at);
CREATE INDEX IF NOT EXISTS idx_retrieval_runs_status        ON retrieval_index_runs(status);
CREATE INDEX IF NOT EXISTS idx_retrieval_pages_run_id       ON retrieval_index_pages(run_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_pages_filename     ON retrieval_index_pages(filename);
"""

RETRIEVAL_INDEX_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_index_page_fts
USING fts5(doc_id UNINDEXED, page_num UNINDEXED, page_text);
"""

_EXTRACTION_MIGRATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("review_state", "TEXT"),
    ("abstention_reason", "TEXT"),
    ("normalized_value", "TEXT"),
    ("updated_at", "TIMESTAMP"),
)

POST_MIGRATION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_extractions_review_state ON extractions(review_state);
CREATE INDEX IF NOT EXISTS idx_extractions_needs_review ON extractions(needs_review);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with FK enforcement always enabled (Pitfall 4)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    """Create all tables and indexes, then migrate legacy Phase 1 extraction tables."""
    conn = _connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate_extractions_table(conn)
        _migrate_retrieval_index_pages_table(conn)
        _init_retrieval_index_fts(conn)
        conn.executescript(POST_MIGRATION_INDEX_SQL)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_retrieval_index_fts(conn: sqlite3.Connection) -> None:
    """Create the optional FTS5 page-text index when SQLite supports FTS5.

    Some minimal SQLite builds omit FTS5. Retrieval repository methods check for
    the virtual table before touching it, so schema initialization remains
    offline-safe and idempotent even on those builds.
    """

    try:
        conn.executescript(RETRIEVAL_INDEX_FTS_SQL)
    except sqlite3.OperationalError as exc:
        if "fts5" not in str(exc).lower():
            raise


def _migrate_extractions_table(conn: sqlite3.Connection) -> None:
    """Add nullable Phase 2 extraction columns to pre-existing Phase 1 databases.

    SQLite's ``CREATE TABLE IF NOT EXISTS`` does not modify existing tables. This
    helper inspects the table shape and applies idempotent ``ALTER TABLE``
    statements only for missing nullable columns.
    """

    existing_columns = _table_columns(conn, "extractions")
    if not existing_columns:
        return

    for column_name, column_type in _EXTRACTION_MIGRATION_COLUMNS:
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE extractions ADD COLUMN {column_name} {column_type}")
            existing_columns.add(column_name)


def _migrate_retrieval_index_pages_table(conn: sqlite3.Connection) -> None:
    """Add nullable-safe retrieval index columns to pre-existing local databases."""

    existing_columns = _table_columns(conn, "retrieval_index_pages")
    if not existing_columns:
        return

    if "snippet" not in existing_columns:
        conn.execute("ALTER TABLE retrieval_index_pages ADD COLUMN snippet TEXT NOT NULL DEFAULT ''")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return column names for a SQLite table from PRAGMA table_info."""

    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
