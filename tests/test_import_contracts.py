"""Import-time isolation checks for ordinary application modules."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.phase3_required

ROOT = Path(__file__).resolve().parents[1]


def test_ordinary_imports_construct_no_provider_or_model_clients() -> None:
    script = r'''
import importlib
from unittest.mock import patch

import google.genai as genai

modules = [
    "src.config",
    "src.extraction.gemini",
    "src.extraction.pipeline",
    "src.rag.gemini",
    "src.rag.service",
    "src.retrieval.indexer",
    "src.retrieval.retriever",
    "src.tracing",
]

with patch.object(genai, "Client", side_effect=AssertionError("provider client constructed during import")):
    for name in modules:
        importlib.import_module(name)
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_public_package_imports_do_not_load_heavy_model_modules() -> None:
    script = r'''
import importlib
import sys

for name in (
    "src.extraction",
    "src.rag",
    "src.retrieval",
    "src.retrieval.models",
):
    importlib.import_module(name)

for forbidden in ("torch", "transformers", "sentence_transformers", "colpali_engine"):
    assert forbidden not in sys.modules, forbidden
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
