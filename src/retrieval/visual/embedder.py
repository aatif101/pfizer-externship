"""Lazy-import GPU seam for the ColQwen2.5 page-image embedder.

Importing this module is offline-safe: it imports neither ``torch`` nor
``colpali_engine`` at module load. All heavy SDK imports live inside function
bodies, mirroring ``src.eval.ragas_quality`` (the project's canonical lazy-import
seam for a heavy/optional dependency).

This loads the REAL ColQwen2.5 model — it never mocks or fabricates embeddings
(metric-integrity rule, 05-CONTEXT.md §"No fabrication"). The functions here are
EXECUTED only on a GPU (the Colab L4 notebook); no offline test asserts a quality
metric off them. Offline tests assert ONLY that the module imports without the
heavy deps and that ``load_colqwen`` raises ``ImportError`` when the deps are
absent (proving no module-top heavy import).

Privacy boundary: this module reads image bytes ONLY to embed them; it returns
embedding tensors for in-memory upsert and never persists or traces image bytes
or page text.
"""
from __future__ import annotations

from collections.abc import Sequence

# The locked model checkpoint (CLAUDE.md / 05-CONTEXT.md): Qwen2.5-VL-3B backbone,
# dynamic resolution up to 768 patches, ColBERT-style multivector output.
DEFAULT_MODEL_ID = "vidore/colqwen2.5-v0.2"


def load_colqwen(
    model_id: str = DEFAULT_MODEL_ID,
    *,
    dtype: str = "bfloat16",
    device: str = "cuda:0",
) -> tuple["object", "object"]:
    """Load the REAL ColQwen2.5 model + processor (GPU/notebook execution only).

    ``torch`` and ``colpali_engine`` are imported lazily INSIDE this function body,
    so importing this module stays offline-safe. Calling this function WITHOUT the
    pinned stack installed raises ``ImportError`` (the lazy seam guarantees the
    heavy deps are never required just to import the module).

    Returns ``(model, processor)`` where ``model`` is loaded in ``dtype`` (bf16 on
    L4) on ``device`` and set to ``.eval()``. Never fabricates a model — the real
    weights are downloaded from Hugging Face on first call (vidore/colqwen2.5-v0.2).
    """
    import torch
    from colpali_engine.models import ColQwen2_5, ColQwen2_5_Processor

    model = ColQwen2_5.from_pretrained(
        model_id,
        torch_dtype=getattr(torch, dtype),
        device_map=device,
    ).eval()
    processor = ColQwen2_5_Processor.from_pretrained(model_id)
    return model, processor


def embed_images(model: "object", processor: "object", images: Sequence["object"]) -> "object":
    """Embed a batch of PIL page images into ColBERT multivectors (GPU only).

    Mirrors RESEARCH Pattern 1: ``processor.process_images(images).to(model.device)``
    then a ``torch.no_grad()`` forward pass. Returns the ``[B, seq, dim]`` image
    embedding tensor. ``torch`` is lazy-imported inside the body. The batch object
    is also returned-by-reference via the processor for downstream patch-grid
    masking (see ``pooled_vectors_for_image``).
    """
    import torch

    batch_images = processor.process_images(list(images)).to(model.device)
    with torch.no_grad():
        image_embeddings = model(**batch_images)
    return image_embeddings


def embed_queries(model: "object", processor: "object", queries: Sequence[str]) -> "object":
    """Embed a batch of text queries into ColBERT multivectors (GPU only).

    Mirrors RESEARCH Pattern 1 for the query side:
    ``processor.process_queries(queries).to(model.device)`` then a
    ``torch.no_grad()`` forward pass. Returns the ``[B, seq, dim]`` query embedding
    tensor used as the Qdrant two-stage query vector.
    """
    import torch

    batch_queries = processor.process_queries(list(queries)).to(model.device)
    with torch.no_grad():
        query_embeddings = model(**batch_queries)
    return query_embeddings


def process_image_batch(processor: "object", images: Sequence["object"]) -> "object":
    """Build the processor batch for a set of images (for mask + n_patches reuse).

    Returned so the caller can pass the SAME batch object to both the model forward
    pass and ``processor.get_image_mask(...)`` / ``processor.get_n_patches(...)``,
    which need the batch's pixel-grid metadata (RESEARCH Pattern 2). GPU/notebook
    only.
    """
    return processor.process_images(list(images))


def pooled_vectors_for_image(
    model: "object",
    processor: "object",
    batch_images: "object",
    image_embeddings: "object",
    i: int,
    image_size: tuple[int, int],
) -> tuple["object", "object"]:
    """Derive the row/column mean-pooled multivectors for the i-th image (GPU only).

    Computes the per-image dynamic patch grid via
    ``processor.get_n_patches(image_size, ...)`` and the patch token mask via
    ``processor.get_image_mask(batch_images)`` (RESEARCH Pattern 2), then DELEGATES
    the reshape/pooling to the pure ``pooling.mean_pool_rows_cols`` helper (Plan 02)
    so the pooling math is the SAME offline-tested code. ``dim`` is derived from
    ``image_embeddings[i].shape[-1]`` (RESEARCH Assumption A2) — never hardcoded.

    Returns ``(pooled_rows, pooled_cols)``. This is a real tensor reshape over a
    real embedding; it never fabricates a similarity score.
    """
    from src.retrieval.visual.pooling import mean_pool_rows_cols

    # Per-image dynamic grid (handles ColQwen2.5's dynamic resolution).
    n_patches_x, n_patches_y = processor.get_n_patches(
        image_size=image_size,
        patch_size=model.patch_size,
        spatial_merge_size=model.spatial_merge_size,
    )
    image_mask = processor.get_image_mask(batch_images)

    emb = image_embeddings[i]
    mask = image_mask[i]
    dim = emb.shape[-1]  # A2: derive dim from the embedding, do not assume 128
    return mean_pool_rows_cols(emb, mask, n_patches_x, n_patches_y, dim)


__all__ = [
    "DEFAULT_MODEL_ID",
    "load_colqwen",
    "embed_images",
    "embed_queries",
    "process_image_batch",
    "pooled_vectors_for_image",
]
