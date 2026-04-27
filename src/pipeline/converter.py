"""Docling VlmPipeline wrapper.

CRITICAL RULES:
- Recreate DocumentConverter per document (Pitfall C3 — memory leak mitigation).
- Do NOT use generate_page_images option (Pitfall C2 — broken in VlmPipeline, GitHub #2416).
- Page images are handled by rasterizer.py (pypdfium2).
- Call del converter + gc.collect() + torch.cuda.empty_cache() after each conversion.
"""
from __future__ import annotations

import gc
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from docling.document_converter import ConversionResult


def convert_pdf(pdf_path: str) -> "ConversionResult":
    """Run Docling VlmPipeline on a single PDF. Recreates converter per call (C3 mitigation)."""
    import torch  # noqa: PLC0415 — deferred import; heavy dep
    from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
    from docling.datamodel import vlm_model_specs  # noqa: PLC0415
    from docling.datamodel.pipeline_options import VlmPipelineOptions  # noqa: PLC0415
    from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: PLC0415
    from docling.pipeline.vlm_pipeline import VlmPipeline  # noqa: PLC0415

    pipeline_options = VlmPipelineOptions(
        vlm_options=vlm_model_specs.GRANITEDOCLING_TRANSFORMERS,
        # NOTE: generate_page_images intentionally omitted — broken in VlmPipeline (issue #2416)
        # Page rasterization is handled by rasterizer.py using pypdfium2
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=VlmPipeline,
                pipeline_options=pipeline_options,
            ),
        }
    )
    try:
        logger.debug(f"Starting Docling conversion: {pdf_path}")
        result = converter.convert(source=pdf_path)
        logger.debug(f"Docling conversion complete: {pdf_path}")
        return result
    finally:
        del converter
        gc.collect()
        try:
            import torch  # noqa: PLC0415
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass