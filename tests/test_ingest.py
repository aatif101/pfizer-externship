"""Integration tests for src/pipeline/ingest.py — INGEST-01."""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest
from loguru import logger
from typer.testing import CliRunner


class _FakeDoclingDocument:
    pages = [object(), object()]
    texts: list[object] = []

    def export_to_markdown(self) -> str:
        return "Safe extracted page text used only for DB persistence."

    def export_to_json(self) -> str:
        return '{"raw_docling_json": "SHOULD_NOT_ENTER_TRACE"}'


class _FakeConversionResult:
    document = _FakeDoclingDocument()


class _OnePageDoclingDocument:
    pages = [object()]
    texts: list[object] = []

    def export_to_markdown(self) -> str:
        return "PRIVATE PAGE TEXT SENTINEL"

    def export_to_json(self) -> str:
        return '{"provider": "PRIVATE PROVIDER SENTINEL"}'


class _OnePageConversionResult:
    document = _OnePageDoclingDocument()


def _install_lightweight_pipeline(monkeypatch, ingest_module):
    calls = {"convert": 0, "rasterize": 0}

    def _convert(_path: str):
        calls["convert"] += 1
        return _OnePageConversionResult()

    def _rasterize(_path: str):
        calls["rasterize"] += 1
        return [b"PNG-ONE"]

    monkeypatch.setattr(ingest_module, "convert_pdf", _convert)
    monkeypatch.setattr(ingest_module, "rasterize_pages", _rasterize)
    return calls


def _forbidden_trace_payload_absent(updates: list[dict]) -> None:
    forbidden = {
        "file_path",
        "page_text",
        "image_blob",
        "docling_json",
        "content_hash",
        "SHOULD_NOT_ENTER_TRACE",
        "Safe extracted page text",
        "absolute-secret-source",
    }
    for update in updates:
        metadata = update.get("metadata") or {}
        if not forbidden.isdisjoint(metadata):
            pytest.fail("forbidden key detected in trace metadata")
        metadata_repr = repr(metadata)
        if any(value in metadata_repr for value in forbidden):
            pytest.fail("forbidden payload detected in trace metadata")


def test_ingest_single_pdf(tmp_db_path: str, sample_pdf_path: str) -> None:
    """INGEST-01: ingest_document must write rows to documents and pages tables."""
    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline.ingest import ingest_document  # noqa: PLC0415
    import sqlite3

    init_db(tmp_db_path)
    result = ingest_document(pdf_path=sample_pdf_path, db_path=tmp_db_path)

    assert result["page_count"] >= 1, "Expected at least 1 page"
    assert "doc_id" in result

    conn = sqlite3.connect(tmp_db_path)
    doc_row = conn.execute(
        "SELECT doc_id, page_count, status FROM documents WHERE doc_id=?",
        (result["doc_id"],),
    ).fetchone()
    page_rows = conn.execute(
        "SELECT page_num FROM pages WHERE doc_id=?", (result["doc_id"],)
    ).fetchall()
    conn.close()

    assert doc_row is not None, "Document not found in DB"
    assert doc_row[2] == "ingested", f"Expected status='ingested', got {doc_row[2]!r}"
    assert len(page_rows) >= 1, "No page rows written"


def test_path_traversal_rejected(tmp_db_path: str) -> None:
    """Security T-1-01: ingest_document must reject paths with traversal components."""
    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline.ingest import ingest_document  # noqa: PLC0415

    init_db(tmp_db_path)
    with pytest.raises((ValueError, PermissionError, FileNotFoundError)):
        ingest_document(pdf_path="../../etc/passwd", db_path=tmp_db_path)


def test_oversized_pdf_rejected(tmp_db_path: str, tmp_path) -> None:
    """Security T-1-03 / D-05: Files exceeding MAX_PDF_MB must be rejected before Docling."""
    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline.ingest import ingest_document  # noqa: PLC0415
    from unittest.mock import patch

    init_db(tmp_db_path)

    # Create a fake PDF file with reported size over 100 MB
    fake_pdf = tmp_path / "huge.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_size = 200 * 1024 * 1024  # 200 MB
        with pytest.raises(ValueError, match="exceeds"):
            ingest_document(pdf_path=str(fake_pdf), db_path=tmp_db_path)


def test_storage_trace_update_failure_does_not_change_db_write(monkeypatch, tmp_db_path: str) -> None:
    """Storage trace failures must be no-op safe for empty page text."""
    import sqlite3

    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline import db_writer  # noqa: PLC0415

    init_db(tmp_db_path)
    trace_calls: list[dict] = []

    def _record_failed_trace(**kwargs) -> bool:
        trace_calls.append(kwargs)
        return False

    monkeypatch.setattr(db_writer, "safe_update_current_trace", _record_failed_trace)

    db_writer.write_document_to_db(
        db_path=tmp_db_path,
        doc_id="doc-storage-safe",
        filename="storage.pdf",
        file_path="C:/absolute-secret-source/storage.pdf",
        page_count=2,
        docling_json='{"docling_json": "SHOULD_NOT_ENTER_TRACE"}',
        page_texts={0: "", 1: "Second page text should persist but not trace."},
        png_blobs=[b"PNG-ONE", b"PNG-TWO"],
    )

    conn = sqlite3.connect(tmp_db_path)
    try:
        doc_row = conn.execute(
            "SELECT status, page_count FROM documents WHERE doc_id=?",
            ("doc-storage-safe",),
        ).fetchone()
        page_rows = conn.execute(
            "SELECT page_num, page_text, image_blob FROM pages WHERE doc_id=? ORDER BY page_num",
            ("doc-storage-safe",),
        ).fetchall()
    finally:
        conn.close()

    assert doc_row == ("ingested", 2)
    assert page_rows == [
        (0, "", b"PNG-ONE"),
        (1, "Second page text should persist but not trace.", b"PNG-TWO"),
    ]
    assert [call["metadata"]["status"] for call in trace_calls] == ["started", "completed"]
    for call in trace_calls:
        assert call["allowed_metadata_keys"] == db_writer._STORAGE_TRACE_METADATA_KEYS
    _forbidden_trace_payload_absent(trace_calls)


def test_ingest_trace_metadata_is_allowlisted_on_lightweight_success(monkeypatch, tmp_db_path: str, tmp_path) -> None:
    """Ingestion/storage traces expose bounded O(1) operational fields only."""
    import sqlite3

    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline import db_writer, ingest as ingest_module  # noqa: PLC0415

    init_db(tmp_db_path)
    fake_pdf = tmp_path / "supplier.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    trace_calls: list[dict] = []

    def _record_trace(**kwargs) -> bool:
        trace_calls.append(kwargs)
        return False

    monkeypatch.setattr(ingest_module, "convert_pdf", lambda _path: _FakeConversionResult())
    monkeypatch.setattr(
        ingest_module,
        "rasterize_pages",
        lambda _path: [b"PNG SHOULD_NOT_ENTER_TRACE", b"PNG TWO SHOULD_NOT_ENTER_TRACE"],
    )
    monkeypatch.setattr(ingest_module, "safe_update_current_trace", _record_trace)
    monkeypatch.setattr(db_writer, "safe_update_current_trace", _record_trace)

    result = ingest_module.ingest_document(pdf_path=str(fake_pdf), db_path=tmp_db_path)

    assert result["page_count"] == 2
    assert result["image_count"] == 2
    assert result["doc_id"]
    conn = sqlite3.connect(tmp_db_path)
    try:
        page_rows = conn.execute(
            "SELECT page_num, page_text, image_blob IS NOT NULL FROM pages WHERE doc_id=? ORDER BY page_num",
            (result["doc_id"],),
        ).fetchall()
    finally:
        conn.close()
    assert page_rows == [(0, "Safe extracted page text used only for DB persistence.", 1), (1, "", 1)]

    statuses = [call["metadata"]["status"] for call in trace_calls]
    assert statuses == ["started", "started", "completed", "completed"]
    assert "doc_id" not in ingest_module._INGEST_TRACE_METADATA_KEYS
    assert "doc_id" not in db_writer._STORAGE_TRACE_METADATA_KEYS
    for call in trace_calls:
        metadata = call["metadata"]
        assert set(metadata).issubset(call["allowed_metadata_keys"])
        assert metadata["boundary"] in {"ingestion", "storage"}
        assert result["doc_id"] not in repr(metadata)
    _forbidden_trace_payload_absent(trace_calls)


def test_ingest_validation_failure_trace_omits_path_and_raw_exception(monkeypatch, tmp_db_path: str, tmp_path) -> None:
    """Invalid PDFs still raise existing errors, but trace metadata remains sanitized."""
    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline import ingest as ingest_module  # noqa: PLC0415

    init_db(tmp_db_path)
    not_pdf = tmp_path / "absolute-secret-source.txt"
    not_pdf.write_text("not a pdf")
    trace_calls: list[dict] = []

    def _record_trace(**kwargs) -> bool:
        trace_calls.append(kwargs)
        return False

    monkeypatch.setattr(ingest_module, "safe_update_current_trace", _record_trace)

    with pytest.raises(ValueError, match="Not a PDF file"):
        ingest_module.ingest_document(pdf_path=str(not_pdf), db_path=tmp_db_path)

    assert len(trace_calls) == 1
    metadata = trace_calls[0]["metadata"]
    assert metadata == {
        "boundary": "ingestion",
        "status": "failed",
        "filename": "absolute-secret-source.txt",
        "error_class": "ValueError",
    }
    assert set(metadata).issubset(trace_calls[0]["allowed_metadata_keys"])
    assert "Not a PDF file" not in repr(metadata)
    assert str(tmp_path) not in repr(metadata)


def test_memory_no_leak(tmp_db_path: str, sample_pdf_path: str) -> None:
    """INGEST-01 / C3: cold VLM allocation is one-time; steady-state RSS stays bounded."""
    import gc
    import os

    import psutil

    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline.ingest import ingest_document  # noqa: PLC0415

    init_db(tmp_db_path)
    process = psutil.Process(os.getpid())

    gc.collect()
    rss_before_cold_start = process.memory_info().rss
    ingest_document(pdf_path=sample_pdf_path, db_path=tmp_db_path)
    gc.collect()
    rss_after_cold_start = process.memory_info().rss

    for _ in range(3):
        ingest_document(pdf_path=sample_pdf_path, db_path=tmp_db_path)
    gc.collect()
    rss_after_steady_state = process.memory_info().rss

    cold_start_growth_mb = (rss_after_cold_start - rss_before_cold_start) / (1024 ** 2)
    steady_state_growth_mb = (rss_after_steady_state - rss_after_cold_start) / (1024 ** 2)

    # The model's process-scoped cold allocation is intentionally excluded. Re-loading
    # that allocation per document produces multi-gigabyte steady-state growth.
    assert steady_state_growth_mb < 200, (
        f"Cold start grew {cold_start_growth_mb:.1f} MB; three steady-state ingests "
        f"grew {steady_state_growth_mb:.1f} MB (VLM model likely reloaded per document)"
    )


def test_cli_skip_existing_is_content_addressed_and_no_skip_forces_work(monkeypatch, tmp_path: Path) -> None:
    from src.pipeline import ingest as ingest_module

    first_dir = tmp_path / "first"
    renamed_dir = tmp_path / "renamed"
    first_dir.mkdir()
    renamed_dir.mkdir()
    first_pdf = first_dir / "supplier.pdf"
    renamed_pdf = renamed_dir / "renamed.pdf"
    first_pdf.write_bytes(b"%PDF-1.4 identical private bytes")
    shutil.copyfile(first_pdf, renamed_pdf)
    db_path = tmp_path / "content.db"
    calls = _install_lightweight_pipeline(monkeypatch, ingest_module)
    runner = CliRunner()

    first = runner.invoke(ingest_module.app, [str(first_dir), "--db-path", str(db_path)])
    assert first.exit_code == 0, first.output
    assert calls == {"convert": 1, "rasterize": 1}

    skipped = runner.invoke(ingest_module.app, [str(renamed_dir), "--db-path", str(db_path)])
    assert skipped.exit_code == 0, skipped.output
    assert "SKIP: renamed.pdf (content already ingested)" in skipped.output
    assert calls == {"convert": 1, "rasterize": 1}

    forced = runner.invoke(
        ingest_module.app,
        [str(renamed_dir), "--db-path", str(db_path), "--no-skip-existing"],
    )
    assert forced.exit_code == 0, forced.output
    assert calls == {"convert": 2, "rasterize": 2}

    digest = hashlib.sha256(first_pdf.read_bytes()).hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT doc_id, content_sha256, status FROM documents"
        ).fetchone()
    finally:
        conn.close()
    assert row == (digest, digest, "ingested")


def test_direct_ingest_never_silently_skips(monkeypatch, tmp_db_path: str, tmp_path: Path) -> None:
    from src.db.schema import init_db
    from src.pipeline import ingest as ingest_module

    init_db(tmp_db_path)
    pdf = tmp_path / "direct.pdf"
    pdf.write_bytes(b"%PDF direct-call content")
    calls = _install_lightweight_pipeline(monkeypatch, ingest_module)

    first = ingest_module.ingest_document(str(pdf), tmp_db_path)
    identity = ingest_module.resolve_document_identity(str(pdf), tmp_db_path)
    assert identity.already_ingested is True
    second = ingest_module.ingest_document(str(pdf), tmp_db_path, identity=identity)

    assert first["doc_id"] == second["doc_id"]
    assert calls == {"convert": 2, "rasterize": 2}


def test_direct_ingest_initializes_a_brand_new_database(monkeypatch, tmp_path: Path) -> None:
    from src.pipeline import ingest as ingest_module

    pdf = tmp_path / "direct-new-db.pdf"
    pdf.write_bytes(b"%PDF direct brand-new database")
    db_path = tmp_path / "brand-new.db"
    calls = _install_lightweight_pipeline(monkeypatch, ingest_module)

    result = ingest_module.ingest_document(str(pdf), str(db_path))

    assert len(result["doc_id"]) == 64
    assert calls == {"convert": 1, "rasterize": 1}
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute(
            "SELECT status FROM documents WHERE doc_id = ?", (result["doc_id"],)
        ).fetchone() == ("ingested",)
    finally:
        conn.close()


def test_legacy_path_identity_reingests_once_then_skips(monkeypatch, tmp_path: Path) -> None:
    from src.db.queries import insert_document, insert_page, mark_document_ingested
    from src.db.schema import init_db
    from src.pipeline import ingest as ingest_module

    folder = tmp_path / "legacy"
    folder.mkdir()
    pdf = folder / "legacy.pdf"
    pdf.write_bytes(b"%PDF legacy content")
    db_path = str(tmp_path / "legacy.db")
    init_db(db_path)
    legacy_id = hashlib.sha256(str(pdf.resolve()).encode()).hexdigest()[:16]
    insert_document(db_path, legacy_id, pdf.name, str(pdf.resolve()), 1, None)
    insert_page(db_path, legacy_id, 0, "old", b"old-png")
    mark_document_ingested(db_path, legacy_id)
    calls = _install_lightweight_pipeline(monkeypatch, ingest_module)
    runner = CliRunner()

    migrated = runner.invoke(ingest_module.app, [str(folder), "--db-path", db_path])
    assert migrated.exit_code == 0, migrated.output
    assert calls == {"convert": 1, "rasterize": 1}
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT doc_id, content_sha256 FROM documents WHERE doc_id = ?", (legacy_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row == (legacy_id, digest)

    skipped = runner.invoke(ingest_module.app, [str(folder), "--db-path", db_path])
    assert skipped.exit_code == 0, skipped.output
    assert calls == {"convert": 1, "rasterize": 1}


@pytest.mark.parametrize(
    ("status", "declared_pages", "stored_pages"),
    [("error", 1, 1), ("pending", 1, 1), ("ingested", 0, 0), ("ingested", 2, 1)],
)
def test_incomplete_identity_is_not_skippable(
    tmp_db_path: str,
    tmp_path: Path,
    status: str,
    declared_pages: int,
    stored_pages: int,
) -> None:
    from src.db.queries import insert_document, insert_page
    from src.db.schema import init_db
    from src.pipeline import ingest as ingest_module

    init_db(tmp_db_path)
    pdf = tmp_path / "incomplete.pdf"
    pdf.write_bytes(b"%PDF incomplete")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    insert_document(
        tmp_db_path,
        digest,
        pdf.name,
        str(pdf.resolve()),
        declared_pages,
        None,
        content_sha256=digest,
    )
    for page_num in range(stored_pages):
        insert_page(tmp_db_path, digest, page_num, "text", b"png")
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("UPDATE documents SET status = ? WHERE doc_id = ?", (status, digest))
    conn.commit()
    conn.close()

    assert ingest_module.resolve_document_identity(str(pdf), tmp_db_path).already_ingested is False


def test_noncontiguous_pages_are_not_treated_as_complete(tmp_db_path: str, tmp_path: Path) -> None:
    from src.db.queries import insert_document, insert_page, mark_document_ingested
    from src.db.schema import init_db
    from src.pipeline import ingest as ingest_module

    init_db(tmp_db_path)
    pdf = tmp_path / "gapped.pdf"
    pdf.write_bytes(b"%PDF gapped pages")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    insert_document(
        tmp_db_path,
        digest,
        pdf.name,
        str(pdf.resolve()),
        2,
        None,
        content_sha256=digest,
    )
    insert_page(tmp_db_path, digest, 0, "first", b"png-zero")
    insert_page(tmp_db_path, digest, 2, "third", b"png-two")
    mark_document_ingested(tmp_db_path, digest)

    assert ingest_module.resolve_document_identity(str(pdf), tmp_db_path).already_ingested is False


def test_cli_error_and_logs_never_expose_raw_content(monkeypatch, caplog, tmp_path: Path) -> None:
    from src.pipeline import ingest as ingest_module

    folder = tmp_path / "absolute-secret-source"
    folder.mkdir()
    pdf = folder / "supplier.pdf"
    pdf.write_bytes(b"%PDF private")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    raw_error = f"RAW PROVIDER PAGE TEXT {folder} {digest}"
    monkeypatch.setattr(
        ingest_module,
        "convert_pdf",
        lambda _path: (_ for _ in ()).throw(RuntimeError(raw_error)),
    )
    runner = CliRunner()
    sink_id = logger.add(caplog.handler, format="{message}", level="DEBUG")
    try:
        result = runner.invoke(
            ingest_module.app,
            [str(folder), "--db-path", str(tmp_path / "error.db")],
        )
    finally:
        logger.remove(sink_id)

    combined = result.output + caplog.text
    assert result.exit_code == 1
    assert "supplier.pdf" in combined
    assert "RuntimeError" in combined
    forbidden_values = (raw_error, str(folder), digest, "RAW PROVIDER PAGE TEXT")
    if any(value in combined for value in forbidden_values):
        pytest.fail("forbidden payload detected in CLI output or logs")


def test_supplied_identity_mismatch_is_rejected_before_conversion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.pipeline import ingest as ingest_module

    pdf = tmp_path / "identity.pdf"
    pdf.write_bytes(b"%PDF current bytes")
    db_path = str(tmp_path / "identity.db")
    calls = _install_lightweight_pipeline(monkeypatch, ingest_module)
    forged = ingest_module.DocumentIdentity(
        doc_id="f" * 64,
        content_sha256="f" * 64,
        already_ingested=False,
    )

    with pytest.raises(RuntimeError, match="identity changed before ingestion"):
        ingest_module.ingest_document(str(pdf), db_path, identity=forged)

    assert calls == {"convert": 0, "rasterize": 0}


def test_pdf_changed_during_conversion_is_not_committed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.pipeline import ingest as ingest_module

    pdf = tmp_path / "changing.pdf"
    pdf.write_bytes(b"%PDF original bytes")
    db_path = str(tmp_path / "changing.db")

    def _convert(_path: str):
        pdf.write_bytes(b"%PDF replacement bytes")
        return _OnePageConversionResult()

    monkeypatch.setattr(ingest_module, "convert_pdf", _convert)
    monkeypatch.setattr(ingest_module, "rasterize_pages", lambda _path: [b"PNG-ONE"])
    monkeypatch.setattr(ingest_module, "_extract_native_pdf_texts", lambda _path: {})

    with pytest.raises(RuntimeError, match="PDF changed during ingestion"):
        ingest_module.ingest_document(str(pdf), db_path)

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
        assert conn.execute("SELECT COUNT(*) FROM pages").fetchone() == (0,)
    finally:
        conn.close()


def test_native_pdf_text_overrides_lossy_vlm_text_per_page() -> None:
    from src.pipeline.ingest import _extract_page_texts

    extracted = _extract_page_texts(
        _OnePageConversionResult(),
        native_page_texts={0: "Expiry Date: 2027-01-31"},
    )

    assert extracted == {0: "Expiry Date: 2027-01-31"}


def test_atomic_write_rolls_back_new_document_on_second_page_failure(monkeypatch, tmp_db_path: str) -> None:
    from src.db.schema import init_db
    from src.pipeline import db_writer

    init_db(tmp_db_path)
    real_upsert_page = db_writer._upsert_page
    calls = 0

    def _fail_second(conn, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("PRIVATE PAGE FAILURE")
        return real_upsert_page(conn, *args, **kwargs)

    monkeypatch.setattr(db_writer, "_upsert_page", _fail_second)
    with pytest.raises(RuntimeError):
        db_writer.write_document_to_db(
            tmp_db_path,
            "atomic-new",
            "new.pdf",
            "C:/private/new.pdf",
            2,
            None,
            {0: "one", 1: "two"},
            [b"one", b"two"],
            content_sha256="a" * 64,
        )
    conn = sqlite3.connect(tmp_db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE doc_id='atomic-new'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pages WHERE doc_id='atomic-new'").fetchone()[0] == 0
    finally:
        conn.close()


def _seed_atomic_snapshot(db_path: str) -> None:
    from src.pipeline.db_writer import write_document_to_db

    write_document_to_db(
        db_path,
        "atomic-existing",
        "old.pdf",
        "C:/old.pdf",
        2,
        "old-json",
        {0: "old-zero", 1: "old-one"},
        [b"old-png-zero", b"old-png-one"],
        content_sha256="b" * 64,
    )
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO page_ocr_texts
            (doc_id, page_num, source, generated_text, text_sha256, page_image_sha256)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("atomic-existing", 0, "gemini", "ocr-zero", "t0", "i0"),
            ("atomic-existing", 1, "gemini", "ocr-one", "t1", "i1"),
        ],
    )
    conn.commit()
    conn.close()


def _atomic_snapshot(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        doc = conn.execute(
            "SELECT filename, file_path, page_count, docling_json, status, content_sha256 FROM documents WHERE doc_id='atomic-existing'"
        ).fetchone()
        pages = conn.execute(
            "SELECT page_num, page_text, image_blob FROM pages WHERE doc_id='atomic-existing' ORDER BY page_num"
        ).fetchall()
        ocr = conn.execute(
            "SELECT page_num, source, generated_text, text_sha256, page_image_sha256 FROM page_ocr_texts WHERE doc_id='atomic-existing' ORDER BY page_num"
        ).fetchall()
        return doc, pages, ocr
    finally:
        conn.close()


def test_reingest_failure_restores_document_pages_and_ocr(monkeypatch, tmp_db_path: str) -> None:
    from src.db.schema import init_db
    from src.pipeline import db_writer

    init_db(tmp_db_path)
    _seed_atomic_snapshot(tmp_db_path)
    before = _atomic_snapshot(tmp_db_path)
    real_upsert_page = db_writer._upsert_page
    calls = 0

    def _fail_second(conn, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("failure")
        return real_upsert_page(conn, *args, **kwargs)

    monkeypatch.setattr(db_writer, "_upsert_page", _fail_second)
    with pytest.raises(RuntimeError):
        db_writer.write_document_to_db(
            tmp_db_path,
            "atomic-existing",
            "new.pdf",
            "C:/new.pdf",
            2,
            "new-json",
            {0: "new-zero", 1: "new-one"},
            [b"new-zero", b"new-one"],
            content_sha256="c" * 64,
        )
    assert _atomic_snapshot(tmp_db_path) == before


def test_successful_reingest_invalidates_ocr_and_sparse_text_is_exact(tmp_db_path: str) -> None:
    from src.db.schema import init_db
    from src.pipeline.db_writer import write_document_to_db

    init_db(tmp_db_path)
    _seed_atomic_snapshot(tmp_db_path)
    write_document_to_db(
        tmp_db_path,
        "atomic-existing",
        "new.pdf",
        "C:/new.pdf",
        3,
        None,
        {1: "only page two"},
        [b"p0", b"p1", b"p2"],
        content_sha256="d" * 64,
    )
    conn = sqlite3.connect(tmp_db_path)
    try:
        pages = conn.execute(
            "SELECT page_num, page_text FROM pages WHERE doc_id='atomic-existing' ORDER BY page_num"
        ).fetchall()
        ocr_count = conn.execute(
            "SELECT COUNT(*) FROM page_ocr_texts WHERE doc_id='atomic-existing'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert pages == [(0, ""), (1, "only page two"), (2, "")]
    assert ocr_count == 0


def test_png_count_mismatch_preserves_existing_snapshot(tmp_db_path: str) -> None:
    from src.db.schema import init_db
    from src.pipeline.db_writer import write_document_to_db

    init_db(tmp_db_path)
    _seed_atomic_snapshot(tmp_db_path)
    before = _atomic_snapshot(tmp_db_path)
    with pytest.raises(ValueError, match="page image count mismatch"):
        write_document_to_db(
            tmp_db_path,
            "atomic-existing",
            "new.pdf",
            "C:/new.pdf",
            2,
            None,
            {0: "new", 1: "new"},
            [b"only-one"],
            content_sha256="e" * 64,
        )
    assert _atomic_snapshot(tmp_db_path) == before


def test_extract_page_texts_preserves_sparse_provenance() -> None:
    from src.pipeline.ingest import _extract_page_texts

    class Provenance:
        page_no = 2

    class TextItem:
        text = "only page two"
        prov = [Provenance()]

    class Document:
        texts = [TextItem()]

    class Result:
        document = Document()

    assert _extract_page_texts(Result()) == {1: "only page two"}
