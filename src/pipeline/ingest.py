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
from dataclasses import dataclass
from pathlib import Path

import typer
from loguru import logger
from tqdm import tqdm

from src.tracing import observe, safe_update_current_trace

from src.config import get_settings
from src.db.queries import lookup_document_identity
from src.db.schema import init_db
from src.pipeline.converter import convert_pdf
from src.pipeline.rasterizer import rasterize_pages
from src.pipeline.db_writer import write_document_to_db

app = typer.Typer(help="Pfizer SDF ingestion pipeline")

_INGEST_TRACE_METADATA_KEYS = frozenset(
    {"boundary", "status", "filename", "page_count", "image_count", "error_class"}
)

_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class DocumentIdentity:
    """Stable content identity plus the persisted completeness decision."""

    doc_id: str
    content_sha256: str
    already_ingested: bool


def _content_sha256(pdf_path: Path) -> str:
    """Hash PDF bytes incrementally without loading supplier content into RAM."""

    digest = hashlib.sha256()
    with pdf_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _legacy_path_doc_id(pdf_path: Path) -> str:
    """Return the historical 16-character path-derived identifier."""

    return hashlib.sha256(str(pdf_path.resolve()).encode()).hexdigest()[:16]


def resolve_document_identity(pdf_path: str, db_path: str) -> DocumentIdentity:
    """Resolve content-first identity and whether its stored snapshot is complete."""

    resolved = Path(pdf_path).resolve()
    content_sha256 = _content_sha256(resolved)
    legacy_doc_id = _legacy_path_doc_id(resolved)
    stored = lookup_document_identity(db_path, content_sha256, legacy_doc_id)

    if stored is None:
        return DocumentIdentity(content_sha256, content_sha256, False)

    if stored.content_sha256 == content_sha256:
        complete = (
            stored.status == "ingested"
            and stored.page_count > 0
            and stored.persisted_page_count == stored.page_count
            and stored.first_page_num == 0
            and stored.last_page_num == stored.page_count - 1
        )
        return DocumentIdentity(stored.doc_id, content_sha256, complete)

    # A pre-hash legacy row is reused exactly once so downstream foreign keys
    # remain stable.  A legacy row with a different established hash is not
    # overwritten: changed bytes receive their own full content ID.
    if stored.doc_id == legacy_doc_id and stored.content_sha256 is None:
        return DocumentIdentity(stored.doc_id, content_sha256, False)
    return DocumentIdentity(content_sha256, content_sha256, False)


def _trace_ingestion(metadata: dict[str, object]) -> None:
    """Best-effort ingestion trace update with a strict metadata allowlist."""
    safe_update_current_trace(
        tags=["phase1", "ingestion"],
        metadata=metadata,
        allowed_metadata_keys=_INGEST_TRACE_METADATA_KEYS,
    )


def _extract_native_pdf_texts(pdf_path: Path) -> dict[int, str]:
    """Return lossless embedded PDF text, when present, keyed by page number.

    Granite-Docling remains the primary parser and source of layout/JSON. Native
    PDF text is preferred for born-digital pages because it preserves literal
    compliance values exactly; scanned pages naturally fall through to the VLM
    text because their embedded text layer is empty.
    """

    try:
        import pypdfium2 as pdfium  # noqa: PLC0415

        document = pdfium.PdfDocument(str(pdf_path))
        native_texts: dict[int, str] = {}
        try:
            for page_num in range(len(document)):
                page = document[page_num]
                try:
                    text_page = page.get_textpage()
                    try:
                        text = text_page.get_text_range()
                    finally:
                        text_page.close()
                finally:
                    page.close()
                if text and text.strip():
                    native_texts[page_num] = text
        finally:
            document.close()
        return native_texts
    except Exception as exc:  # noqa: BLE001 - best-effort quality fallback.
        logger.warning(
            f"Embedded-text recovery unavailable for {pdf_path.name} "
            f"({type(exc).__name__}); retaining Docling text"
        )
        return {}


def _extract_page_texts(
    conv_result,
    *,
    native_page_texts: dict[int, str] | None = None,
) -> dict[int, str]:
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

    extracted = {pno: "\n".join(chunks) for pno, chunks in page_texts.items()}
    for page_num, native_text in (native_page_texts or {}).items():
        if native_text.strip():
            extracted[page_num] = native_text
    return extracted


@observe(name="ingest_document")
def ingest_document(
    pdf_path: str,
    db_path: str,
    *,
    identity: DocumentIdentity | None = None,
) -> dict:
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
            raise FileNotFoundError(f"PDF not found: {filename}")
        if not resolved.suffix.lower() == ".pdf":
            raise ValueError(f"Not a PDF file: {filename}")

        # T-1-02: OOM/DoS protection — check size before Docling
        file_size_mb = resolved.stat().st_size / (1024 ** 2)
        if file_size_mb > settings.max_pdf_mb:
            raise ValueError(
                f"PDF {resolved.name} ({file_size_mb:.1f} MB) exceeds "
                f"MAX_PDF_MB={settings.max_pdf_mb}. Skipping to prevent OOM."
            )

        # Keep the public one-document boundary useful on a brand-new database;
        # the folder CLI also initializes once up front for batch efficiency.
        init_db(db_path)
        current_identity = resolve_document_identity(str(resolved), db_path)
        if identity is not None and (
            identity.doc_id != current_identity.doc_id
            or identity.content_sha256 != current_identity.content_sha256
        ):
            raise RuntimeError(f"PDF identity changed before ingestion: {filename}")
        resolved_identity = current_identity
        doc_id = resolved_identity.doc_id
        _trace_ingestion(
            {
                "boundary": "ingestion",
                "status": "started",
                "filename": filename,
            }
        )

        # Step 1: Docling text extraction (process-scoped converter avoids repeated VLM loads)
        logger.info(f"Converting {resolved.name} with Docling VlmPipeline...")
        conv_result = convert_pdf(str(resolved))
        doc = conv_result.document
        page_count = len(doc.pages) if doc.pages else 0

        # Step 2: pypdfium2 rasterization (independent of Docling — C2 mitigation)
        logger.info(f"Rasterizing {page_count} pages at 150 DPI...")
        png_blobs = rasterize_pages(str(resolved))
        image_count = len(png_blobs)

        # Step 3: Extract page texts. Prefer an exact embedded text layer for
        # born-digital pages; image-only scans retain Granite-Docling output.
        native_page_texts = _extract_native_pdf_texts(resolved)
        page_texts = _extract_page_texts(
            conv_result,
            native_page_texts=native_page_texts,
        )

        # Bind the committed content identity to the exact bytes consumed by
        # conversion/rasterization. A file changed mid-run is never persisted
        # under the stale preflight digest.
        if _content_sha256(resolved) != resolved_identity.content_sha256:
            raise RuntimeError(f"PDF changed during ingestion: {filename}")

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
            content_sha256=resolved_identity.content_sha256,
        )

        _trace_ingestion(
            {
                "boundary": "ingestion",
                "status": "completed",
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
        typer.echo(f"ERROR: Folder not found: {folder.name or 'input'}", err=True)
        raise typer.Exit(1)
    if not resolved_folder.is_dir():
        typer.echo(f"ERROR: Not a directory: {folder.name or 'input'}", err=True)
        raise typer.Exit(1)

    pdf_files = sorted(resolved_folder.glob("*.pdf"))
    if not pdf_files:
        typer.echo(f"No PDFs found in {resolved_folder.name}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(pdf_files)} PDF(s) in {resolved_folder.name}")
    init_db(db_path)

    errors: list[tuple[str, str]] = []
    succeeded = 0
    skipped = 0
    for pdf_path in tqdm(pdf_files, desc="Ingesting", unit="doc"):
        try:
            identity = resolve_document_identity(str(pdf_path), db_path)
            if skip_existing and identity.already_ingested:
                typer.echo(f"SKIP: {pdf_path.name} (content already ingested)")
                skipped += 1
                continue

            result = ingest_document(str(pdf_path), db_path, identity=identity)
            succeeded += 1
            logger.info(
                f"OK: {pdf_path.name} — {result['page_count']} pages, "
                f"{result['image_count']} images"
            )
        except Exception as exc:
            error_class = type(exc).__name__
            logger.error(f"FAILED: {pdf_path.name} ({error_class})")
            errors.append((pdf_path.name, error_class))

    total = len(pdf_files)
    failed = len(errors)
    typer.echo(
        f"\nSUMMARY succeeded={succeeded} skipped={skipped} "
        f"failed={failed} total={total}"
    )
    if errors:
        for name, error_class in errors:
            typer.echo(f"ERROR: {name} ({error_class})", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
