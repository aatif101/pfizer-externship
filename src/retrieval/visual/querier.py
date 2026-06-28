"""Pure, offline-safe two-stage Qdrant query-payload builder + response mapping.

VISUAL-02's retrieval seam splits cleanly into deterministic plumbing (testable
offline, no GPU) and GPU/Qdrant execution (deferred to the Colab notebook):

- ``build_query_payload`` constructs the canonical two-stage ``query_points``
  kwargs — two mean-pooled ``Prefetch`` entries (HNSW prefetch) reranked with
  ``using="original"`` (full multivector MAX_SIM). ``qdrant_client`` is lazy
  (inside the function body) so importing this module needs no qdrant-client
  install and stays offline-safe.
- ``execute_query`` is a thin wrapper that runs the payload against a live client
  (notebook/GPU only — never asserted offline).
- ``map_response_to_candidates`` reads each point's ``{doc_id, page_num}`` payload
  + score into a frozen ``VisualCandidate`` carrying a 0-indexed ``page_num`` and
  ``display_page_num = page_num + 1`` (RESEARCH Pitfall 6 — page identity).

The Qdrant payload (Plan 01) carries identifiers ONLY; this module never reads
image bytes or page text — there are none to read.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.retrieval.visual.collection import collection_name


@dataclass(frozen=True)
class VisualCandidate:
    """One ranked visual retrieval candidate, keyed on 0-indexed page identity.

    Carries identifiers + the rerank score ONLY — never image bytes or page text.
    ``display_page_num`` is ``page_num + 1`` for citation surfaces only.
    """

    doc_id: str
    page_num: int
    display_page_num: int
    score: float


def build_query_payload(
    query_embedding: "object",
    *,
    prefetch_limit: int = 200,
    search_limit: int = 20,
    version: int = 1,
) -> dict:
    """Build the canonical two-stage ``query_points`` kwargs dict.

    Prefetches the two mean-pooled named vectors via HNSW (top
    ``prefetch_limit``), then reranks the merged candidates with the full
    multivector (``using="original"``, MAX_SIM) down to ``search_limit``. The
    returned dict is passed verbatim as ``client.query_points(**payload)``
    (RESEARCH Pattern 4). ``qdrant_client`` is imported lazily so this stays
    offline-importable.
    """
    from qdrant_client import models

    prefetch = [
        models.Prefetch(query=query_embedding, limit=prefetch_limit, using="mean_pooling_columns"),
        models.Prefetch(query=query_embedding, limit=prefetch_limit, using="mean_pooling_rows"),
    ]
    return {
        "collection_name": collection_name(version),
        "query": query_embedding,
        "prefetch": prefetch,
        "limit": search_limit,
        "with_payload": True,
        "with_vectors": False,
        "using": "original",
    }


def execute_query(client: "object", query_embedding: "object", **kwargs: "object") -> "object":
    """Execute the two-stage query against a live Qdrant client (notebook/GPU only).

    A thin wrapper over ``build_query_payload`` + ``client.query_points``. This is
    never exercised by the offline suite (no live collection); the offline tests
    assert ``build_query_payload`` shape and ``map_response_to_candidates``
    identity instead (metric-integrity rule).
    """
    payload = build_query_payload(query_embedding, **kwargs)
    return client.query_points(**payload)


def map_response_to_candidates(points: "object") -> list[VisualCandidate]:
    """Map Qdrant response points → 0-indexed ``VisualCandidate`` rows.

    Reads ``payload["doc_id"]`` and ``int(payload["page_num"])`` (0-indexed) plus
    the rerank ``score``; sets ``display_page_num = page_num + 1``. Points missing
    ``doc_id`` / ``page_num`` (or with no payload) are skipped, not raised, so a
    malformed point never aborts the whole result.
    """
    candidates: list[VisualCandidate] = []
    for point in points or []:
        payload = getattr(point, "payload", None) or {}
        doc_id = payload.get("doc_id")
        raw_page_num = payload.get("page_num")
        if doc_id is None or raw_page_num is None:
            continue
        page_num = int(raw_page_num)
        candidates.append(
            VisualCandidate(
                doc_id=str(doc_id),
                page_num=page_num,
                display_page_num=page_num + 1,
                score=float(getattr(point, "score", 0.0)),
            )
        )
    return candidates
