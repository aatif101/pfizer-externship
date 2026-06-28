"""Two-stage query-payload shape + candidate-mapping assertions (Task 1).

The payload builder is the VISUAL-02 retrieval seam. These tests assert
deterministic plumbing ONLY (metric-integrity rule): the canonical two-stage
prefetch shape (exactly two pooled ``Prefetch`` entries + ``using="original"``
rerank), the limit/with_payload/with_vector flags, and the identity mapping from
Qdrant points to 0-indexed ``VisualCandidate`` rows. NEVER a retrieval-quality
number off a fabricated embedding/score.

The ``build_query_payload`` shape assertions ``importorskip`` qdrant-client (it
constructs real ``models.Prefetch`` objects); ``map_response_to_candidates`` is
pure Python driven by fake point stand-ins and runs unconditionally.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.retrieval.visual.querier import (
    VisualCandidate,
    build_query_payload,
    map_response_to_candidates,
)


def test_build_query_payload_two_stage_shape() -> None:
    pytest.importorskip("qdrant_client")
    query_embedding = [[0.0] * 128]
    payload = build_query_payload(query_embedding, prefetch_limit=200, search_limit=20)

    assert payload["collection_name"] == "sdf_page_images_v1"
    assert payload["query"] is query_embedding
    assert payload["using"] == "original"
    assert payload["limit"] == 20
    assert payload["with_payload"] is True
    assert payload["with_vectors"] is False

    prefetch = payload["prefetch"]
    assert len(prefetch) == 2
    usings = [p.using for p in prefetch]
    assert usings == ["mean_pooling_columns", "mean_pooling_rows"]
    assert all(p.limit == 200 for p in prefetch)
    assert all(p.query is query_embedding for p in prefetch)


def test_build_query_payload_respects_version() -> None:
    pytest.importorskip("qdrant_client")
    payload = build_query_payload([[0.0] * 128], prefetch_limit=50, search_limit=5, version=3)
    assert payload["collection_name"] == "sdf_page_images_v3"
    assert payload["limit"] == 5
    assert all(p.limit == 50 for p in payload["prefetch"])


@dataclass
class _FakePoint:
    payload: dict
    score: float


def test_map_response_to_candidates_zero_indexed_identity() -> None:
    points = [
        _FakePoint(payload={"doc_id": "5543408c4dacc48b", "page_num": 2}, score=0.91),
        _FakePoint(payload={"doc_id": "doc-b", "page_num": 0}, score=0.42),
    ]
    candidates = map_response_to_candidates(points)
    assert candidates == [
        VisualCandidate(doc_id="5543408c4dacc48b", page_num=2, display_page_num=3, score=0.91),
        VisualCandidate(doc_id="doc-b", page_num=0, display_page_num=1, score=0.42),
    ]
    # page_num stays 0-indexed int; display is +1.
    assert candidates[0].page_num == 2
    assert candidates[0].display_page_num == 3
    assert isinstance(candidates[0].page_num, int)


def test_map_response_casts_string_page_num_to_int() -> None:
    points = [_FakePoint(payload={"doc_id": "doc-c", "page_num": "7"}, score=0.1)]
    candidates = map_response_to_candidates(points)
    assert candidates[0].page_num == 7
    assert isinstance(candidates[0].page_num, int)
    assert candidates[0].display_page_num == 8


def test_map_response_skips_points_missing_identity() -> None:
    points = [
        _FakePoint(payload={"page_num": 1}, score=0.5),  # no doc_id
        _FakePoint(payload={"doc_id": "doc-d"}, score=0.5),  # no page_num
        _FakePoint(payload={"doc_id": "doc-e", "page_num": 4}, score=0.5),  # valid
    ]
    candidates = map_response_to_candidates(points)
    assert len(candidates) == 1
    assert candidates[0].doc_id == "doc-e"
    assert candidates[0].page_num == 4


def test_map_response_handles_empty_payload_without_crash() -> None:
    points = [_FakePoint(payload=None, score=0.5)]
    assert map_response_to_candidates(points) == []
