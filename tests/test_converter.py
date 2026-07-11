"""Lifecycle regression tests for the public Docling conversion boundary."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_converter_module_import_remains_offline_safe() -> None:
    """Importing the boundary must not eagerly import Docling or Torch."""
    repo_root = Path(__file__).resolve().parents[1]
    probe = r'''
import builtins

real_import = builtins.__import__


def reject_heavy_imports(name, *args, **kwargs):
    if name == "torch" or name.startswith("docling"):
        raise AssertionError(f"eager heavy import: {name}")
    return real_import(name, *args, **kwargs)


builtins.__import__ = reject_heavy_imports
from src.pipeline.converter import convert_pdf
print(convert_pdf.__name__)
'''

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "convert_pdf"


def test_convert_pdf_initializes_heavy_pipeline_once_per_process() -> None:
    """One cold construction must serve every steady-state ``convert_pdf`` call."""
    repo_root = Path(__file__).resolve().parents[1]
    probe = r'''
import json
import sys
import types


def install_module(name):
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


torch = install_module("torch")
torch.cuda = types.SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None)

docling = install_module("docling")
docling.__path__ = []
datamodel = install_module("docling.datamodel")
datamodel.__path__ = []
base_models = install_module("docling.datamodel.base_models")
pipeline_options = install_module("docling.datamodel.pipeline_options")
vlm_model_specs = install_module("docling.datamodel.vlm_model_specs")
document_converter = install_module("docling.document_converter")
pipeline = install_module("docling.pipeline")
pipeline.__path__ = []
vlm_pipeline = install_module("docling.pipeline.vlm_pipeline")


class InputFormat:
    PDF = "pdf"


class VlmPipelineOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class PdfFormatOption:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class VlmPipeline:
    pass


class DocumentConverter:
    constructions = 0
    sources = []

    def __init__(self, **kwargs):
        type(self).constructions += 1
        self.kwargs = kwargs

    def convert(self, *, source):
        type(self).sources.append(source)
        return {"source": source}


base_models.InputFormat = InputFormat
pipeline_options.VlmPipelineOptions = VlmPipelineOptions
vlm_model_specs.GRANITEDOCLING_TRANSFORMERS = "granite"
datamodel.vlm_model_specs = vlm_model_specs
document_converter.DocumentConverter = DocumentConverter
document_converter.PdfFormatOption = PdfFormatOption
vlm_pipeline.VlmPipeline = VlmPipeline

from src.pipeline.converter import convert_pdf

results = [convert_pdf(path) for path in ("one.pdf", "two.pdf", "three.pdf")]
print(json.dumps({
    "constructions": DocumentConverter.constructions,
    "sources": DocumentConverter.sources,
    "results": results,
}))
'''

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout.strip().splitlines()[-1])

    assert report == {
        "constructions": 1,
        "sources": ["one.pdf", "two.pdf", "three.pdf"],
        "results": [
            {"source": "one.pdf"},
            {"source": "two.pdf"},
            {"source": "three.pdf"},
        ],
    }
