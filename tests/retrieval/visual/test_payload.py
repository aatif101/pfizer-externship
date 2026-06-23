"""Upsert-payload identity assertions for the visual tier (Task 3).

These are the metric-integrity-adjacent identity guards (RESEARCH Pitfall 6/7):
payload carries 0-indexed ``page_num`` + ``doc_id`` only, the point id is a
deterministic hash that round-trips, and NO image bytes / page text leak into the
payload. ``deterministic_point_id`` is pure Python and tested unconditionally;
the PointStruct assertions ``importorskip`` qdrant-client.
"""
from __future__ import annotations

import pytest

from src.retrieval.visual.collection import build_upsert_point, deterministic_point_id


def test_deterministic_point_id_is_stable_and_unique() -> None:
    a1 = deterministic_point_id("doc-a", 0)
    a2 = deterministic_point_id("doc-a", 0)
    b = deterministic_point_id("doc-a", 1)
    c = deterministic_point_id("doc-b", 0)
    assert a1 == a2  # idempotent re-upsert
    assert a1 != b  # different page -> different id
    assert a1 != c  # different doc -> different id


def test_upsert_payload_is_zero_indexed_and_content_free() -> None:
    pytest.importorskip("qdrant_client")
    point = build_upsert_point(
        "5543408c4dacc48b",
        2,
        original_mv=[[0.0] * 128],
        pooled_rows=[[0.0] * 128],
        pooled_cols=[[0.0] * 128],
    )
    assert point.payload == {"doc_id": "5543408c4dacc48b", "page_num": 2}
    assert isinstance(point.payload["page_num"], int)
    # No raw-content keys.
    assert "image_blob" not in point.payload
    assert "page_text" not in point.payload
    # No bytes value anywhere in the payload.
    assert not any(isinstance(v, (bytes, bytearray, memoryview)) for v in point.payload.values())


def test_upsert_point_id_matches_deterministic_hash() -> None:
    pytest.importorskip("qdrant_client")
    point = build_upsert_point(
        "doc-x",
        3,
        original_mv=[[0.0] * 128],
        pooled_rows=[[0.0] * 128],
        pooled_cols=[[0.0] * 128],
    )
    assert point.id == deterministic_point_id("doc-x", 3)
    # Vector dict carries exactly the three named vectors.
    assert set(point.vector.keys()) == {"original", "mean_pooling_rows", "mean_pooling_columns"}
