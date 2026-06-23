"""Pure, offline-safe Qdrant collection-config + upsert-payload builders.

All ``qdrant_client`` imports are lazy (inside function bodies) so importing this
module requires no qdrant-client install and stays offline-safe. The builders
construct config/point objects only — they never open a Qdrant client. Upsert
payloads carry ``{doc_id, page_num}`` identifiers ONLY (0-indexed page_num),
never image bytes or page text (RESEARCH Pitfall 6/7, T-05-02).
"""
from __future__ import annotations

import hashlib

COLLECTION_BASENAME = "sdf_page_images"


def collection_name(version: int = 1) -> str:
    """Return the versioned collection name, mirroring ``retrieval_index_runs`` versioning."""
    return f"{COLLECTION_BASENAME}_v{version}"


def build_vectors_config() -> dict:
    """Build the three-named-vector Qdrant config for the page-image collection.

    - ``original``: full multivector, HNSW DISABLED (``m=0``) to avoid indexing
      ~768 patch vectors/page (RESEARCH Pitfall 1 / Anti-Pattern).
    - ``mean_pooling_rows`` / ``mean_pooling_columns``: pooled multivectors with
      HNSW enabled (no ``m=0`` override) for the prefetch stage.

    All three are ``size=128``, COSINE distance, MAX_SIM comparator.
    """
    from qdrant_client import models

    base = dict(size=128, distance=models.Distance.COSINE)
    msim = models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM)
    return {
        "original": models.VectorParams(
            **base,
            multivector_config=msim,
            hnsw_config=models.HnswConfigDiff(m=0),  # HNSW OFF on the full multivector
        ),
        "mean_pooling_columns": models.VectorParams(**base, multivector_config=msim),
        "mean_pooling_rows": models.VectorParams(**base, multivector_config=msim),
    }


def deterministic_point_id(doc_id: str, page_num: int) -> str:
    """Return a stable point id from ``(doc_id, page_num)`` for idempotent re-upsert.

    Mirrors the deterministic-run-id style (``indexer._deterministic_run_id``);
    a SHA-256 hexdigest so the same page always maps to the same point
    (RESEARCH Pitfall 8 — resumable build).
    """
    return hashlib.sha256(f"{doc_id}:{page_num}".encode("utf-8")).hexdigest()


def build_upsert_point(
    doc_id: str,
    page_num: int,
    original_mv: "object",
    pooled_rows: "object",
    pooled_cols: "object",
) -> "object":
    """Build a Qdrant ``PointStruct`` for one page image.

    The payload carries ONLY ``{doc_id, page_num}`` with ``page_num`` int-cast
    0-indexed (RESEARCH Pitfall 6 — page identity). NO image bytes, NO page text.
    The point id is deterministic so re-upserting the same page is idempotent.
    """
    from qdrant_client import models

    return models.PointStruct(
        id=deterministic_point_id(doc_id, page_num),
        vector={
            "original": original_mv,
            "mean_pooling_rows": pooled_rows,
            "mean_pooling_columns": pooled_cols,
        },
        payload={"doc_id": doc_id, "page_num": int(page_num)},
    )
