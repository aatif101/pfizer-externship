"""Pure, offline-safe pooling + blob-decode helpers for the visual tier.

Reads image bytes ONLY to decode them for embedding; exposes no bytes/text in
any return that gets traced or persisted. ``torch`` is imported lazily inside
``mean_pool_rows_cols`` so importing this module stays offline-safe even when
torch is not installed (Pillow is a hard dependency, so ``blob_to_image`` always
works). No function loads a model or asserts a similarity score — shape math and
deterministic decoding only (metric-integrity rule).
"""
from __future__ import annotations


def blob_to_image(image_blob: bytes) -> "object":
    """Decode a stored ``pages.image_blob`` PNG byte string to a PIL RGB image.

    The stored blob is the reproducible 150-DPI PNG written by the rasterizer, so
    decoding is deterministic: identical bytes yield identical image size/mode.
    """
    import io

    from PIL import Image

    return Image.open(io.BytesIO(image_blob)).convert("RGB")


def mean_pool_rows_cols(
    emb: "object",
    image_mask: "object",
    n_patches_x: int,
    n_patches_y: int,
    dim: int | None = None,
) -> tuple["object", "object"]:
    """Reduce a full page multivector to row- and column-pooled multivectors.

    Pure tensor reshape (no model load, no similarity score). ``emb`` is an
    already-computed ``[seq, dim]`` embedding; ``image_mask`` is a ``[seq]`` bool
    selecting the ``n_patches_x * n_patches_y`` image-patch tokens. The grid is
    mean-pooled over rows and columns, then the non-image (special / query-
    augmentation) tokens are concatenated onto each pooled multivector per the
    Qdrant ColPali pattern. ``dim`` is derived from ``emb.shape[-1]`` when not
    supplied (RESEARCH Assumption A2).

    Returns ``(pooled_rows, pooled_cols)`` with shapes
    ``[n_patches_y + n_special, dim]`` and ``[n_patches_x + n_special, dim]``.
    """
    import torch

    resolved_dim = dim if dim is not None else emb.shape[-1]

    image_part = emb[image_mask]
    patches = image_part.view(n_patches_x, n_patches_y, resolved_dim)
    pooled_rows = patches.mean(dim=0)  # [n_patches_y, dim]
    pooled_cols = patches.mean(dim=1)  # [n_patches_x, dim]

    special = emb[~image_mask]  # non-image tokens, [n_special, dim]
    pooled_rows = torch.cat([pooled_rows, special])
    pooled_cols = torch.cat([pooled_cols, special])
    return pooled_rows, pooled_cols
