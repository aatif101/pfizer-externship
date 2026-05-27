"""Compliance dashboard data adapter and Streamlit renderer.

This module is intentionally credential-free: it only reads persisted SQLite
compliance rows and formats display-safe values for Streamlit. It must not call
provider or tracing runtime code.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import streamlit as st

from src.dashboard.ui import render_empty_state, render_section_divider, render_tab_header
from src.db.queries import get_page_image
from src.extraction.repository import list_compliance_records


_UNKNOWN_LABEL = "Unknown"
_BLANK_LABEL = ""
_MAX_DETAIL_TEXT_CHARS = 1_000
_TABLE_COLUMNS: tuple[str, ...] = (
    "risk_level_label",
    "compliance_status_label",
    "vendor_name",
    "doc_type",
    "manufacturing_date",
    "effective_date",
    "revision_date",
    "expiry_date",
    "age_days",
    "aggregate_confidence_display",
    "review_state_label",
    "needs_review_display",
    "source_page_label",
    "run_id",
    "trace_id",
)
_TABLE_COLUMN_LABELS: dict[str, str] = {
    "risk_level_label": "Risk",
    "compliance_status_label": "Status",
    "vendor_name": "Vendor",
    "doc_type": "Document Type",
    "manufacturing_date": "Manufacturing Date",
    "effective_date": "Effective Date",
    "revision_date": "Revision Date",
    "expiry_date": "Expiry Date",
    "age_days": "Age (Days)",
    "aggregate_confidence_display": "Confidence",
    "review_state_label": "Review State",
    "needs_review_display": "Review Flag",
    "source_page_label": "Source Page",
    "run_id": "Run ID",
    "trace_id": "Trace ID",
}
_RISK_ORDER: tuple[str, ...] = ("red", "amber", "green", "unknown")


def load_compliance_rows(db_path: str) -> list[dict[str, Any]]:
    """Return persisted compliance rows, or an empty list for uninitialized DBs.

    SQLite opens a missing path as an empty database; selecting from the missing
    ``compliance_records`` table then raises ``sqlite3.OperationalError``. For
    the dashboard that state is equivalent to "no extraction has run yet", so it
    becomes a deterministic empty list instead of a Streamlit traceback.
    """

    try:
        return list_compliance_records(db_path)
    except sqlite3.OperationalError as exc:
        if _is_missing_database_or_table(exc):
            return []
        raise


def format_compliance_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add Streamlit-friendly display fields while preserving raw DB keys."""

    return [_format_compliance_row(row) for row in rows]


def render_compliance_tab(db_path: str | None = None) -> None:
    """Render persisted compliance records and selected source evidence.

    The render path intentionally performs one compliance-row query per
    Streamlit rerun. Page images are loaded only for the selected detail row, so
    large BLOBs never enter the main dashboard table.
    """

    resolved_db_path = _resolve_db_path(db_path)
    rows = format_compliance_rows(load_compliance_rows(resolved_db_path))

    render_tab_header(
        "Compliance",
        "Review extracted compliance status and risk signals with source evidence.",
    )

    if not rows:
        render_empty_state(
            "No compliance records are available yet.",
            caption=(
                "Ingest documents and run extraction to populate this SQLite-backed dashboard. "
                f"Looking for persisted records in `{resolved_db_path}`."
            ),
        )
        return

    _render_summary_metrics(rows)

    render_section_divider()
    st.subheader("Compliance records")
    st.dataframe(
        _table_rows(rows),
        hide_index=True,
        width="stretch",
    )

    render_section_divider()
    _render_source_detail(resolved_db_path, rows)


def _resolve_db_path(db_path: str | None) -> str:
    if db_path:
        return db_path

    from src.config import get_settings

    return get_settings().db_path


def _render_summary_metrics(rows: list[dict[str, Any]]) -> None:
    counts = _risk_counts(rows)
    needs_review_count = sum(1 for row in rows if bool(row.get("needs_review")))

    total_col, red_col, amber_col, green_col, unknown_col, review_col = st.columns(6)
    total_col.metric("Total documents", len(rows))
    red_col.metric("Red", counts["red"])
    amber_col.metric("Amber", counts["amber"])
    green_col.metric("Green", counts["green"])
    unknown_col.metric("Unknown", counts["unknown"])
    review_col.metric("Needs review", needs_review_count)


def _risk_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {risk: 0 for risk in _RISK_ORDER}
    for row in rows:
        risk = str(row.get("risk_level") or "unknown").strip().lower()
        if risk not in counts:
            risk = "unknown"
        counts[risk] += 1
    return counts


def _table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {_TABLE_COLUMN_LABELS[column]: row.get(column, _BLANK_LABEL) for column in _TABLE_COLUMNS}
        for row in rows
    ]


def _render_source_detail(db_path: str, rows: list[dict[str, Any]]) -> None:
    st.subheader("Source evidence")

    options = [str(row.get("doc_id") or f"row-{index + 1}") for index, row in enumerate(rows)]
    selected_doc_id = st.selectbox("Select a document", options=options)
    selected_row = rows[options.index(selected_doc_id)]

    st.markdown(f"**Risk reason:** {_safe_detail_text(selected_row.get('risk_reason'))}")
    st.markdown(f"**Source page:** {selected_row.get('source_page_label') or 'No source page'}")
    st.markdown(f"**Source verbatim span:** {_safe_detail_text(selected_row.get('source_verbatim_span'))}")
    st.markdown(f"**Source bounding box:** {_safe_detail_text(selected_row.get('source_bbox'))}")

    image = _load_selected_source_image(db_path, selected_row)
    if image is None:
        st.caption("No source preview available for the selected document/page.")
    else:
        st.image(image, caption=selected_row.get("source_page_label") or "Source page")


def _load_selected_source_image(db_path: str, row: dict[str, Any]) -> Any | None:
    doc_id = row.get("doc_id")
    source_page = row.get("source_page")
    if not doc_id or source_page is None:
        return None
    try:
        return get_page_image(db_path, str(doc_id), int(source_page))
    except (OSError, TypeError, ValueError, sqlite3.Error):
        return None


def _safe_detail_text(value: Any) -> str:
    if value is None:
        return "Not available"
    text = str(value).strip()
    if not text:
        return "Not available"
    if len(text) > _MAX_DETAIL_TEXT_CHARS:
        return f"{text[:_MAX_DETAIL_TEXT_CHARS]}…"
    return text


def _format_compliance_row(row: dict[str, Any]) -> dict[str, Any]:
    formatted = dict(row)

    source_page = row.get("source_page")
    formatted["source_page_display"] = _source_page_display(source_page)
    formatted["source_page_label"] = _source_page_label(source_page)
    formatted["source_evidence_label"] = _source_evidence_label(
        source_page=source_page,
        source_span=row.get("source_verbatim_span"),
    )

    formatted["needs_review_display"] = _needs_review_display(row.get("needs_review"))
    formatted["aggregate_confidence_display"] = _confidence_display(row.get("aggregate_confidence"))
    formatted["risk_level_label"] = _labelize(row.get("risk_level"))
    formatted["review_state_label"] = _labelize(row.get("review_state"))
    formatted["compliance_status_label"] = _labelize(row.get("compliance_status"))

    return formatted


def _is_missing_database_or_table(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "no such table" in message or "unable to open database file" in message


def _source_page_display(source_page: Any) -> int | str:
    if source_page is None:
        return _BLANK_LABEL
    try:
        return int(source_page) + 1
    except (TypeError, ValueError):
        return _BLANK_LABEL


def _source_page_label(source_page: Any) -> str:
    display = _source_page_display(source_page)
    if display == _BLANK_LABEL:
        return "No source page"
    return f"Page {display}"


def _source_evidence_label(*, source_page: Any, source_span: Any) -> str:
    page_label = _source_page_label(source_page)
    if source_span:
        return page_label
    if page_label == "No source page":
        return "No source evidence"
    return f"{page_label} (no source span)"


def _needs_review_display(needs_review: Any) -> str:
    if needs_review is None:
        return _UNKNOWN_LABEL
    return "Needs review" if bool(needs_review) else "No review needed"


def _confidence_display(confidence: Any) -> str:
    if confidence is None:
        return _UNKNOWN_LABEL
    try:
        return f"{float(confidence):.0%}"
    except (TypeError, ValueError):
        return _UNKNOWN_LABEL


def _labelize(value: Any) -> str:
    if value is None:
        return _UNKNOWN_LABEL
    text = str(value).strip()
    if not text:
        return _UNKNOWN_LABEL
    return text.replace("_", " ").title()
