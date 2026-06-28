"""Versioned visual index-run builder, mirroring ``retrieval_index_runs``.

The visual tier is a SEPARATE tier from the text indexer: it indexes ALL corpus
pages INCLUDING image-only ones, so it explicitly does NOT reuse
``indexer.load_indexable_pages`` with its ``indexer.py:192`` empty-text exclusion
(that exclusion is what stranded the Example-3 image-only pages; RESEARCH
Anti-Pattern). ``plan_visual_run`` computes a deterministic content hash over the
sorted ``(doc_id, page_num, filename)`` identifier tuples — no page text needed,
since the visual tier indexes page images — and yields a ``VisualIndexRun`` with a
``visual-built-{hash}`` run_id (idempotent re-runs over the same corpus).

``build_visual_index_run`` plans + persists the run metadata only; the GPU
embed/upsert step is the notebook's job (Plan 04). Rows/DTOs carry counts /
run_id / model_version / collection_name only — never image bytes or page text.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence

from src.retrieval.visual.collection import collection_name
from src.retrieval.visual.models import VisualIndexRun, deterministic_visual_run_id
from src.retrieval.visual.repository import save_visual_index_run

# A page descriptor for the visual tier: (doc_id, page_num, filename).
PageMeta = tuple[str, int, str]


def _compute_visual_content_hash(pages_meta: Sequence[PageMeta]) -> str:
    """Hash the corpus over sorted ``(doc_id, page_num, filename)`` identifiers.

    Mirrors ``indexer.compute_indexable_corpus_fingerprint`` in shape, but over
    identifiers ONLY (no page text) — the visual tier indexes images, so page text
    is irrelevant and image bytes must never enter the hash input.
    """
    digest = hashlib.sha256()
    for doc_id, page_num, filename in sorted(pages_meta, key=lambda m: (m[0], m[1], m[2])):
        for value in (doc_id, page_num, filename):
            digest.update(str(value).encode("utf-8"))
            digest.update(b"\x1f")
        digest.update(b"\x1e")
    return digest.hexdigest()


def plan_visual_run(
    pages_meta: Sequence[PageMeta],
    *,
    model_version: str,
    version: int = 1,
    previous_content_hash: str | None = None,
) -> VisualIndexRun:
    """Plan a deterministic ``VisualIndexRun`` over ALL corpus pages.

    ``pages_meta`` is an identifier-only sequence of ``(doc_id, page_num,
    filename)`` for every corpus page INCLUDING image-only ones. Counts are the
    distinct document count and the total page count (no empty-text exclusion).
    The ``run_id`` is ``deterministic_visual_run_id(content_hash)`` so the same
    corpus always plans to the same run.
    """
    content_hash = _compute_visual_content_hash(pages_meta)
    distinct_docs = {doc_id for doc_id, _page_num, _filename in pages_meta}
    page_count = len(pages_meta)
    return VisualIndexRun(
        run_id=deterministic_visual_run_id(content_hash),
        status="built",
        built_at=None,
        source_document_count=len(distinct_docs),
        source_page_count=page_count,
        indexed_page_count=page_count,
        model_version=model_version,
        collection_name=collection_name(version),
        content_hash=content_hash,
        previous_content_hash=previous_content_hash,
    )


def build_visual_index_run(
    db_path: str,
    pages_meta: Sequence[PageMeta],
    *,
    model_version: str,
    version: int = 1,
    previous_content_hash: str | None = None,
) -> VisualIndexRun:
    """Plan + persist a visual index run; return the planned run.

    Records run metadata only (the GPU embed/Qdrant-upsert step is the notebook's
    job — Plan 04). Persistence is idempotent via ``save_visual_index_run``'s
    ON CONFLICT update.

    Ensures the DB conforms to the current schema first: the visual tier may run
    against a ``compliance.db`` built before ``visual_index_runs`` existed, and
    ``init_db`` is idempotent (``CREATE TABLE IF NOT EXISTS`` only — no
    destructive DDL), so existing rows are never touched.
    """
    from src.db.schema import init_db

    init_db(db_path)
    run = plan_visual_run(
        pages_meta,
        model_version=model_version,
        version=version,
        previous_content_hash=previous_content_hash,
    )
    save_visual_index_run(db_path, run)
    return run
