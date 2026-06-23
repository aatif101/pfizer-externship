"""Qdrant collection-config shape assertions for the visual tier (Task 3).

Pure config-construction checks: 3 named vectors, HNSW disabled (m=0) on
``original`` only, size==128, all MAX_SIM. ``importorskip``s qdrant-client so the
suite stays green offline; the same builder runs unconditionally on Colab. No
embedding/score is fabricated.
"""
from __future__ import annotations

import pytest

from src.retrieval.visual.collection import build_vectors_config, collection_name


def test_collection_name_is_versioned() -> None:
    assert collection_name() == "sdf_page_images_v1"
    assert collection_name(2) == "sdf_page_images_v2"


def test_build_vectors_config_has_exactly_three_named_vectors() -> None:
    pytest.importorskip("qdrant_client")
    config = build_vectors_config()
    assert set(config.keys()) == {"original", "mean_pooling_rows", "mean_pooling_columns"}


def test_original_has_hnsw_disabled_pooled_do_not() -> None:
    pytest.importorskip("qdrant_client")
    config = build_vectors_config()
    assert config["original"].hnsw_config is not None
    assert config["original"].hnsw_config.m == 0
    # Pooled vectors carry no HNSW override (HNSW enabled).
    assert config["mean_pooling_rows"].hnsw_config is None
    assert config["mean_pooling_columns"].hnsw_config is None


def test_all_vectors_size_128_and_max_sim() -> None:
    pytest.importorskip("qdrant_client")
    from qdrant_client import models

    config = build_vectors_config()
    for params in config.values():
        assert params.size == 128
        assert params.multivector_config.comparator == models.MultiVectorComparator.MAX_SIM
