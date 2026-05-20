"""Tests for the provider-free retrieval index CLI."""
from __future__ import annotations

import sqlite3

from typer.testing import CliRunner

from src.db.queries import insert_document, insert_page, mark_document_ingested
from src.db.schema import init_db
from src.retrieval.cli import app

runner = CliRunner()


def _seed_doc(
    db_path: str,
    *,
    doc_id: str = "doc-1",
    filename: str = "sdf.pdf",
    pages: tuple[str | None, ...] = ("Certificate page zero", "Supplier page one"),
) -> None:
    insert_document(db_path, doc_id, filename, f"/tmp/{filename}", len(pages), docling_json=None)
    mark_document_ingested(db_path, doc_id)
    for page_num, text in enumerate(pages):
        insert_page(db_path, doc_id, page_num, text, image_blob=b"image bytes that must not appear")


def test_status_before_build_reports_missing_index_without_raw_text(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, pages=("Sensitive supplier text",))

    result = runner.invoke(app, ["status", "--db-path", tmp_db_path])

    assert result.exit_code == 1
    assert "status=missing" in result.output
    assert "run_id=none" in result.output
    assert "indexed_docs=1" in result.output
    assert "indexed_pages=0" in result.output
    assert "source_pages=1" in result.output
    assert "stale=false" in result.output
    assert "reason=index_missing" in result.output
    assert "Sensitive supplier text" not in result.output
    assert "image bytes" not in result.output


def test_build_success_outputs_safe_metadata_and_status_passes(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, pages=("Certificate page zero", "Supplier page one"))

    build = runner.invoke(app, ["build", "--db-path", tmp_db_path])
    status = runner.invoke(app, ["status", "--db-path", tmp_db_path])

    assert build.exit_code == 0
    assert "status=built" in build.output
    assert "run_id=retrieval-built-" in build.output
    assert "indexed_docs=1" in build.output
    assert "indexed_pages=2" in build.output
    assert "source_pages=2" in build.output
    assert "content_hash=" in build.output
    assert "stale=false" in build.output
    assert "reason=none" in build.output
    assert "Certificate page zero" not in build.output
    assert status.exit_code == 0
    assert "status=built" in status.output
    assert "reason=none" in status.output


def test_empty_corpus_build_and_status_return_nonzero_with_reason(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path, pages=("   ", None))

    build = runner.invoke(app, ["build", "--db-path", tmp_db_path])
    status = runner.invoke(app, ["status", "--db-path", tmp_db_path])

    assert build.exit_code == 1
    assert "status=empty" in build.output
    assert "indexed_docs=0" in build.output
    assert "indexed_pages=0" in build.output
    assert "reason=corpus_empty" in build.output
    assert status.exit_code == 1
    assert "status=empty" in status.output
    assert "reason=corpus_empty" in status.output


def test_status_reports_stale_after_source_page_changes(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    _seed_doc(tmp_db_path)
    build = runner.invoke(app, ["build", "--db-path", tmp_db_path])
    assert build.exit_code == 0

    insert_page(tmp_db_path, "doc-1", 1, "Changed supplier page text", image_blob=b"changed image")
    status = runner.invoke(app, ["status", "--db-path", tmp_db_path])

    assert status.exit_code == 1
    assert "status=stale" in status.output
    assert "run_id=retrieval-built-" in status.output
    assert "indexed_docs=1" in status.output
    assert "indexed_pages=2" in status.output
    assert "stale=true" in status.output
    assert "reason=corpus_stale" in status.output
    assert "Changed supplier page text" not in status.output


def test_missing_database_and_missing_schema_report_safe_errors(tmp_db_path: str, tmp_path) -> None:
    missing_result = runner.invoke(app, ["status", "--db-path", str(tmp_path / "missing.db")])
    assert missing_result.exit_code == 2
    assert "status=error" in missing_result.output
    assert "reason=db_missing" in missing_result.output

    sqlite3.connect(tmp_db_path).close()
    schema_result = runner.invoke(app, ["build", "--db-path", tmp_db_path])
    assert schema_result.exit_code == 2
    assert "status=error" in schema_result.output
    assert "reason=schema_missing" in schema_result.output


def test_sql_like_filename_and_page_text_are_not_echoed_unsanitized(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    malicious_filename = "sdf'); DROP TABLE retrieval_index_runs; --.pdf"
    malicious_text = "alpha'); DROP TABLE documents; -- beta"
    _seed_doc(tmp_db_path, filename=malicious_filename, pages=(malicious_text,))

    build = runner.invoke(app, ["build", "--db-path", tmp_db_path])
    status = runner.invoke(app, ["status", "--db-path", tmp_db_path])

    assert build.exit_code == 0
    assert status.exit_code == 0
    for output in (build.output, status.output):
        assert malicious_filename not in output
        assert malicious_text not in output
        assert "DROP TABLE" not in output
        assert "status=built" in output
        assert "reason=none" in output
