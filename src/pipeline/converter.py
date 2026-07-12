"""Docling VlmPipeline wrapper.

CRITICAL RULES:
- Lazily reuse one DocumentConverter per process so Docling initializes VLM weights once.
- Do NOT use generate_page_images option (Pitfall C2 — broken in VlmPipeline, GitHub #2416).
- Page images are handled by rasterizer.py (pypdfium2).
- Collect transient objects and release unused CUDA cache after each conversion.
"""
from __future__ import annotations

import gc
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from docling.document_converter import ConversionResult, DocumentConverter


def _build_vlm_options():
    """Build Granite Docling options using the current API with a narrow fallback."""

    try:
        from docling.datamodel.pipeline_options import VlmConvertOptions  # noqa: PLC0415
    except (ImportError, AttributeError):
        from docling.datamodel import vlm_model_specs  # noqa: PLC0415

        return vlm_model_specs.GRANITEDOCLING_TRANSFORMERS

    if not hasattr(VlmConvertOptions, "from_preset"):
        from docling.datamodel import vlm_model_specs  # noqa: PLC0415

        return vlm_model_specs.GRANITEDOCLING_TRANSFORMERS

    # Keep the supported API explicit and fail loudly if a present modern
    # registry cannot resolve its own built-in preset.
    options = VlmConvertOptions.from_preset("granite_docling")

    # Preserve a deterministic engine choice across CPU and GPU demo hosts.
    # The named preset remains the source of the model/generation contract.
    if hasattr(options, "engine_options"):
        try:
            from docling.datamodel.vlm_engine_options import (  # noqa: PLC0415
                TransformersVlmEngineOptions,
            )
        except (ImportError, AttributeError):
            pass
        else:
            options.engine_options = TransformersVlmEngineOptions()
    return options


@cache
def _get_converter() -> "DocumentConverter":
    """Build the process-scoped Docling converter on first use."""
    from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
    from docling.datamodel.pipeline_options import VlmPipelineOptions  # noqa: PLC0415
    from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: PLC0415
    from docling.pipeline.vlm_pipeline import VlmPipeline  # noqa: PLC0415

    pipeline_options = VlmPipelineOptions(
        vlm_options=_build_vlm_options(),
        # NOTE: generate_page_images intentionally omitted — broken in VlmPipeline (issue #2416)
        # Page rasterization is handled by rasterizer.py using pypdfium2
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=VlmPipeline,
                pipeline_options=pipeline_options,
            ),
        }
    )


def convert_pdf(pdf_path: str) -> "ConversionResult":
    """Run Docling VlmPipeline, reusing its heavyweight model across calls."""
    converter = _get_converter()
    filename = Path(pdf_path).name
    try:
        logger.debug(f"Starting Docling conversion: {filename}")
        result = converter.convert(source=pdf_path)
        logger.debug(f"Docling conversion complete: {filename}")
        return result
    finally:
        gc.collect()
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
