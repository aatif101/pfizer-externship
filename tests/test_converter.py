"""Lifecycle regression tests for the public Docling conversion boundary."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from loguru import logger


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


class VlmConvertOptions:
    @classmethod
    def from_preset(cls, preset):
        return {"preset": preset}


class PdfFormatOption:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class VlmPipeline:
    pass


class DocumentConverter:
    constructions = 0
    sources = []
    last_kwargs = None

    def __init__(self, **kwargs):
        type(self).constructions += 1
        type(self).last_kwargs = kwargs
        self.kwargs = kwargs

    def convert(self, *, source):
        type(self).sources.append(source)
        return {"source": source}


base_models.InputFormat = InputFormat
pipeline_options.VlmPipelineOptions = VlmPipelineOptions
pipeline_options.VlmConvertOptions = VlmConvertOptions
vlm_model_specs.GRANITEDOCLING_TRANSFORMERS = "granite"
datamodel.vlm_model_specs = vlm_model_specs
document_converter.DocumentConverter = DocumentConverter
document_converter.PdfFormatOption = PdfFormatOption
vlm_pipeline.VlmPipeline = VlmPipeline

from src.pipeline.converter import convert_pdf

results = [convert_pdf(path) for path in ("one.pdf", "two.pdf", "three.pdf")]
configured = DocumentConverter.last_kwargs["format_options"]["pdf"].kwargs["pipeline_options"].kwargs["vlm_options"]
print(json.dumps({
    "constructions": DocumentConverter.constructions,
    "sources": DocumentConverter.sources,
    "results": results,
    "configured_vlm_options": configured,
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
        "configured_vlm_options": {"preset": "granite_docling"},
    }


def test_build_vlm_options_uses_current_named_preset(monkeypatch) -> None:
    import sys
    import types

    from src.pipeline import converter

    calls: list[str] = []
    module = types.ModuleType("docling.datamodel.pipeline_options")

    class VlmConvertOptions:
        @classmethod
        def from_preset(cls, preset: str):
            calls.append(preset)
            return "modern-options"

    module.VlmConvertOptions = VlmConvertOptions
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", module)
    assert converter._build_vlm_options() == "modern-options"
    assert calls == ["granite_docling"]


def test_build_vlm_options_keeps_transformers_engine_for_reproducibility(monkeypatch) -> None:
    import sys
    import types

    from src.pipeline import converter

    pipeline_module = types.ModuleType("docling.datamodel.pipeline_options")
    engine_module = types.ModuleType("docling.datamodel.vlm_engine_options")

    class Options:
        engine_options = "auto"

    options = Options()

    class VlmConvertOptions:
        @classmethod
        def from_preset(cls, _preset: str):
            return options

    class TransformersVlmEngineOptions:
        pass

    pipeline_module.VlmConvertOptions = VlmConvertOptions
    engine_module.TransformersVlmEngineOptions = TransformersVlmEngineOptions
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel.vlm_engine_options", engine_module)

    assert converter._build_vlm_options() is options
    assert isinstance(options.engine_options, TransformersVlmEngineOptions)


def test_build_vlm_options_falls_back_only_when_modern_api_absent(monkeypatch) -> None:
    import sys
    import types

    from src.pipeline import converter

    options_module = types.ModuleType("docling.datamodel.pipeline_options")
    specs_module = types.ModuleType("docling.datamodel.vlm_model_specs")
    specs_module.GRANITEDOCLING_TRANSFORMERS = "legacy-options"
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", options_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel.vlm_model_specs", specs_module)
    assert converter._build_vlm_options() == "legacy-options"


def test_build_vlm_options_does_not_hide_broken_modern_registry(monkeypatch) -> None:
    import sys
    import types

    from src.pipeline import converter

    module = types.ModuleType("docling.datamodel.pipeline_options")

    class VlmConvertOptions:
        @classmethod
        def from_preset(cls, _preset: str):
            raise KeyError("registry broken")

    module.VlmConvertOptions = VlmConvertOptions
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", module)
    with pytest.raises(KeyError, match="registry broken"):
        converter._build_vlm_options()


def test_converter_logs_basename_without_absolute_path(monkeypatch, caplog, tmp_path: Path) -> None:
    from src.pipeline import converter

    class FakeConverter:
        def convert(self, *, source):
            return source

    monkeypatch.setattr(converter, "_get_converter", lambda: FakeConverter())
    absolute = tmp_path / "private" / "supplier.pdf"
    sink_id = logger.add(caplog.handler, format="{message}", level="DEBUG")
    try:
        assert converter.convert_pdf(str(absolute)) == str(absolute)
    finally:
        logger.remove(sink_id)
    assert "supplier.pdf" in caplog.text
    if str(absolute) in caplog.text:
        pytest.fail("converter log exposed an absolute source path")
