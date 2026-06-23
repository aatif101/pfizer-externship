"""Fused-hit → ``RetrievalHit`` DTO mapping assertions (Task 2).

These assert the deterministic DTO mapping the eval/RAG path consumes unchanged
(metric-integrity rule — no fabricated quality number): 0-indexed ``page_num``,
``display_page_num = page_num + 1``, ``score == round(rrf_score, 4)``, the
``source`` tag ("fused" when in both tiers, "visual" when text-absent), and the
image-only empty-evidence contract (snippet/evidence_text "" when no text in the
lookup, mirroring ``_bounded_evidence_text`` empty-page fallback).
"""
from __future__ import annotations

from src.retrieval.models import RetrievalHit
from src.retrieval.visual.fusion import TextLookupRecord, rrf_fuse, to_retrieval_hits


def test_to_retrieval_hits_zero_indexed_identity_and_source_tags() -> None:
    visual = [("doc_a", 0), ("5543408c4dacc48b", 2)]
    text = [("doc_a", 0)]
    fused = rrf_fuse(visual, text, k=60)
    lookup = {
        ("doc_a", 0): TextLookupRecord(filename="a.pdf", snippet="alpha snippet", evidence_text="alpha evidence"),
        # image-only page (5543408c..,2) intentionally NOT in lookup
        ("5543408c4dacc48b", 2): TextLookupRecord(filename="cytiva.pdf"),
    }
    visual_only = frozenset({("5543408c4dacc48b", 2)})
    hits = to_retrieval_hits(fused, lookup, visual_only_ids=visual_only)

    assert all(isinstance(h, RetrievalHit) for h in hits)
    by_key = {(h.doc_id, h.page_num): h for h in hits}

    a = by_key[("doc_a", 0)]
    assert a.page_num == 0
    assert a.display_page_num == 1
    assert a.score == round(dict(fused)[("doc_a", 0)], 4)
    assert a.score_components.source == "fused"  # present in both tiers
    assert a.snippet == "alpha snippet"
    assert a.evidence_text == "alpha evidence"

    img = by_key[("5543408c4dacc48b", 2)]
    assert img.page_num == 2
    assert img.display_page_num == 3
    assert img.score_components.source == "visual"  # visual-only page


def test_image_only_page_has_empty_snippet_and_evidence_text() -> None:
    visual = [("5543408c4dacc48b", 2)]
    fused = rrf_fuse(visual, [], k=60)
    lookup = {("5543408c4dacc48b", 2): TextLookupRecord(filename="cytiva.pdf")}
    hits = to_retrieval_hits(fused, lookup, visual_only_ids=frozenset({("5543408c4dacc48b", 2)}))

    img = hits[0]
    # No fabricated grounding for an image-only page (ou3 empty-page fallback).
    assert img.snippet == ""
    assert img.evidence_text == ""
    assert img.filename == "cytiva.pdf"


def test_missing_lookup_entry_yields_empty_text_safely() -> None:
    fused = rrf_fuse([("orphan", 4)], [], k=60)
    hits = to_retrieval_hits(fused, {})  # no lookup record at all
    assert len(hits) == 1
    assert hits[0].doc_id == "orphan"
    assert hits[0].filename == ""
    assert hits[0].snippet == ""
    assert hits[0].evidence_text == ""


def test_hits_preserve_fused_rank_order() -> None:
    visual = [("doc_a", 0), ("doc_b", 1)]
    text = [("doc_b", 1)]
    fused = rrf_fuse(visual, text, k=60)
    lookup = {
        ("doc_a", 0): TextLookupRecord(filename="a.pdf"),
        ("doc_b", 1): TextLookupRecord(filename="b.pdf", snippet="b", evidence_text="b"),
    }
    hits = to_retrieval_hits(fused, lookup)
    # doc_b is in both tiers -> higher fused score -> first.
    assert [(h.doc_id, h.page_num) for h in hits] == [("doc_b", 1), ("doc_a", 0)]
