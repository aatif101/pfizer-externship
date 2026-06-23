"""Typed DTOs for the visual retrieval index boundary.

These models intentionally expose page-count metadata, hashes, run ids, the
collection name, and the model version, but NOT raw page text or image bytes.
The embedder/run layer owns the image-byte handoff to the GPU so callers cannot
accidentally log page-image contents (RESEARCH Pitfall 7, T-05-01).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualIndexRun:
    """Inspectable metadata for one ``sdf_page_images`` index build/status run.

    Mirrors ``src.retrieval.models.RetrievalIndexRun`` but adds ``model_version``
    and ``collection_name`` and stores ``status`` as its string value. Carries
    counts/run_id/identifiers ONLY — never image bytes or page text.
    """

    run_id: str
    status: str
    built_at: str | None
    source_document_count: int
    source_page_count: int
    indexed_page_count: int
    model_version: str = ""
    collection_name: str = ""
    content_hash: str | None = None
    previous_content_hash: str | None = None
    is_stale: bool = False
    stale_reason: str | None = None
    error_reason: str | None = None


def deterministic_visual_run_id(content_hash: str) -> str:
    """Return a stable visual run id from a corpus content hash.

    Mirrors ``src.retrieval.indexer._deterministic_run_id`` so re-runs over the
    same corpus produce an idempotent run identifier.
    """
    return f"visual-built-{content_hash[:16]}"
