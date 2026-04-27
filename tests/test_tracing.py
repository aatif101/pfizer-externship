"""Tests for src/tracing.py — Langfuse v3 wiring."""
from __future__ import annotations

import importlib

import langfuse  # noqa: PLC0415
import pytest
from src.tracing import verify_langfuse_connection  # noqa: PLC0415


def test_langfuse_v3_pinned() -> None:
    """Langfuse must be pinned to v3 (langfuse.__version__ starts with '3.')."""
    assert langfuse.__version__.startswith("3."), (
        f"langfuse version {langfuse.__version__!r} is not v3. "
        "Upgrade to v4 is prohibited — pin langfuse>=3.0,<4.0."
    )


def test_langfuse_import_paths() -> None:
    """v3 import paths must be resolvable."""
    from langfuse.decorators import langfuse_context, observe  # noqa: PLC0415,F401

    assert callable(observe), "langfuse.decorators.observe must be callable"
    assert langfuse_context is not None, "langfuse_context must be importable"


def test_tracing_module_imports() -> None:
    """src/tracing.py must be importable without error."""
    import src.tracing  # noqa: PLC0415,F401


def test_verify_langfuse_connection_callable() -> None:
    """verify_langfuse_connection() must be exported and callable."""
    assert callable(verify_langfuse_connection)
    # Result may be True or False depending on env — we only check it doesn't raise
    result = verify_langfuse_connection()
    assert isinstance(result, bool)