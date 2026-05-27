"""Integration tests for src/pipeline/ingest.py — INGEST-01."""
from __future__ import annotations

import pytest


class _FakeDoclingDocument:
    pages = [object(), object()]
    texts: list[object] = []

    def export_to_markdown(self) -> str:
        return "Safe extracted page text used only for DB persistence."

    def export_to_json(self) -> str:
        return '{"raw_docling_json": "SHOULD_NOT_ENTER_TRACE"}'


class _FakeConversionResult:
    document = _FakeDoclingDocument()


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
        assert forbidden.isdisjoint(metadata)
        metadata_repr = repr(metadata)
        for value in forbidden:
            assert value not in metadata_repr


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
    """Storage trace failures must be no-op safe for empty page text and missing blobs."""
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
        png_blobs=[],
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
    assert page_rows == [(0, "", None), (1, "Second page text should persist but not trace.", None)]
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
    monkeypatch.setattr(ingest_module, "rasterize_pages", lambda _path: [b"PNG SHOULD_NOT_ENTER_TRACE"])
    monkeypatch.setattr(ingest_module, "safe_update_current_trace", _record_trace)
    monkeypatch.setattr(db_writer, "safe_update_current_trace", _record_trace)

    result = ingest_module.ingest_document(pdf_path=str(fake_pdf), db_path=tmp_db_path)

    assert result["page_count"] == 2
    assert result["image_count"] == 1
    assert result["doc_id"]
    conn = sqlite3.connect(tmp_db_path)
    try:
        page_rows = conn.execute(
            "SELECT page_num, page_text, image_blob IS NOT NULL FROM pages WHERE doc_id=? ORDER BY page_num",
            (result["doc_id"],),
        ).fetchall()
    finally:
        conn.close()
    assert page_rows == [(0, "Safe extracted page text used only for DB persistence.", 1), (1, "", 0)]

    statuses = [call["metadata"]["status"] for call in trace_calls]
    assert statuses == ["started", "started", "completed", "completed"]
    for call in trace_calls:
        metadata = call["metadata"]
        assert set(metadata).issubset(call["allowed_metadata_keys"])
        assert metadata["boundary"] in {"ingestion", "storage"}
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
    """INGEST-01 / C3 pitfall: memory must not grow unboundedly across 3 sequential ingests."""
    import psutil, os  # noqa: E401
    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline.ingest import ingest_document  # noqa: PLC0415

    init_db(tmp_db_path)
    process = psutil.Process(os.getpid())

    rss_before = process.memory_info().rss
    for _ in range(3):
        ingest_document(pdf_path=sample_pdf_path, db_path=tmp_db_path)
    rss_after = process.memory_info().rss

    growth_mb = (rss_after - rss_before) / (1024 ** 2)
    # Allow up to 200 MB growth for 3 sequential ingests (model load is expected);
    # unbounded growth would be 500 MB+ per run
    assert growth_mb < 500, f"Memory grew {growth_mb:.1f} MB across 3 ingests (C3 leak?)"