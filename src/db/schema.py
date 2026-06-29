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

CREATE TABLE IF NOT EXISTS page_ocr_texts (
    doc_id             TEXT NOT NULL,
    page_num           INTEGER NOT NULL,
    source             TEXT NOT NULL,
    generated_text     TEXT NOT NULL,
    text_sha256        TEXT NOT NULL,
    page_image_sha256  TEXT NOT NULL,
    created_at         TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at         TIMESTAMP,
    PRIMARY KEY (doc_id, page_num, source),
    FOREIGN KEY (doc_id, page_num) REFERENCES pages(doc_id, page_num) ON DELETE CASCADE
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
    evidence_type     TEXT,
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
    source_verbatim_span    TEXT,
    source_evidence_type    TEXT
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    run_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    document_count  INTEGER NOT NULL DEFAULT 0,
    field_count     INTEGER NOT NULL DEFAULT 0,
    trace_id         TEXT,
    started_at       TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at     TIMESTAMP,
    created_at       TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extraction_history (
    history_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
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
    evidence_type     TEXT,
    extracted_at      TIMESTAMP,
    updated_at        TIMESTAMP,
    UNIQUE (run_id, doc_id, field_name)
);

CREATE TABLE IF NOT EXISTS compliance_record_history (
    history_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                  TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
    doc_id                  TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
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
    extracted_at            TIMESTAMP,
    created_at              TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at              TIMESTAMP,
    risk_level              TEXT,
    risk_reason             TEXT,
    compliance_status       TEXT,
    age_days                INTEGER,
    source_page             INTEGER,
    source_bbox             TEXT,
    source_verbatim_span    TEXT,
    source_evidence_type    TEXT,
    UNIQUE (run_id, doc_id)
);

-- LEGACY: Phase 1 evaluation surface (per-metric rows without run grouping).
-- Keep for backward compatibility; new evaluation code should use eval_runs + eval_metrics.
CREATE TABLE IF NOT EXISTS evaluations (
    eval_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    pipeline_label TEXT NOT NULL,
    metric_name    TEXT NOT NULL,
    metric_value   REAL,
    doc_id         TEXT,
    created_at     TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id         TEXT PRIMARY KEY,
    eval_type      TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_at     TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at   TIMESTAMP,
    pipeline_label TEXT,
    params_json    TEXT,
    error_reason   TEXT
);

CREATE TABLE IF NOT EXISTS eval_metrics (
    metric_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES eval_runs(run_id) ON DELETE CASCADE,
    metric_name   TEXT NOT NULL,
    metric_value  REAL,
    scope_type    TEXT,
    scope_id      TEXT,
    created_at    TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS rag_eval_observations (
    observation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_run_id    TEXT,
    query_id         TEXT,
    status           TEXT NOT NULL,
    latency_ms       REAL,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    total_tokens     INTEGER,
    cost_usd         REAL,
    faithfulness     REAL,
    answer_relevancy REAL,
    cited_doc_id     TEXT,
    cited_page_num   INTEGER,
    created_at       TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS extraction_usage_observations (
    observation_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
    doc_id              TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    stage               TEXT NOT NULL,
    provider            TEXT,
    model               TEXT,
    status              TEXT NOT NULL,
    latency_ms          REAL,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    total_tokens        INTEGER,
    estimated_cost_usd  REAL,
    trace_id            TEXT,
    error_reason        TEXT,
    created_at          TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS gold_extraction_labels (
    doc_id           TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    field_name       TEXT NOT NULL,
    expected_value   TEXT NOT NULL,
    normalized_value TEXT,
    source_page      INTEGER,
    created_at       TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (doc_id, field_name)
);

CREATE TABLE IF NOT EXISTS gold_retrieval_queries (
    query_id    TEXT PRIMARY KEY,
    query_text  TEXT NOT NULL,
    notes       TEXT,
    created_at  TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS gold_retrieval_targets (
    query_id    TEXT NOT NULL REFERENCES gold_retrieval_queries(query_id) ON DELETE CASCADE,
    doc_id      TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    page_num    INTEGER NOT NULL,
    created_at  TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (query_id, doc_id, page_num),
    FOREIGN KEY (doc_id, page_num) REFERENCES pages(doc_id, page_num) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS visual_index_runs (
    run_id                  TEXT PRIMARY KEY,
    status                  TEXT NOT NULL,
    built_at                TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source_document_count   INTEGER NOT NULL DEFAULT 0,
    source_page_count       INTEGER NOT NULL DEFAULT 0,
    indexed_page_count      INTEGER NOT NULL DEFAULT 0,
    content_hash            TEXT,
    previous_content_hash   TEXT,
    model_version           TEXT NOT NULL DEFAULT '',
    collection_name         TEXT NOT NULL DEFAULT '',
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
    text_source        TEXT NOT NULL DEFAULT 'original',
    has_ocr_text       BOOLEAN NOT NULL DEFAULT 0,
    ocr_text_sha256    TEXT,
    run_id             TEXT NOT NULL REFERENCES retrieval_index_runs(run_id) ON DELETE CASCADE,
    indexed_at         TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (doc_id, page_num),
    FOREIGN KEY (doc_id, page_num) REFERENCES pages(doc_id, page_num) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pages_doc_id                 ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_page_ocr_texts_source        ON page_ocr_texts(source);
CREATE INDEX IF NOT EXISTS idx_page_ocr_texts_updated       ON page_ocr_texts(updated_at);
CREATE INDEX IF NOT EXISTS idx_extractions_doc_id           ON extractions(doc_id);
CREATE INDEX IF NOT EXISTS idx_extractions_trace_id         ON extractions(trace_id);
CREATE INDEX IF NOT EXISTS idx_compliance_review_state      ON compliance_records(review_state);
CREATE INDEX IF NOT EXISTS idx_compliance_needs_review      ON compliance_records(needs_review);
CREATE INDEX IF NOT EXISTS idx_compliance_risk_level        ON compliance_records(risk_level);
CREATE INDEX IF NOT EXISTS idx_compliance_vendor_name       ON compliance_records(vendor_name);
CREATE INDEX IF NOT EXISTS idx_compliance_expiry_date       ON compliance_records(expiry_date);
CREATE INDEX IF NOT EXISTS idx_compliance_trace_id          ON compliance_records(trace_id);
CREATE INDEX IF NOT EXISTS idx_compliance_run_id            ON compliance_records(run_id);
CREATE INDEX IF NOT EXISTS idx_extraction_runs_started_at   ON extraction_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_extraction_runs_created_at   ON extraction_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_extraction_runs_status       ON extraction_runs(status);
CREATE INDEX IF NOT EXISTS idx_extraction_history_run_id    ON extraction_history(run_id);
CREATE INDEX IF NOT EXISTS idx_extraction_history_doc_id    ON extraction_history(doc_id);
CREATE INDEX IF NOT EXISTS idx_extraction_history_run_doc   ON extraction_history(run_id, doc_id);
CREATE INDEX IF NOT EXISTS idx_extraction_history_trace_id  ON extraction_history(trace_id);
CREATE INDEX IF NOT EXISTS idx_compliance_history_run_id    ON compliance_record_history(run_id);
CREATE INDEX IF NOT EXISTS idx_compliance_history_doc_id    ON compliance_record_history(doc_id);
CREATE INDEX IF NOT EXISTS idx_compliance_history_run_doc   ON compliance_record_history(run_id, doc_id);
CREATE INDEX IF NOT EXISTS idx_compliance_history_trace_id  ON compliance_record_history(trace_id);
CREATE INDEX IF NOT EXISTS idx_compliance_history_risk      ON compliance_record_history(risk_level);
CREATE INDEX IF NOT EXISTS idx_compliance_history_review    ON compliance_record_history(review_state);
CREATE INDEX IF NOT EXISTS idx_evaluations_run_id           ON evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_status              ON eval_runs(status);
CREATE INDEX IF NOT EXISTS idx_eval_runs_created_at          ON eval_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_eval_metrics_run_id           ON eval_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_metrics_metric_name      ON eval_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_rag_eval_obs_source_run_id    ON rag_eval_observations(source_run_id);
CREATE INDEX IF NOT EXISTS idx_rag_eval_obs_query_id         ON rag_eval_observations(query_id);
CREATE INDEX IF NOT EXISTS idx_extraction_usage_run_id       ON extraction_usage_observations(run_id);
CREATE INDEX IF NOT EXISTS idx_extraction_usage_doc_id       ON extraction_usage_observations(doc_id);
CREATE INDEX IF NOT EXISTS idx_extraction_usage_stage        ON extraction_usage_observations(stage);
CREATE INDEX IF NOT EXISTS idx_extraction_usage_status       ON extraction_usage_observations(status);
CREATE INDEX IF NOT EXISTS idx_extraction_usage_run_doc_stage ON extraction_usage_observations(run_id, doc_id, stage);
CREATE INDEX IF NOT EXISTS idx_gold_extraction_doc_id        ON gold_extraction_labels(doc_id);
CREATE INDEX IF NOT EXISTS idx_gold_retrieval_query_text     ON gold_retrieval_queries(query_text);
CREATE INDEX IF NOT EXISTS idx_visual_runs_built_at         ON visual_index_runs(built_at);
CREATE INDEX IF NOT EXISTS idx_visual_runs_status           ON visual_index_runs(status);
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
    ("evidence_type", "TEXT"),
    ("updated_at", "TIMESTAMP"),
)

# Additive evidence_type columns (D027). NULL-at-rest is treated as "text" on read.
_EVIDENCE_TYPE_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("extractions", "evidence_type", "TEXT"),
    ("extraction_history", "evidence_type", "TEXT"),
    ("compliance_records", "source_evidence_type", "TEXT"),
    ("compliance_record_history", "source_evidence_type", "TEXT"),
)

POST_MIGRATION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_extractions_review_state ON extractions(review_state);
CREATE INDEX IF NOT EXISTS idx_extractions_needs_review ON extractions(needs_review);
CREATE INDEX IF NOT EXISTS idx_retrieval_pages_text_source ON retrieval_index_pages(text_source);
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
        _migrate_evidence_type_columns(conn)
        _migrate_retrieval_index_pages_table(conn)
        _migrate_visual_index_runs_table(conn)
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


def _migrate_evidence_type_columns(conn: sqlite3.Connection) -> None:
    """Add additive evidence_type columns to pre-existing databases (D027).

    Idempotent: each ``ALTER TABLE ... ADD COLUMN`` runs only when the target
    table exists and the column is missing. Pre-existing rows keep NULL, which
    the read path coalesces to "text".
    """

    for table_name, column_name, column_type in _EVIDENCE_TYPE_MIGRATIONS:
        existing_columns = _table_columns(conn, table_name)
        if not existing_columns:
            continue
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _migrate_retrieval_index_pages_table(conn: sqlite3.Connection) -> None:
    """Add nullable-safe retrieval index columns to pre-existing local databases."""

    existing_columns = _table_columns(conn, "retrieval_index_pages")
    if not existing_columns:
        return

    migrations = (
        ("snippet", "TEXT NOT NULL DEFAULT ''"),
        ("text_source", "TEXT NOT NULL DEFAULT 'original'"),
        ("has_ocr_text", "BOOLEAN NOT NULL DEFAULT 0"),
        ("ocr_text_sha256", "TEXT"),
    )
    for column_name, column_def in migrations:
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE retrieval_index_pages ADD COLUMN {column_name} {column_def}")
            existing_columns.add(column_name)


_VISUAL_INDEX_RUNS_MIGRATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("model_version", "TEXT NOT NULL DEFAULT ''"),
    ("collection_name", "TEXT NOT NULL DEFAULT ''"),
)


def _migrate_visual_index_runs_table(conn: sqlite3.Connection) -> None:
    """Add additive visual-run columns to pre-existing local databases.

    Idempotent: ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so
    a database created before ``model_version`` / ``collection_name`` existed gets
    the columns via guarded ``ALTER TABLE``. Each ALTER runs only when the table
    exists and the column is missing (mirrors ``_migrate_retrieval_index_pages_table``).
    """

    existing_columns = _table_columns(conn, "visual_index_runs")
    if not existing_columns:
        return

    for column_name, column_def in _VISUAL_INDEX_RUNS_MIGRATION_COLUMNS:
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE visual_index_runs ADD COLUMN {column_name} {column_def}")
            existing_columns.add(column_name)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return column names for a SQLite table from PRAGMA table_info."""

    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
