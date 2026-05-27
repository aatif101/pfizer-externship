"""Langfuse v3 observability module for the Pfizer SDF pipeline.

CRITICAL VERSION CONSTRAINT:
    langfuse must be >=3.0,<4.0. v4 has breaking import path changes.
    This file asserts the version at import time to catch accidental upgrades.

v3 import paths (DO NOT change to v4 equivalents):
    from langfuse.decorators import langfuse_context, observe   ← v3 ✓
    from langfuse import Langfuse                               ← v3 ✓
    langfuse_context.auth_check()                               ← v3 ✓

v4 would look like (DO NOT USE):
    from langfuse.langchain import CallbackHandler              ← v4 ONLY
    langfuse.update_current_trace(...)                          ← v4 ONLY

D-04: Trace each major function: PDF ingestion, text extraction, storage, retrieval.
      Functions are decorated with @observe in their respective pipeline modules.
      This module provides the client init and connection verification.
"""
from __future__ import annotations

import math
import re
import sys
from collections.abc import Iterable, Mapping
from typing import Any

# Handle pydantic v1 compatibility issue with Python 3.14+
# This is a known issue with langfuse v3 on newer Python versions
try:
    import langfuse as _langfuse_module
except Exception as e:
    # If langfuse import fails due to pydantic v1 issues, we'll provide a mock
    _langfuse_module = None
    _import_error = e

# Version guard: fail loud at import time if langfuse v4 is accidentally installed
# Only check if import succeeded
if '_langfuse_module' in globals() and _langfuse_module is not None:
    version = None
    if hasattr(_langfuse_module, '__version__'):
        version = _langfuse_module.__version__
    else:
        # Try to get version from version module
        try:
            from langfuse.version import __version__ as version
        except ImportError:
            try:
                from importlib.metadata import version
                version = version('langfuse')
            except Exception:
                version = 'unknown'
    assert version and version.startswith("3."), (
        f"langfuse version {version} detected. "
        "Only v3.x is supported (langfuse>=3.0,<4.0). "
        "Run: pip install 'langfuse>=3.0,<4.0' to downgrade."
    )

try:
    from langfuse import observe, get_client  # noqa: E402, F401
except Exception:  # pragma: no cover - exercised only when optional Langfuse is absent/broken
    def observe(*decorator_args: Any, **decorator_kwargs: Any) -> Any:  # type: ignore[no-redef]
        """No-op replacement for langfuse.observe when Langfuse is unavailable."""
        if decorator_args and callable(decorator_args[0]) and not decorator_kwargs:
            return decorator_args[0]

        def _decorator(func: Any) -> Any:
            return func

        return _decorator

    def get_client() -> Any:  # type: ignore[no-redef]
        raise RuntimeError("Langfuse is unavailable")

from loguru import logger  # noqa: E402

from src.config import get_settings  # noqa: E402

_TRACE_VALUE_MAX_CHARS = 256
_TRACE_LIST_MAX_ITEMS = 20
_SECRET_VALUE_RE = re.compile(
    r"(api[_-]?key|secret|password|passwd|token|bearer\s+[a-z0-9._~+/=-]+|sk-[a-z0-9_-]+|pk-[a-z0-9_-]+)",
    re.IGNORECASE,
)


def _is_secret_like(value: str) -> bool:
    return bool(_SECRET_VALUE_RE.search(value))


def _bounded_string(value: str, *, max_chars: int = _TRACE_VALUE_MAX_CHARS) -> str | None:
    """Return a bounded string, or None when the value looks secret-bearing."""
    if _is_secret_like(value):
        return None
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}…[truncated:{len(value) - max_chars}]"


def _safe_trace_value(value: Any) -> Any | None:
    """Convert a metadata value to a bounded, safely representable scalar/list.

    Raw bytes, mappings, arbitrary objects, NaN/Inf floats, and secret-looking strings
    are dropped rather than stringified so provider payloads, page text containers, image
    blobs, or malformed objects cannot leak via repr().
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _bounded_string(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, Mapping):
        return None
    if isinstance(value, Iterable):
        safe_items: list[Any] = []
        for item in value:
            safe_item = _safe_trace_value(item)
            if safe_item is not None:
                safe_items.append(safe_item)
            if len(safe_items) >= _TRACE_LIST_MAX_ITEMS:
                break
        return safe_items
    return None


def filter_trace_metadata(metadata: Mapping[str, Any] | None, allowed_keys: set[str] | frozenset[str]) -> dict[str, Any]:
    """Return only allowlisted Langfuse metadata with bounded safe values."""
    if not metadata or not allowed_keys:
        return {}

    safe_metadata: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in allowed_keys:
            continue
        safe_value = _safe_trace_value(value)
        if safe_value is not None:
            safe_metadata[key] = safe_value
    return safe_metadata


def _get_langfuse_context() -> Any | None:
    """Import the v3 decorator context lazily so missing Langfuse is a no-op."""
    try:
        from langfuse.decorators import langfuse_context  # noqa: PLC0415
    except Exception:
        return None
    return langfuse_context


def safe_update_current_trace(
    *,
    tags: Iterable[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    allowed_metadata_keys: set[str] | frozenset[str] | None = None,
    context: Any | None = None,
) -> bool:
    """Safely update the current Langfuse v3 trace without leaking raw content.

    The helper is intentionally no-op safe: missing SDK/context, auth/backend issues,
    unavailable active trace state, malformed metadata, and update exceptions all return
    False instead of raising. Metadata is opt-in via ``allowed_metadata_keys`` and values
    are bounded/dropped before reaching Langfuse.
    """
    trace_context = context if context is not None else _get_langfuse_context()
    if trace_context is None or not hasattr(trace_context, "update_current_trace"):
        return False

    safe_metadata = filter_trace_metadata(metadata, allowed_metadata_keys or frozenset())
    safe_tags: list[str] = []
    if tags is not None:
        for tag in tags:
            safe_tag = _safe_trace_value(tag)
            if isinstance(safe_tag, str):
                safe_tags.append(safe_tag)

    if not safe_metadata and not safe_tags:
        return False

    update_kwargs: dict[str, Any] = {}
    if safe_tags:
        update_kwargs["tags"] = safe_tags
    if safe_metadata:
        update_kwargs["metadata"] = safe_metadata

    try:
        trace_context.update_current_trace(**update_kwargs)
    except Exception:
        return False
    return True


def verify_langfuse_connection() -> bool:
    """Return True if Langfuse API keys are set and the connection is valid.

    Uses get_client().auth_check() (v3 API).
    Returns False (never raises) when keys are absent or connection fails.

    Security: API keys are read from environment — never logged.
    """
    # If langfuse failed to import due to compatibility issues, return False
    if '_langfuse_module' not in globals() or _langfuse_module is None:
        logger.warning(f"Langfuse import failed: {_import_error}. Tracing disabled.")
        return False

    settings = get_settings()

    if not settings.langfuse_enabled:
        logger.info("Langfuse tracing disabled (LANGFUSE_ENABLED=false)")
        return False

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.info("Langfuse API keys not configured — tracing disabled")
        return False

    try:
        client = get_client()
        result: bool = client.auth_check()
        if result:
            logger.info("Langfuse connection verified")
        else:
            logger.warning("Langfuse auth_check() returned False — check API keys")
        return result
    except Exception as exc:
        # Never propagate — Streamlit app must not crash if Langfuse is unavailable
        logger.warning(f"Langfuse connection check failed: {type(exc).__name__}")
        return False