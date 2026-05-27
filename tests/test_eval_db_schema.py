import sqlite3
from pathlib import Path

from src.db.schema import init_db


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
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
    assert "rag_eval_observations" in tables
    assert "gold_extraction_labels" in tables
    assert "gold_retrieval_queries" in tables
    assert "gold_retrieval_targets" in tables


def test_rag_eval_observations_schema_is_bounded_and_indexed(tmp_path: Path) -> None:
    db_path = str(tmp_path / "eval_schema.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = _column_names(conn, "rag_eval_observations")
        indexes = _index_names(conn)
    finally:
        conn.close()

    assert {
        "observation_id",
        "source_run_id",
        "query_id",
        "status",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cost_usd",
        "faithfulness",
        "answer_relevancy",
        "cited_doc_id",
        "cited_page_num",
        "created_at",
    } <= columns
    assert "idx_rag_eval_obs_source_run_id" in indexes
    assert "idx_rag_eval_obs_query_id" in indexes

    forbidden_fragments = (
        "prompt",
        "answer_text",
        "raw_answer",
        "context",
        "snippet",
        "page_text",
        "provider_payload",
        "payload",
        "image",
        "blob",
        "docling_json",
    )
    assert not any(
        forbidden in column
        for column in columns
        for forbidden in forbidden_fragments
    )


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
    assert "rag_eval_observations" in tables
    assert "gold_extraction_labels" in tables
    assert "gold_retrieval_queries" in tables
    assert "gold_retrieval_targets" in tables
