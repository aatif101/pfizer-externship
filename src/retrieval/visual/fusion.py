"""Pure, offline-safe RRF fusion → ``RetrievalHit`` mapping.

This is the VISUAL-02 fusion seam: it combines the visual tier's ranked pages
with the text tier's ranked pages by Reciprocal Rank Fusion (k=60), then maps the
fused page identities into the SAME ``RetrievalHit`` DTO that ``retrieve_evidence``
and the eval harness already consume — so the recall@k / ndcg / citation-accuracy
metric code needs ZERO change (they key only on ``(doc_id, page_num)``).

Imports stdlib + ``src.retrieval.models`` ONLY — no heavy deps, fully offline.
Pages are keyed on a 0-indexed ``(doc_id, page_num)`` (RESEARCH Pitfall 6); a
wrong index silently yields recall@k=0. Image-only pages (no text-tier match)
keep ``snippet``/``evidence_text`` empty — no fabricated grounding, mirroring the
``_bounded_evidence_text`` empty-page fallback established in quick-260611-ou3.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.retrieval.models import RetrievalHit, RetrievalScoreComponents

PageKey = tuple[str, int]


@dataclass(frozen=True)
class TextLookupRecord:
    """Per-page text-tier metadata used to fill a fused hit's display fields.

    Carries the filename plus the bounded snippet/evidence_text DRAWN FROM THE
    TEXT TIER. For an image-only page (no text match) the record is absent or
    carries empty strings, so the fused hit keeps empty grounding — never image
    bytes, never fabricated text.
    """

    filename: str = ""
    snippet: str = ""
    evidence_text: str = ""
    text_source: str = "original"
    has_ocr_text: bool = False


def rrf_fuse(
    visual_ranked: Sequence[PageKey],
    text_ranked: Sequence[PageKey],
    *,
    k: int = 60,
) -> list[tuple[PageKey, float]]:
    """Fuse two ranked page lists by Reciprocal Rank Fusion (k=60).

    ``score(page) = Σ_tiers 1 / (k + rank + 1)`` with ``rank`` 0-based, keyed on
    ``(doc_id, page_num)`` (RESEARCH Pattern 5). Returns ``[(page_key, score)]``
    sorted by descending fused score with a stable tie-break on the page key
    ascending, so the fused order is fully deterministic (T-05-09).
    """
    scores: dict[PageKey, float] = {}
    for ranked in (visual_ranked, text_ranked):
        for rank, page_key in enumerate(ranked):
            scores[page_key] = scores.get(page_key, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def to_retrieval_hits(
    fused: Sequence[tuple[PageKey, float]],
    lookup: dict[PageKey, TextLookupRecord],
    *,
    visual_only_ids: frozenset[PageKey] = frozenset(),
) -> tuple[RetrievalHit, ...]:
    """Map fused ``(page_key, rrf_score)`` entries → canonical ``RetrievalHit``.

    Mirrors ``retriever._score_candidate``: 0-indexed ``page_num``,
    ``display_page_num = page_num + 1``, ``score = round(rrf_score, 4)``, a
    ``RetrievalScoreComponents`` whose ``source`` is ``"visual"`` when the page
    came only from the visual tier (in ``visual_only_ids``) else ``"fused"``.
    ``snippet``/``evidence_text`` come from the text-tier ``lookup`` record; an
    image-only page (absent from ``lookup`` or carrying empty text) keeps both
    empty — no fabricated grounding (ou3 empty-page fallback). No image bytes ever
    enter a hit.
    """
    hits: list[RetrievalHit] = []
    for page_key, rrf_score in fused:
        doc_id, page_num = page_key
        record = lookup.get(page_key) or TextLookupRecord()
        source = "visual" if page_key in visual_only_ids else "fused"
        components = RetrievalScoreComponents(source=source)
        hits.append(
            RetrievalHit(
                doc_id=doc_id,
                filename=record.filename,
                page_num=page_num,
                display_page_num=page_num + 1,
                score=round(rrf_score, 4),
                score_components=components,
                snippet=record.snippet,
                evidence_text=record.evidence_text,
                text_source=record.text_source,
                has_ocr_text=record.has_ocr_text,
            )
        )
    return tuple(hits)
