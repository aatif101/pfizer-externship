"""Langfuse v3 observability module for the Pfizer SDF pipeline.

CRITICAL VERSION CONSTRAINT:
    langfuse>=3.9,<4.0 (propagate_attributes). v4 has breaking import path changes.
    This file asserts the version at import time to catch accidental upgrades.

v3 import paths (DO NOT change):
    from langfuse import observe, get_client                    ← v3 ✓
    get_client().update_current_trace(...)                      ← v3 ✓
    get_client().auth_check()                                   ← v3 ✓

Dead v2 path (DO NOT USE anywhere): the legacy "decorators" submodule
(`from langfuse import decorators` style imports of langfuse_context/observe)
does not exist under installed v3 and raises ModuleNotFoundError.

D-04: Trace each major function: PDF ingestion, text extraction, storage, retrieval.
      Functions are decorated with @observe in their respective pipeline modules.
      This module provides the client init and connection verification.
"""
from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
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
    from langfuse import Langfuse as _Langfuse, observe, get_client  # noqa: E402, F401
    _LANGFUSE_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when optional Langfuse is absent/broken
    _LANGFUSE_AVAILABLE = False

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


# Phase 6 (OBS-01): every trace session carries a phase tag.
PHASE_TAGS: dict[str, str] = {"linear": "phase1", "agentic": "phase2"}
_CURRENT_PHASE: ContextVar[str | None] = ContextVar("pfizer_trace_phase", default=None)
_SESSION_METADATA_KEYS: frozenset[str] = frozenset({"pipeline", "entry_point", "command"})

# Test seams. When None, resolved lazily from the Langfuse SDK inside a try/except.
_propagate_attributes_factory: Callable[..., Any] | None = None
_callback_handler_factory: Callable[[], Any] | None = None


def current_phase() -> str | None:
    """Return the phase tag of the active ``trace_session`` (None outside a session)."""
    return _CURRENT_PHASE.get()


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


def _ordered_unique_tags(tags: Iterable[Any]) -> list[str]:
    """Return safe string tags in first-occurrence order with duplicates removed."""
    ordered: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            continue
        safe_tag = _safe_trace_value(tag)
        if not isinstance(safe_tag, str) or not safe_tag or safe_tag in seen:
            continue
        seen.add(safe_tag)
        ordered.append(safe_tag)
    return ordered


def _ensure_langfuse_initialized() -> bool:
    """Initialize the global Langfuse client from Settings if keys are present.

    pydantic_settings reads .env into Python objects but does NOT set os.environ,
    so Langfuse's default env-var lookup finds nothing. Explicitly constructing
    Langfuse() with settings values bridges the gap without touching os.environ.
    Idempotent: re-initializing the same keys is harmless in langfuse v3.
    """
    if not _LANGFUSE_AVAILABLE:
        return False
    settings = get_settings()
    if not settings.langfuse_enabled:
        return False
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return False
    try:
        _Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return True
    except Exception:
        return False


def _get_langfuse_context() -> Any | None:
    """Return the live Langfuse v3 client lazily; None when the SDK is unavailable."""
    _ensure_langfuse_initialized()
    try:
        client = get_client()
    except Exception:
        return None
    return client


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

    phase = current_phase()
    if phase:
        safe_tags = _ordered_unique_tags([phase, *safe_tags])

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


def _resolve_propagate_attributes() -> Callable[..., Any] | None:
    if _propagate_attributes_factory is not None:
        return _propagate_attributes_factory
    try:
        from langfuse import propagate_attributes  # noqa: PLC0415

        return propagate_attributes
    except Exception:
        return None


def _build_propagate_context(
    *,
    tags: list[str],
    session_id: str | None,
    metadata: dict[str, str],
) -> Any:
    """Build a Langfuse propagate_attributes context, or a nullcontext on any failure."""
    try:
        if not _ensure_langfuse_initialized():
            return nullcontext()
        factory = _resolve_propagate_attributes()
        if factory is None:
            return nullcontext()
        kwargs: dict[str, Any] = {"tags": tags, "metadata": metadata}
        if session_id:
            safe_session = _safe_trace_value(session_id) if isinstance(session_id, str) else None
            if isinstance(safe_session, str) and safe_session:
                kwargs["session_id"] = safe_session
        ctx = factory(**kwargs)
        if ctx is None or not hasattr(ctx, "__enter__") or not hasattr(ctx, "__exit__"):
            return nullcontext()
        return ctx
    except Exception:
        return nullcontext()


@contextmanager
def trace_session(
    *,
    phase: str,
    session_id: str | None = None,
    tags: Iterable[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> Iterator[None]:
    """Open a phase-tagged Langfuse v3 trace session around an entry point.

    Sets the active phase (so every ``safe_update_current_trace`` carries it) and, when
    Langfuse is enabled with keys, enters ``propagate_attributes`` with tags
    ``[phase, *tags]`` (deduplicated), ``metadata={"phase": phase, ...allowlisted}`` and
    ``session_id``. Tracing failures never raise; only exceptions from the with-body do.
    """
    token = None
    try:
        token = _CURRENT_PHASE.set(phase if isinstance(phase, str) and phase else None)
    except Exception:
        token = None

    try:
        session_tags = _ordered_unique_tags([phase, *(tags or ())])
    except Exception:
        session_tags = []
    try:
        extra = filter_trace_metadata(metadata, _SESSION_METADATA_KEYS)
        session_metadata = {"phase": str(phase), **{k: str(v) for k, v in extra.items()}}
    except Exception:
        session_metadata = {"phase": str(phase)}

    ctx = _build_propagate_context(tags=session_tags, session_id=session_id, metadata=session_metadata)
    entered = False
    try:
        ctx.__enter__()
        entered = True
    except Exception:
        entered = False

    try:
        yield
    except BaseException as body_exc:
        if entered:
            try:
                ctx.__exit__(type(body_exc), body_exc, body_exc.__traceback__)
            except Exception:
                pass
            entered = False
        raise
    finally:
        if entered:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass
        if token is not None:
            try:
                _CURRENT_PHASE.reset(token)
            except Exception:
                pass


def _resolve_callback_handler_factory() -> Callable[[], Any] | None:
    if _callback_handler_factory is not None:
        return _callback_handler_factory
    try:
        from langfuse.langchain import CallbackHandler  # noqa: PLC0415

        return CallbackHandler
    except Exception:
        return None


def build_callback_handler() -> Any | None:
    """Return a Langfuse LangChain CallbackHandler for LangGraph, or None.

    Only built when tracing is enabled and keys are present. Never raises.
    """
    try:
        if not _ensure_langfuse_initialized():
            return None
        factory = _resolve_callback_handler_factory()
        if factory is None:
            return None
        return factory()
    except Exception:
        return None


def flush_traces() -> bool:
    """Flush buffered Langfuse spans (Streamlit handlers). Returns False on any failure."""
    if not _LANGFUSE_AVAILABLE:
        return False
    try:
        get_client().flush()
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

    _ensure_langfuse_initialized()
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