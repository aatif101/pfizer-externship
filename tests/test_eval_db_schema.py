import sqlite3
from pathlib import Path

from src.db.schema import init_db


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def test_init_db_idempotent(tmp_path: Path) -> None:
    db_path = str(tmp_path / "eval_schema.sqlite")

    init_db(db_path)
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        tables = _table_names(conn)
    finally:
        conn.close()

    assert "eval_runs" in tables
    assert "eval_metrics" in tables
    assert "gold_extraction_labels" in tables
    assert "gold_retrieval_queries" in tables
    assert "gold_retrieval_targets" in tables


def test_init_db_upgrades_older_schema(tmp_path: Path) -> None:
    db_path = str(tmp_path / "older.sqlite")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        # Minimal legacy schema: init_db should extend this with eval-focused tables.
        conn.executescript(
            """
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                page_count INTEGER NOT NULL
            );

            CREATE TABLE pages (
                page_id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                page_num INTEGER NOT NULL,
                UNIQUE(doc_id, page_num)
            );

            CREATE TABLE extractions (
                extraction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                field_name TEXT NOT NULL,
                field_value TEXT,
                confidence REAL,
                source_page INTEGER,
                source_bbox TEXT,
                verbatim_span TEXT,
                trace_id TEXT,
                created_at TIMESTAMP,
                needs_review BOOLEAN DEFAULT 0,
                UNIQUE(doc_id, field_name)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        tables = _table_names(conn)
    finally:
        conn.close()

    assert "eval_runs" in tables
    assert "eval_metrics" in tables
    assert "gold_extraction_labels" in tables
    assert "gold_retrieval_queries" in tables
    assert "gold_retrieval_targets" in tables
