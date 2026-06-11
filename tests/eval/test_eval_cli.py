"""Tests for the offline-safe retrieval eval CLI (``eval run``)."""
from __future__ import annotations

import sqlite3
import sys

from typer.testing import CliRunner

from src.db.schema import init_db
from src.eval.cli import app

runner = CliRunner()


def _seed_indexed_corpus(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, file_path, page_count, status) VALUES (?, ?, ?, ?, ?)",
            ("d1", "doc1.pdf", "/tmp/doc1.pdf", 1, "ingested"),
        )
        conn.execute("INSERT INTO pages (doc_id, page_num, page_text) VALUES (?, ?, ?)", ("d1", 0, "alpha beta"))
        conn.execute("INSERT INTO gold_retrieval_queries (query_id, query_text) VALUES (?, ?)", ("q1", "alpha"))
        conn.execute(
            "INSERT INTO gold_retrieval_targets (query_id, doc_id, page_num) VALUES (?, ?, ?)",
            ("q1", "d1", 0),
        )
        conn.commit()
    finally:
        conn.close()


def test_cli_import_is_offline() -> None:
    assert "ragas" not in sys.modules
    assert not any(name.startswith("langchain_google_genai") for name in sys.modules)


def test_run_missing_db_reports_bounded_error(tmp_path) -> None:
    result = runner.invoke(app, ["run", "--db-path", str(tmp_path / "nope.db")])
    assert result.exit_code == 2
    assert "status=error" in result.output
    assert "reason=db_missing" in result.output


def test_run_without_ragas_completes_and_echoes_bounded_status(tmp_path) -> None:
    from src.retrieval.indexer import build_retrieval_index

    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_indexed_corpus(db_path)
    build_retrieval_index(db_path)

    result = runner.invoke(app, ["run", "--db-path", db_path])

    assert result.exit_code == 0
    assert "status=complete" in result.output
    assert "with_ragas=false" in result.output
    # No query text / answers / snippets / secrets in bounded echo.
    assert "alpha" not in result.output


def test_run_with_ragas_degrades_gracefully_without_key(tmp_path, monkeypatch) -> None:
    """--with-ragas must not crash when no API key / ragas is available.

    The runner degrades gracefully: core metrics persist, the run completes, and
    the CLI echoes a bounded complete status.
    """
    from src.retrieval.indexer import build_retrieval_index

    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_indexed_corpus(db_path)
    build_retrieval_index(db_path)

    # Force the no-key path regardless of local .env.
    monkeypatch.setattr("src.config.get_settings", lambda: type("S", (), {"gemini_api_key": ""})())

    result = runner.invoke(app, ["run", "--db-path", db_path, "--with-ragas"])

    assert result.exit_code == 0
    assert "status=complete" in result.output
    assert "with_ragas=true" in result.output
