"""Unit tests for src/pipeline/rasterizer.py — INGEST-02."""
from __future__ import annotations

import io
import sqlite3

import pytest
from PIL import Image


def test_rasterize_returns_png_bytes(sample_pdf_path: str) -> None:
    """INGEST-02: rasterize_pages must return a non-empty list of PNG bytes."""
    from src.pipeline.rasterizer import rasterize_pages  # noqa: PLC0415

    blobs = rasterize_pages(sample_pdf_path)
    assert len(blobs) >= 1, "Expected at least one page"
    for blob in blobs:
        assert isinstance(blob, bytes), "Each blob must be bytes"
        assert len(blob) > 0, "Blob must not be empty"
        # Validate PNG magic bytes: \x89PNG\r\n\x1a\n
        assert blob[:8] == b"\x89PNG\r\n\x1a\n", "Blob is not a valid PNG"


def test_150dpi_dimensions(sample_pdf_path: str) -> None:
    """INGEST-02 / Pitfall 6: 150 DPI PNG must have correct pixel dimensions for a US Letter page."""
    from src.pipeline.rasterizer import rasterize_pages  # noqa: PLC0415

    blobs = rasterize_pages(sample_pdf_path)
    assert blobs, "No pages rasterized"

    img = Image.open(io.BytesIO(blobs[0]))
    width_px, height_px = img.size

    # US Letter at 150 DPI: 8.5in × 11in → 1275 × 1650 px (±10 px tolerance)
    # Sample PDF uses 612×792 pt (8.5×11 in); scale = 150/72 ≈ 2.083
    # Expected: 612 * 2.083 ≈ 1275 px wide, 792 * 2.083 ≈ 1650 px tall
    assert 1200 <= width_px <= 1350, f"Width {width_px}px not near 1275px (150 DPI)"
    assert 1550 <= height_px <= 1750, f"Height {height_px}px not near 1650px (150 DPI)"


def test_png_blob_stored(tmp_db_path: str, sample_pdf_path: str) -> None:
    """INGEST-02: image_blob column in pages table must be non-null after ingest."""
    from src.db.schema import init_db  # noqa: PLC0415
    from src.pipeline.ingest import ingest_document  # noqa: PLC0415

    init_db(tmp_db_path)
    result = ingest_document(pdf_path=sample_pdf_path, db_path=tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    rows = conn.execute(
        "SELECT page_num, image_blob FROM pages WHERE doc_id=?",
        (result["doc_id"],),
    ).fetchall()
    conn.close()

    assert rows, "No page rows found"
    for page_num, blob in rows:
        assert blob is not None, f"image_blob is NULL for page {page_num}"
        assert len(blob) > 0, f"image_blob is empty for page {page_num}"