"""pypdfium2 page rasterizer — 150 DPI PNG thumbnails.

CRITICAL: scale = DPI / 72 (Pitfall C6).
scale=1.5 → ~108 DPI (WRONG). scale=150/72 ≈ 2.083 → 150 DPI (CORRECT).

This module is independent of Docling. It opens the same PDF separately
because VlmPipeline's generate_page_images is broken (Pitfall C2).
"""
from __future__ import annotations

import io

import pypdfium2 as pdfium
from loguru import logger

DPI_TARGET: int = 150
SCALE: float = DPI_TARGET / 72  # ≈ 2.083


def rasterize_pages(pdf_path: str) -> list[bytes]:
    """Render all pages of a PDF to PNG bytes at 150 DPI.

    Returns a list of bytes where index i is the PNG for 0-indexed page i.
    """
    png_blobs: list[bytes] = []
    with pdfium.PdfDocument(pdf_path) as pdf:
        n_pages = len(pdf)
        logger.debug(f"Rasterizing {n_pages} pages from {pdf_path} at {DPI_TARGET} DPI")
        for page_idx in range(n_pages):
            page = pdf.get_page(page_idx)
            bitmap = page.render(scale=SCALE, rev_byteorder=True)
            pil_img = bitmap.to_pil()
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG", optimize=False)
            png_blobs.append(buf.getvalue())
            logger.debug(f"  Page {page_idx}: {pil_img.size[0]}×{pil_img.size[1]}px")
    return png_blobs