"""Shared Streamlit-only UI helpers for consistent dashboard presentation.

This module is intentionally presentation-only:
- No database access
- No provider / tracing imports

Keep helpers dependency-free beyond Streamlit and the stdlib.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st


def render_tab_header(title: str, caption: str | None = None) -> None:
    """Render a consistent tab title + optional caption."""

    st.header(title)
    if caption:
        st.caption(caption)


def render_section_divider() -> None:
    """Render a consistent divider between major sections."""

    st.divider()


def render_empty_state(message: str, *, caption: str | None = None) -> None:
    """Render a consistent empty-state callout."""

    st.info(message)
    if caption:
        st.caption(caption)


def format_percent(value: Any, *, digits: int = 0, unknown: str = "Unknown") -> str:
    if value is None:
        return unknown
    try:
        return f"{float(value):.{digits}%}"
    except (TypeError, ValueError):
        return unknown


def format_float(value: Any, *, digits: int = 3, unknown: str = "") -> str:
    if value is None:
        return unknown
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return unknown


def format_datetimeish(value: Any, *, unknown: str = "") -> str:
    """Format datetimes and datetime-like strings safely.

    - datetime -> ISO-ish local display
    - isoformat-ish strings -> pass through trimmed
    - everything else -> ""

    This is presentation-only; parsing is intentionally conservative.
    """

    if value is None:
        return unknown

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds")

    text = str(value).strip()
    if not text:
        return unknown

    # If it's already an ISO-ish datetime string, keep it readable.
    # We avoid dateutil/regex parsing to keep this module dependency-free.
    if "T" in text or "-" in text or "/" in text:
        return text

    return unknown
