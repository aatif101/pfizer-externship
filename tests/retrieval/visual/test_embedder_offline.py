"""Offline structural tests for the ColQwen2.5 embedder lazy-import seam.

These tests assert the SEAM SHAPE only — that the module imports with no
torch/colpali installed and that ``load_colqwen`` raises ``ImportError`` when the
heavy deps are absent (proving no module-top heavy import). They NEVER fabricate
an embedding or assert a recall/ndcg/similarity number — the real numbers come
only from the Colab L4 GPU run (metric-integrity rule, 05-CONTEXT.md
§"No fabrication"). Any model-execution test carries ``@pytest.mark.gpu`` so it is
skipped offline.
"""
from __future__ import annotations

import importlib

import pytest


def test_embedder_module_imports_without_heavy_deps() -> None:
    """The module imports offline with neither torch nor colpali_engine installed.

    A successful import proves all heavy SDK imports live INSIDE function bodies
    (the lazy-import seam), not at module top.
    """
    module = importlib.import_module("src.retrieval.visual.embedder")
    assert module.DEFAULT_MODEL_ID == "vidore/colqwen2.5-v0.2"
    # The seam exposes the GPU functions as plain callables even offline.
    for name in (
        "load_colqwen",
        "embed_images",
        "embed_queries",
        "pooled_vectors_for_image",
    ):
        assert callable(getattr(module, name))


def test_no_module_top_heavy_imports() -> None:
    """No ``import torch`` / ``import colpali`` appears at module top level.

    Reads the source text and asserts the heavy-dep import lines are indented
    (inside a function body), never at column 0 (module top).
    """
    from pathlib import Path

    source = Path("src/retrieval/visual/embedder.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import torch") or stripped.startswith("from colpali_engine"):
            # A top-level import would start at column 0 (no leading whitespace).
            assert line != stripped, f"heavy import must be lazy (indented), got: {line!r}"


def test_load_colqwen_raises_importerror_when_deps_absent() -> None:
    """Calling ``load_colqwen`` with the pinned stack absent raises ImportError.

    This proves the heavy deps are loaded lazily ON CALL — not at import — so the
    module stays offline-importable while the real model load still requires the
    GPU stack. If torch/colpali happen to be installed in this environment, skip
    (we never fabricate a model load).
    """
    torch_spec = importlib.util.find_spec("torch")
    colpali_spec = importlib.util.find_spec("colpali_engine")
    if torch_spec is not None and colpali_spec is not None:
        pytest.skip("torch + colpali_engine are installed; the absent-deps path is GPU-only")

    from src.retrieval.visual.embedder import load_colqwen

    with pytest.raises(ImportError):
        load_colqwen()


@pytest.mark.gpu
def test_embed_one_image_shape_smoke() -> None:
    """GPU smoke: load the real model and confirm the per-token embedding dim.

    Skipped offline (``@pytest.mark.gpu``). On a CUDA box this loads the REAL
    ColQwen2.5 and embeds one image, asserting the embedding has a trailing
    per-token dim (RESEARCH A1) — NOT a quality metric. Kept here so the seam is
    exercised end-to-end only where a GPU exists; the metrics live in the notebook.
    """
    pytest.importorskip("torch")
    pytest.importorskip("colpali_engine")
    import torch

    if not torch.cuda.is_available():
        pytest.skip("no CUDA device available")

    from PIL import Image

    from src.retrieval.visual.embedder import embed_images, load_colqwen

    model, processor = load_colqwen()
    image = Image.new("RGB", (256, 256), color="white")
    embeddings = embed_images(model, processor, [image])
    assert embeddings.shape[-1] > 0  # per-token dim exists (expect 128); no metric asserted
