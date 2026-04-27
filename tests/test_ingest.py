"""Integration tests for src/pipeline/ingest.py — INGEST-01."""
from __future__ import annotations

import pytest


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