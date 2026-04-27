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

CREATE TABLE IF NOT EXISTS evaluations (
    eval_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    pipeline_label TEXT NOT NULL,
    metric_name    TEXT NOT NULL,
    metric_value   REAL,
    doc_id         TEXT,
    created_at     TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_pages_doc_id       ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_extractions_doc_id  ON extractions(doc_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_run_id  ON evaluations(run_id);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with FK enforcement always enabled (Pitfall 4)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    """Create all tables and indexes if they do not already exist."""
    conn = _connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()