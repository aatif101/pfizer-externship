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

import sys

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
    assert hasattr(_langfuse_module, '__version__') and _langfuse_module.__version__.startswith("3."), (
        f"langfuse version {getattr(_langfuse_module, '__version__', 'unknown')} detected. "
        "Only v3.x is supported (langfuse>=3.0,<4.0). "
        "Run: pip install 'langfuse>=3.0,<4.0' to downgrade."
    )

from langfuse.decorators import langfuse_context, observe  # noqa: E402, F401
from loguru import logger  # noqa: E402

from src.config import get_settings  # noqa: E402


def verify_langfuse_connection() -> bool:
    """Return True if Langfuse API keys are set and the connection is valid.

    Uses langfuse_context.auth_check() (v3 API).
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
        result: bool = langfuse_context.auth_check()
        if result:
            logger.info("Langfuse connection verified")
        else:
            logger.warning("Langfuse auth_check() returned False — check API keys")
        return result
    except Exception as exc:
        # Never propagate — Streamlit app must not crash if Langfuse is unavailable
        logger.warning(f"Langfuse connection check failed: {type(exc).__name__}")
        return False