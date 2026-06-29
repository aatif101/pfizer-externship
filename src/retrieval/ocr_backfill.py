"""OCR/VLM text backfill for image-backed pages with empty extracted text.

This module keeps OCR-derived text distinct from the original ingestion
``pages.page_text`` column. Backfilled text is stored in ``page_ocr_texts`` with
source provenance, timestamp metadata, and a hash of the exact page image blob
that was OCR'd; the retrieval index then combines original + OCR text at index
build time.

Docling imports are lazy so normal retrieval/index tests stay lightweight.
"""
from __future__ import annotations

import gc
import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from src.db.schema import _connect, init_db
from src.retrieval.indexer import normalize_index_text

DEFAULT_OCR_SOURCE = "docling_forced_ocr"
DEFAULT_LOW_TEXT_THRESHOLD = 20

PageTextExtractor = Callable[[str, frozenset[int]], dict[int, str]]


@dataclass(frozen=True)
class OcrCandidatePage:
    """One image-backed page eligible for OCR backfill."""

    doc_id: str
    filename: str
    file_path: str
    page_num: int
    current_text_length: int
    page_image_sha256: str


@dataclass(frozen=True)
class OcrBackfillRecord:
    """OCR text persisted for one page, separate from original page text."""

    doc_id: str
    page_num: int
    source: str
    generated_text: str
    text_sha256: str
    page_image_sha256: str


@dataclass(frozen=True)
class OcrBackfillResult:
    """Inspectable summary for an OCR backfill run."""

    candidates: tuple[OcrCandidatePage, ...]
    records: tuple[OcrBackfillRecord, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def written_count(self) -> int:
        return len(self.records)


def backfill_low_text_pages(
    db_path: str,
    *,
    min_text_length: int = DEFAULT_LOW_TEXT_THRESHOLD,
    source: str = DEFAULT_OCR_SOURCE,
    extractor: PageTextExtractor | None = None,
) -> OcrBackfillResult:
    """OCR pages whose original ``page_text`` is blank or very short.

    ``extractor`` receives ``(pdf_path, page_nums)`` and returns OCR text keyed by
    0-indexed page number. Tests inject this callable; production defaults to
    Docling forced full-page OCR. Empty OCR results are not written.
    """

    init_db(db_path)
    candidates = load_ocr_candidate_pages(db_path, min_text_length=min_text_length)
    if not candidates:
        return OcrBackfillResult(candidates=(), records=())

    extractor = extractor or extract_docling_forced_ocr_page_texts
    records: list[OcrBackfillRecord] = []
    for _doc_id, pages in _group_candidates_by_doc(candidates).items():
        page_nums = frozenset(page.page_num for page in pages)
        extracted = extractor(pages[0].file_path, page_nums)
        for page in pages:
            generated_text = normalize_index_text(extracted.get(page.page_num, ""))
            if not generated_text:
                continue
            record = OcrBackfillRecord(
                doc_id=page.doc_id,
                page_num=page.page_num,
                source=source,
                generated_text=generated_text,
                text_sha256=_sha256_text(generated_text),
                page_image_sha256=page.page_image_sha256,
            )
            upsert_page_ocr_text(db_path, record)
            records.append(record)
    return OcrBackfillResult(candidates=candidates, records=tuple(records))


def load_ocr_candidate_pages(
    db_path: str,
    *,
    min_text_length: int = DEFAULT_LOW_TEXT_THRESHOLD,
) -> tuple[OcrCandidatePage, ...]:
    """Return ingested pages with image blobs and short/blank original text."""

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                d.doc_id,
                d.filename,
                d.file_path,
                p.page_num,
                LENGTH(TRIM(COALESCE(p.page_text, ''))) AS current_text_length,
                p.image_blob
            FROM documents d
            JOIN pages p ON p.doc_id = d.doc_id
            WHERE d.status = ?
              AND p.image_blob IS NOT NULL
              AND LENGTH(TRIM(COALESCE(p.page_text, ''))) < ?
            ORDER BY d.doc_id ASC, p.page_num ASC
            """,
            ("ingested", int(min_text_length)),
        ).fetchall()
    finally:
        conn.close()

    return tuple(
        OcrCandidatePage(
            doc_id=str(row[0]),
            filename=str(row[1]),
            file_path=str(row[2]),
            page_num=int(row[3]),
            current_text_length=int(row[4]),
            page_image_sha256=_sha256_bytes(bytes(row[5])),
        )
        for row in rows
    )


def upsert_page_ocr_text(db_path: str, record: OcrBackfillRecord) -> None:
    """Persist OCR-derived text with provenance, separate from ``pages``."""

    safe_text = normalize_index_text(record.generated_text)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO page_ocr_texts (
                doc_id, page_num, source, generated_text, text_sha256,
                page_image_sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(doc_id, page_num, source) DO UPDATE SET
                generated_text = excluded.generated_text,
                text_sha256 = excluded.text_sha256,
                page_image_sha256 = excluded.page_image_sha256,
                updated_at = excluded.updated_at
            """,
            (
                record.doc_id,
                record.page_num,
                record.source,
                safe_text,
                record.text_sha256,
                record.page_image_sha256,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def extract_docling_forced_ocr_page_texts(pdf_path: str, page_nums: frozenset[int]) -> dict[int, str]:
    """Run Docling forced full-page OCR and return text for requested pages.

    This uses Docling's standard PDF pipeline with OCR enabled and
    ``force_full_page_ocr=True``. The default RapidOCR options are provider-free,
    but they may download OCR model artifacts on first run depending on the local
    Docling installation. For GPU/Colab demo runs, this remains separate from the
    ColQwen visual index and can be run before rebuilding the text index.
    """

    from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions  # noqa: PLC0415
    from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: PLC0415

    pipeline_options = PdfPipelineOptions(do_ocr=True)
    pipeline_options.ocr_options = RapidOcrOptions(
        lang=["english"],
        force_full_page_ocr=True,
        backend="torch",
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )
    try:
        result = converter.convert(source=pdf_path)
        page_texts = _extract_page_texts_from_docling_document(result.document)
        return {page_num: page_texts.get(page_num, "") for page_num in page_nums}
    finally:
        del converter
        gc.collect()


def _extract_page_texts_from_docling_document(doc: object) -> dict[int, str]:
    page_texts: dict[int, list[str]] = {}
    if hasattr(doc, "texts"):
        for text_item in doc.texts:
            if not getattr(text_item, "prov", None):
                continue
            for prov in text_item.prov:
                page_no = getattr(prov, "page_no", None)
                text = getattr(text_item, "text", "")
                if page_no is not None and text:
                    page_texts.setdefault(int(page_no) - 1, []).append(str(text))

    if not page_texts and hasattr(doc, "export_to_markdown"):
        page_texts[0] = [str(doc.export_to_markdown())]

    return {page_num: "\n".join(chunks) for page_num, chunks in page_texts.items()}


def _group_candidates_by_doc(candidates: Iterable[OcrCandidatePage]) -> dict[str, list[OcrCandidatePage]]:
    grouped: dict[str, list[OcrCandidatePage]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.doc_id].append(candidate)
    return grouped


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
