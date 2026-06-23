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
