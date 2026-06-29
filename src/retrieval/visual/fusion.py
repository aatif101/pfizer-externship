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

from collections.abc import Mapping, Sequence
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
    text_weight: float = 4.0,
    visual_weight: float = 1.0,
    page_text_lengths: Mapping[PageKey, int] | None = None,
    empty_text_boost: float = 3.0,
    empty_text_threshold: int = 0,
) -> list[tuple[PageKey, float]]:
    """Fuse ranked page lists with a deterministic text-first guardrail.

    Scores use weighted RRF with ``text_weight > visual_weight``. Ordering is
    intentionally gated: text hits keep their original order, visual-only hits
    append after text hits, and visual-only pages whose original ``page_text`` is
    empty are ordered before other visual-only pages.
    """
    scores: dict[PageKey, float] = {}
    for rank, page_key in enumerate(text_ranked):
        scores[page_key] = scores.get(page_key, 0.0) + text_weight / (k + rank + 1)
    for rank, page_key in enumerate(visual_ranked):
        score = visual_weight / (k + rank + 1)
        if _is_empty_text_page(page_key, page_text_lengths, empty_text_threshold):
            score += empty_text_boost / (k + rank + 1)
        scores[page_key] = scores.get(page_key, 0.0) + score

    seen_text: set[PageKey] = set()
    fused: list[tuple[PageKey, float]] = []
    for page_key in text_ranked:
        if page_key in seen_text:
            continue
        fused.append((page_key, scores[page_key]))
        seen_text.add(page_key)

    visual_only = list(dict.fromkeys(page_key for page_key in visual_ranked if page_key not in seen_text))
    visual_only.sort(
        key=lambda page_key: (
            not _is_empty_text_page(page_key, page_text_lengths, empty_text_threshold),
            -scores[page_key],
            page_key,
        )
    )
    fused.extend((page_key, scores[page_key]) for page_key in visual_only)
    return fused


def assert_fused_recall_not_below_text(
    gold_targets_by_query: Mapping[str, Sequence[PageKey]],
    text_ranked_by_query: Mapping[str, Sequence[PageKey]],
    fused_ranked_by_query: Mapping[str, Sequence[PageKey]],
    *,
    k_values: Sequence[int] = (5, 10),
) -> None:
    """Raise if fused page recall drops below text-only for any requested k."""

    for k in k_values:
        text_recall = _macro_recall_at_k(gold_targets_by_query, text_ranked_by_query, k)
        fused_recall = _macro_recall_at_k(gold_targets_by_query, fused_ranked_by_query, k)
        if fused_recall < text_recall:
            raise AssertionError(
                f"fused recall@{k}={fused_recall:.6f} is below text-only recall@{k}={text_recall:.6f}"
            )


def _macro_recall_at_k(
    gold_targets_by_query: Mapping[str, Sequence[PageKey]],
    ranked_by_query: Mapping[str, Sequence[PageKey]],
    k: int,
) -> float:
    if k <= 0:
        raise ValueError("k must be >= 1")
    recalls: list[float] = []
    for query_id, targets in gold_targets_by_query.items():
        gold = set(targets)
        if not gold:
            recalls.append(0.0)
            continue
        retrieved = set((ranked_by_query.get(query_id) or [])[:k])
        recalls.append(len(gold.intersection(retrieved)) / len(gold))
    return sum(recalls) / len(recalls) if recalls else 0.0


def _is_empty_text_page(
    page_key: PageKey,
    page_text_lengths: Mapping[PageKey, int] | None,
    empty_text_threshold: int,
) -> bool:
    if page_text_lengths is None:
        return False
    return int(page_text_lengths.get(page_key, empty_text_threshold + 1)) <= empty_text_threshold


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
