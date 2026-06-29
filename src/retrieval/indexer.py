"""Provider-free deterministic retrieval indexer over ingested SQLite pages.

This module deliberately reads only document/page metadata and text from the
local SQLite database. It never loads image blobs, extraction provider outputs,
or secrets. Public diagnostics return hashes, counts, run IDs, and short
whitespace-normalized snippets only.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from src.db.schema import _connect, init_db
from src.retrieval.models import (
    CorpusFingerprint,
    PageIndexInput,
    RetrievalIndexPageRecord,
    RetrievalIndexRun,
    RetrievalIndexStatus,
    RetrievalIndexStatusReport,
)
from src.retrieval.repository import load_latest_index_run, save_index_run_with_pages
from src.tracing import observe, safe_update_current_trace

# Injectable test seams: tests monkeypatch both symbols. langfuse_context=None
# means "resolve the live v3 client lazily inside src.tracing".
_LANGFUSE_AVAILABLE: bool = True
langfuse_context: Any | None = None

_INDEX_TRACE_ALLOWED_KEYS = frozenset(
    {
        "boundary",
        "index_status",
        "run_id",
        "source_document_count",
        "source_page_count",
        "indexed_page_count",
        "error_class",
    }
)

_SNIPPET_MAX_CHARS = 160
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class IndexablePage:
    """Normalized source page loaded for indexing, with no image/provider fields."""

    doc_id: str
    filename: str
    page_count: int
    status: str
    page_num: int
    normalized_text: str
    snippet: str
    text_source: str
    has_ocr_text: bool
    ocr_text_sha256: str | None


@dataclass(frozen=True)
class RetrievalIndexBuildResult:
    """Result of a retrieval index build with safe inspectable metadata."""

    run: RetrievalIndexRun
    pages: tuple[RetrievalIndexPageRecord, ...]


@observe(name="retrieval_index_build")
def build_retrieval_index(db_path: str) -> RetrievalIndexBuildResult:
    """Build and persist the current text retrieval index state transactionally.

    Empty corpora are recorded as an ``empty`` run. Non-empty corpora are
    recorded as ``built`` with page metadata and optional FTS rows written in the
    same transaction as run metadata.
    """

    try:
        init_db(db_path)
        latest = load_latest_index_run(db_path)
        pages = load_indexable_pages(db_path)
        fingerprint = compute_indexable_corpus_fingerprint(pages)
        status = RetrievalIndexStatus.EMPTY if not pages else RetrievalIndexStatus.BUILT
        run_id = _deterministic_run_id(status, fingerprint.content_hash)
        previous_hash = latest.content_hash if latest else None
        run = RetrievalIndexRun(
            run_id=run_id,
            status=status,
            built_at=None,
            source_document_count=fingerprint.document_count,
            source_page_count=fingerprint.page_count,
            indexed_page_count=len(pages),
            content_hash=fingerprint.content_hash,
            previous_content_hash=previous_hash,
            is_stale=False,
            stale_reason=None,
            error_reason=None,
        )
        page_inputs = [
            PageIndexInput(
                page.doc_id,
                page.page_num,
                page.filename,
                page.normalized_text,
                text_source=page.text_source,
                has_ocr_text=page.has_ocr_text,
                ocr_text_sha256=page.ocr_text_sha256,
            )
            for page in pages
        ]
        snippets = {(page.doc_id, page.page_num): page.snippet for page in pages}
        records = save_index_run_with_pages(db_path, run, page_inputs, snippets=snippets)
        _safe_update_trace_metadata(
            {
                "boundary": "retrieval_index",
                "index_status": run.status.value,
                "run_id": run.run_id,
                "source_document_count": run.source_document_count,
                "source_page_count": run.source_page_count,
                "indexed_page_count": run.indexed_page_count,
            }
        )
        return RetrievalIndexBuildResult(run=run, pages=tuple(records))
    except Exception as exc:
        _safe_update_trace_metadata(
            {
                "boundary": "retrieval_index",
                "index_status": RetrievalIndexStatus.ERROR.value,
                "error_class": exc.__class__.__name__,
            }
        )
        raise


def get_retrieval_index_status(db_path: str) -> RetrievalIndexStatusReport:
    """Report missing, built, empty, or stale without mutating index state."""

    init_db(db_path)
    latest = load_latest_index_run(db_path)
    pages = load_indexable_pages(db_path)
    fingerprint = compute_indexable_corpus_fingerprint(pages)

    if latest is None:
        return RetrievalIndexStatusReport(
            status=RetrievalIndexStatus.MISSING,
            run_id=None,
            source_document_count=fingerprint.document_count,
            source_page_count=fingerprint.page_count,
            indexed_page_count=0,
            content_hash=fingerprint.content_hash,
            stale_reason="No retrieval index run has been built.",
        )

    if not pages:
        return RetrievalIndexStatusReport(
            status=RetrievalIndexStatus.EMPTY,
            run_id=latest.run_id,
            source_document_count=fingerprint.document_count,
            source_page_count=fingerprint.page_count,
            indexed_page_count=0,
            content_hash=fingerprint.content_hash,
            previous_content_hash=latest.content_hash,
            is_stale=latest.content_hash != fingerprint.content_hash,
            stale_reason="Current corpus has no ingested pages with nonblank text.",
        )

    if latest.content_hash != fingerprint.content_hash or latest.status is RetrievalIndexStatus.EMPTY:
        return RetrievalIndexStatusReport(
            status=RetrievalIndexStatus.STALE,
            run_id=latest.run_id,
            source_document_count=fingerprint.document_count,
            source_page_count=fingerprint.page_count,
            indexed_page_count=len(pages),
            content_hash=fingerprint.content_hash,
            previous_content_hash=latest.content_hash,
            is_stale=True,
            stale_reason="Current ingested page corpus differs from latest successful retrieval index run.",
        )

    return RetrievalIndexStatusReport(
        status=RetrievalIndexStatus.BUILT,
        run_id=latest.run_id,
        source_document_count=fingerprint.document_count,
        source_page_count=fingerprint.page_count,
        indexed_page_count=latest.indexed_page_count,
        content_hash=fingerprint.content_hash,
        previous_content_hash=latest.previous_content_hash,
        is_stale=False,
    )


def load_indexable_pages(db_path: str) -> tuple[IndexablePage, ...]:
    """Load ingested pages with original and OCR-derived text in index order."""

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            WITH ocr AS (
                SELECT
                    doc_id,
                    page_num,
                    GROUP_CONCAT(generated_text, char(10)) AS ocr_text,
                    GROUP_CONCAT(text_sha256, ',') AS ocr_text_sha256
                FROM page_ocr_texts
                WHERE TRIM(COALESCE(generated_text, '')) <> ''
                GROUP BY doc_id, page_num
            )
            SELECT
                d.doc_id,
                d.filename,
                d.page_count,
                d.status,
                p.page_num,
                p.page_text,
                COALESCE(ocr.ocr_text, '') AS ocr_text,
                ocr.ocr_text_sha256
            FROM documents d
            JOIN pages p ON p.doc_id = d.doc_id
            LEFT JOIN ocr ON ocr.doc_id = p.doc_id AND ocr.page_num = p.page_num
            WHERE d.status = ?
              AND (
                TRIM(COALESCE(p.page_text, '')) <> ''
                OR TRIM(COALESCE(ocr.ocr_text, '')) <> ''
              )
            ORDER BY d.doc_id ASC, p.page_num ASC
            """,
            ("ingested",),
        ).fetchall()
    finally:
        conn.close()

    pages: list[IndexablePage] = []
    for row in rows:
        original_text = row[5] or ""
        ocr_text = row[6] or ""
        has_original = bool(normalize_index_text(original_text))
        has_ocr = bool(normalize_index_text(ocr_text))
        if has_original and has_ocr:
            text_source = "original+ocr"
            combined_text = f"{original_text}\n{ocr_text}"
        elif has_ocr:
            text_source = "ocr"
            combined_text = ocr_text
        else:
            text_source = "original"
            combined_text = original_text
        pages.append(
            IndexablePage(
                doc_id=row[0],
                filename=row[1],
                page_count=row[2],
                status=row[3],
                page_num=row[4],
                normalized_text=normalize_index_text(combined_text),
                snippet=make_page_snippet(combined_text),
                text_source=text_source,
                has_ocr_text=has_ocr,
                ocr_text_sha256=row[7],
            )
        )
    return tuple(pages)


def compute_indexable_corpus_fingerprint(pages: tuple[IndexablePage, ...]) -> CorpusFingerprint:
    """Compute a stable hash from indexable source metadata and normalized text."""

    digest = hashlib.sha256()
    seen_docs: set[str] = set()
    for page in pages:
        seen_docs.add(page.doc_id)
        for value in (
            page.doc_id,
            page.filename,
            page.page_count,
            page.status,
            page.page_num,
            page.text_source,
            page.has_ocr_text,
            page.ocr_text_sha256 or "",
            page.normalized_text,
        ):
            digest.update(str(value).encode("utf-8"))
            digest.update(b"\x1f")
        digest.update(b"\x1e")

    return CorpusFingerprint(document_count=len(seen_docs), page_count=len(pages), content_hash=digest.hexdigest())


def normalize_index_text(text: str | None) -> str:
    """Normalize page text for hashing, snippets, and FTS ingestion."""

    return _WHITESPACE_RE.sub(" ", text or "").strip()


def make_page_snippet(text: str | None, *, max_chars: int = _SNIPPET_MAX_CHARS) -> str:
    """Return a short, verbatim-order, whitespace-normalized prefix."""

    normalized = normalize_index_text(text)
    return normalized[:max_chars]


def _deterministic_run_id(status: RetrievalIndexStatus, content_hash: str) -> str:
    return f"retrieval-{status.value}-{content_hash[:16]}"


def _safe_update_trace_metadata(metadata: dict[str, Any]) -> None:
    """Attach whitelisted retrieval-index metadata to the current trace, if available.

    This helper is intentionally defensive: Langfuse absence, auth absence, and
    context update failures must never change indexing behavior.
    """

    if not _LANGFUSE_AVAILABLE:
        return
    safe_update_current_trace(
        tags=["retrieval", "index"],
        metadata=metadata,
        allowed_metadata_keys=_INDEX_TRACE_ALLOWED_KEYS,
        context=langfuse_context,
    )
