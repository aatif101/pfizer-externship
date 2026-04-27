"""Tests for src/tracing.py — Langfuse v3 wiring."""
from __future__ import annotations

import importlib

import langfuse  # noqa: PLC0415
from importlib.metadata import version
import pytest
from src.tracing import verify_langfuse_connection  # noqa: PLC0415


def test_langfuse_v3_pinned() -> None:
    """Langfuse must be pinned to v3 (langfuse version starts with '3.')."""
    langfuse_version = version('langfuse')
    assert langfuse_version.startswith("3."), (
        f"langfuse version {langfuse_version!r} is not v3. "
        "Upgrade to v4 is prohibited — pin langfuse>=3.0,<4.0."
    )


def test_langfuse_import_paths() -> None:
    """v3 import paths must be resolvable."""
    from langfuse import observe, get_client  # noqa: PLC0415,F401

    assert callable(observe), "langfuse.observe must be callable"
    assert get_client is not None, "get_client must be importable"


def test_tracing_module_imports() -> None:
    """src/tracing.py must be importable without error."""
    import src.tracing  # noqa: PLC0415,F401


def test_verify_langfuse_connection_callable() -> None:
    """verify_langfuse_connection() must be exported and callable."""
    assert callable(verify_langfuse_connection)
    # Result may be True or False depending on env — we only check it doesn't raise
    result = verify_langfuse_connection()
    assert isinstance(result, bool)