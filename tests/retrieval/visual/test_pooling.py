"""Pure pooling + blob-decode behaviors for the visual tier (Task 2).

Metric-integrity rule: these tests assert SHAPES and identity round-trips ONLY,
on synthetic-but-honestly-labeled tensors of KNOWN shape. No embedding/score is
fabricated and no similarity/recall/ndcg number is asserted. The pooling test
``importorskip``s torch (it runs unconditionally on Colab); the blob-decode test
runs everywhere because Pillow is a hard dependency.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from src.retrieval.visual.pooling import blob_to_image, mean_pool_rows_cols


def test_mean_pool_rows_cols_shapes_with_special_tokens() -> None:
    torch = pytest.importorskip("torch")

    n_patches_x, n_patches_y, dim = 4, 3, 8
    n_special = 5
    n_image = n_patches_x * n_patches_y
    seq = n_image + n_special

    # Synthetic embedding of KNOWN shape [seq, dim]; honest labels, no model.
    emb = torch.arange(seq * dim, dtype=torch.float32).reshape(seq, dim)
    # First n_image tokens are image patches; the rest are special tokens.
    image_mask = torch.zeros(seq, dtype=torch.bool)
    image_mask[:n_image] = True

    pooled_rows, pooled_cols = mean_pool_rows_cols(
        emb, image_mask, n_patches_x, n_patches_y
    )

    # rows pooled over x -> [n_patches_y + n_special, dim]
    assert tuple(pooled_rows.shape) == (n_patches_y + n_special, dim)
    # cols pooled over y -> [n_patches_x + n_special, dim]
    assert tuple(pooled_cols.shape) == (n_patches_x + n_special, dim)


def test_mean_pool_rows_cols_derives_dim_from_emb() -> None:
    torch = pytest.importorskip("torch")

    n_patches_x, n_patches_y, dim = 2, 2, 16
    n_image = n_patches_x * n_patches_y
    emb = torch.ones(n_image, dim, dtype=torch.float32)
    image_mask = torch.ones(n_image, dtype=torch.bool)

    # dim is NOT supplied; it must be derived from emb.shape[-1].
    pooled_rows, pooled_cols = mean_pool_rows_cols(
        emb, image_mask, n_patches_x, n_patches_y
    )
    assert pooled_rows.shape[-1] == dim
    assert pooled_cols.shape[-1] == dim
    # No special tokens here, so shapes are exactly the pooled grid dims.
    assert tuple(pooled_rows.shape) == (n_patches_y, dim)
    assert tuple(pooled_cols.shape) == (n_patches_x, dim)


def test_blob_to_image_decodes_png_deterministically() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 14), color=(5, 6, 7)).save(buffer, format="PNG")
    blob = buffer.getvalue()

    image_a = blob_to_image(blob)
    image_b = blob_to_image(blob)

    assert image_a.mode == "RGB"
    assert image_a.size == (20, 14)
    # Identical bytes decode to identical size deterministically.
    assert image_a.size == image_b.size
