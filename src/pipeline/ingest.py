"""CLI entry point for the ingestion pipeline.

Usage:
    python -m pipeline.ingest <folder> [--db-path compliance.db]

Security:
    T-1-01: Path traversal — resolve input path; reject paths that do not exist
    T-1-02: OOM/DoS — reject PDFs exceeding MAX_PDF_MB before Docling ingest
    T-1-03: SQL injection — all SQL via parameterized queries in db/queries.py
    T-1-04: Log leakage — page text content is NEVER logged at INFO level
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from tqdm import tqdm

from src.tracing import observe, safe_update_current_trace

from src.config import get_settings
from src.db.schema import init_db
from src.pipeline.converter import convert_pdf
from src.pipeline.rasterizer import rasterize_pages
from src.pipeline.db_writer import write_document_to_db

app = typer.Typer(help="Pfizer SDF ingestion pipeline")

_INGEST_TRACE_METADATA_KEYS = frozenset(
    {"boundary", "status", "doc_id", "filename", "page_count", "image_count", "error_class"}
)


def _trace_ingestion(metadata: dict[str, object]) -> None:
    """Best-effort ingestion trace update with a strict metadata allowlist."""
    safe_update_current_trace(
        tags=["phase1", "ingestion"],
        metadata=metadata,
        allowed_metadata_keys=_INGEST_TRACE_METADATA_KEYS,
    )


def _extract_page_texts(conv_result) -> dict[int, str]:
    """Extract text per page from DoclingDocument.

    Primary approach: iterate doc.texts items, group by prov.page_no.
    Assumption A1: page_no is 1-indexed in docling provenance.
    Returns dict keyed by 0-indexed page_num for consistency with pypdfium2.
    """
    page_texts: dict[int, list[str]] = {}
    doc = conv_result.document

    # Approach 1: iterate text items with provenance
    if hasattr(doc, "texts"):
        for text_item in doc.texts:
            if text_item.prov:
                for prov in text_item.prov:
                    page_no = getattr(prov, "page_no", None)
                    if page_no is not None:
                        # docling page_no is 1-indexed; convert to 0-indexed
                        page_idx = page_no - 1
                        page_texts.setdefault(page_idx, []).append(text_item.text)

    # Approach 2: fallback — export full document as markdown if no provenance
    if not page_texts and hasattr(doc, "export_to_markdown"):
        full_text = doc.export_to_markdown()
        page_texts[0] = [full_text]

    return {pno: "\n".join(chunks) for pno, chunks in page_texts.items()}


@observe(name="ingest_document")
def ingest_document(pdf_path: str, db_path: str) -> dict:
    """Ingest a single PDF: Docling text + pypdfium2 images + SQLite writes.

    D-04: Decorated with @observe for Langfuse tracing.
    T-1-01: Validates path before any processing.
    T-1-02: Rejects files exceeding MAX_PDF_MB.
    """
    settings = get_settings()
    resolved = Path(pdf_path).resolve()
    filename = resolved.name
    doc_id: str | None = None
    page_count: int | None = None
    image_count: int | None = None

    try:
        # T-1-01: Path traversal protection — resolve to absolute path
        if not resolved.exists():
            raise FileNotFoundError(f"PDF not found: {resolved}")
        if not resolved.suffix.lower() == ".pdf":
            raise ValueError(f"Not a PDF file: {resolved}")

        # T-1-02: OOM/DoS protection — check size before Docling
        file_size_mb = resolved.stat().st_size / (1024 ** 2)
        if file_size_mb > settings.max_pdf_mb:
            raise ValueError(
                f"PDF {resolved.name} ({file_size_mb:.1f} MB) exceeds "
                f"MAX_PDF_MB={settings.max_pdf_mb}. Skipping to prevent OOM."
            )

        doc_id = hashlib.sha256(str(resolved).encode()).hexdigest()[:16]
        _trace_ingestion(
            {
                "boundary": "ingestion",
                "status": "started",
                "doc_id": doc_id,
                "filename": filename,
            }
        )

        # Step 1: Docling text extraction (new converter per call — C3 mitigation)
        logger.info(f"Converting {resolved.name} with Docling VlmPipeline...")
        conv_result = convert_pdf(str(resolved))
        doc = conv_result.document
        page_count = len(doc.pages) if doc.pages else 0

        # Step 2: pypdfium2 rasterization (independent of Docling — C2 mitigation)
        logger.info(f"Rasterizing {page_count} pages at 150 DPI...")
        png_blobs = rasterize_pages(str(resolved))
        image_count = len(png_blobs)

        # Step 3: Extract page texts
        page_texts = _extract_page_texts(conv_result)

        # Step 4: SQLite writes (T-1-03: all SQL parameterized in db/queries.py)
        # T-1-04: docling_json stored in DB but NOT logged at INFO level
        docling_json = doc.export_to_json() if hasattr(doc, "export_to_json") else None

        write_document_to_db(
            db_path=db_path,
            doc_id=doc_id,
            filename=resolved.name,
            file_path=str(resolved),
            page_count=page_count,
            docling_json=docling_json,
            page_texts=page_texts,
            png_blobs=png_blobs,
        )

        _trace_ingestion(
            {
                "boundary": "ingestion",
                "status": "completed",
                "doc_id": doc_id,
                "filename": filename,
                "page_count": page_count,
                "image_count": image_count,
            }
        )
        return {"doc_id": doc_id, "page_count": page_count, "image_count": image_count}
    except Exception as exc:
        metadata: dict[str, object] = {
            "boundary": "ingestion",
            "status": "failed",
            "filename": filename,
            "error_class": type(exc).__name__,
        }
        if doc_id is not None:
            metadata["doc_id"] = doc_id
        if page_count is not None:
            metadata["page_count"] = page_count
        if image_count is not None:
            metadata["image_count"] = image_count
        _trace_ingestion(metadata)
        raise


@app.command()
def ingest(
    folder: Path = typer.Argument(..., help="Folder containing PDF files to ingest"),
    db_path: str = typer.Option("compliance.db", "--db-path", help="SQLite database path"),
    skip_existing: bool = typer.Option(True, "--skip-existing/--no-skip-existing",
                                        help="Skip already-ingested documents"),
) -> None:
    """Ingest all PDFs in FOLDER into the compliance database."""
    # T-1-01: Resolve and validate folder path
    resolved_folder = folder.resolve()
    if not resolved_folder.exists():
        typer.echo(f"ERROR: Folder not found: {resolved_folder}", err=True)
        raise typer.Exit(1)
    if not resolved_folder.is_dir():
        typer.echo(f"ERROR: Not a directory: {resolved_folder}", err=True)
        raise typer.Exit(1)

    pdf_files = sorted(resolved_folder.glob("*.pdf"))
    if not pdf_files:
        typer.echo(f"No PDFs found in {resolved_folder}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(pdf_files)} PDF(s) in {resolved_folder}")
    init_db(db_path)

    errors: list[tuple[str, str]] = []
    for pdf_path in tqdm(pdf_files, desc="Ingesting", unit="doc"):
        try:
            result = ingest_document(str(pdf_path), db_path)
            logger.info(
                f"OK: {pdf_path.name} — {result['page_count']} pages, "
                f"{result['image_count']} images"
            )
        except Exception as exc:
            logger.error(f"FAILED: {pdf_path.name} — {exc}")
            errors.append((pdf_path.name, str(exc)))

    total = len(pdf_files)
    succeeded = total - len(errors)
    typer.echo(f"\nDone. {succeeded}/{total} succeeded.")
    if errors:
        for name, err in errors:
            typer.echo(f"  ERROR: {name}: {err}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()