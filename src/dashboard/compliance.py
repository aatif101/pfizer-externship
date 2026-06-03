"""Compliance dashboard data adapter and Streamlit renderer.

This module is intentionally credential-free: it only reads persisted SQLite
compliance rows and formats display-safe values for Streamlit. It must not call
provider or tracing runtime code.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

import streamlit as st

from src.dashboard.ui import render_empty_state, render_section_divider, render_tab_header
from src.db.queries import get_page_image
from src.extraction.repository import (
    ExtractionRunSummary,
    list_compliance_records,
    list_compliance_records_for_run,
    list_extraction_run_summaries,
)


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
_LATEST_OPTION_ID = "latest"
_RUN_OPTION_PREFIX = "run:"
_MAX_LABEL_VALUE_CHARS = 80


@dataclass(frozen=True)
class RunSelectorOption:
    """Display-only state for one compliance dashboard run selector option."""

    option_id: str
    display_label: str
    view_kind: str
    run_id: str | None
    status: str | None
    document_count: int
    field_count: int
    trace_id: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str | None = None
    updated_at: str | None = None


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


def load_extraction_run_summaries(db_path: str) -> list[ExtractionRunSummary]:
    """Return bounded extraction run summaries, or none for uninitialized DBs."""

    try:
        return list_extraction_run_summaries(db_path)
    except sqlite3.OperationalError as exc:
        if _is_missing_database_or_table(exc):
            return []
        raise


def build_run_selector_options(summaries: list[ExtractionRunSummary]) -> list[RunSelectorOption]:
    """Build display-safe selector options with latest-write compatibility first."""

    options = [
        RunSelectorOption(
            option_id=_LATEST_OPTION_ID,
            display_label="Latest compatibility state",
            view_kind="latest",
            run_id=None,
            status=None,
            document_count=0,
            field_count=0,
            trace_id=None,
            started_at=None,
            completed_at=None,
        )
    ]
    options.extend(_run_selector_option(summary) for summary in summaries)
    return options


def load_compliance_rows_for_selection(db_path: str, selected_option_id: str | None) -> list[dict[str, Any]]:
    """Load latest or run-specific compliance rows for a validated selector id.

    Unknown or malformed option IDs intentionally fall back to latest-write state
    so user-controlled selector values cannot become arbitrary run-id queries.
    """

    selected_run_id = _run_id_for_selected_option(load_extraction_run_summaries(db_path), selected_option_id)
    if selected_run_id is None:
        return load_compliance_rows(db_path)

    try:
        return list_compliance_records_for_run(db_path, selected_run_id)
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
    summaries = load_extraction_run_summaries(resolved_db_path)
    selector_options = build_run_selector_options(summaries)
    option_by_id = {option.option_id: option for option in selector_options}

    render_tab_header(
        "Compliance",
        "Review extracted compliance status and risk signals with source evidence.",
    )
    selected_option_id = st.selectbox(
        "Extraction run view",
        options=[option.option_id for option in selector_options],
        format_func=lambda option_id: option_by_id[option_id].display_label,
    )
    selected_option = option_by_id.get(str(selected_option_id), selector_options[0])
    rows = format_compliance_rows(
        _load_compliance_rows_for_selection(resolved_db_path, selected_option.option_id, summaries)
    )
    _render_selected_extraction_view(selected_option)

    if not rows:
        message, caption = _empty_state_for_selection(selected_option, resolved_db_path)
        render_empty_state(message, caption=caption)
        return

    _render_summary_metrics(rows)
    _render_current_extraction_state(rows, selected_option)

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


def _load_compliance_rows_for_selection(
    db_path: str,
    selected_option_id: str | None,
    summaries: list[ExtractionRunSummary],
) -> list[dict[str, Any]]:
    selected_run_id = _run_id_for_selected_option(summaries, selected_option_id)
    if selected_run_id is None:
        return load_compliance_rows(db_path)

    try:
        return list_compliance_records_for_run(db_path, selected_run_id)
    except sqlite3.OperationalError as exc:
        if _is_missing_database_or_table(exc):
            return []
        raise


def _run_id_for_selected_option(summaries: list[ExtractionRunSummary], selected_option_id: str | None) -> str | None:
    if not selected_option_id or selected_option_id == _LATEST_OPTION_ID:
        return None
    valid_run_ids = {summary.run_id for summary in summaries}
    if not selected_option_id.startswith(_RUN_OPTION_PREFIX):
        return None
    run_id = selected_option_id.removeprefix(_RUN_OPTION_PREFIX)
    if run_id not in valid_run_ids:
        return None
    return run_id


def _run_selector_option(summary: ExtractionRunSummary) -> RunSelectorOption:
    view_kind = _run_view_kind(summary.run_id)
    return RunSelectorOption(
        option_id=f"{_RUN_OPTION_PREFIX}{summary.run_id}",
        display_label=_run_display_label(summary, view_kind),
        view_kind=view_kind,
        run_id=summary.run_id,
        status=summary.status,
        document_count=int(summary.document_count or 0),
        field_count=int(summary.field_count or 0),
        trace_id=summary.trace_id,
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


def _run_view_kind(run_id: str) -> str:
    normalized = run_id.lower()
    if "baseline" in normalized:
        return "baseline"
    if "candidate" in normalized:
        return "candidate"
    return "historical"


def _run_display_label(summary: ExtractionRunSummary, view_kind: str) -> str:
    prefix = {
        "baseline": "Baseline run",
        "candidate": "Candidate run",
        "historical": "Historical run",
    }[view_kind]
    parts = [
        f"{prefix}: {_bounded_label_value(summary.run_id)}",
        _bounded_label_value(summary.status or "unknown"),
        f"{int(summary.document_count or 0)} docs",
        f"{int(summary.field_count or 0)} fields",
    ]
    if summary.trace_id:
        parts.append(f"trace {_bounded_label_value(summary.trace_id)}")
    if summary.started_at:
        parts.append(f"started {_bounded_label_value(summary.started_at)}")
    if summary.completed_at:
        parts.append(f"completed {_bounded_label_value(summary.completed_at)}")
    return " • ".join(parts)


def _bounded_label_value(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if len(text) > _MAX_LABEL_VALUE_CHARS:
        return f"{text[:_MAX_LABEL_VALUE_CHARS]}…"
    return text


def _render_selected_extraction_view(option: RunSelectorOption) -> None:
    st.info(f"Selected extraction view: {_selected_view_label(option)}.")
    st.caption(_selected_view_diagnostics(option))


def _selected_view_label(option: RunSelectorOption) -> str:
    if option.view_kind == "latest":
        return "current latest-write compatibility state"
    return f"{_run_kind_label(option.view_kind)} `{_bounded_label_value(option.run_id or '')}`"


def _selected_view_diagnostics(option: RunSelectorOption) -> str:
    if option.view_kind == "latest":
        return (
            "View metadata: latest compatibility state reflects the current rows in `compliance_records`; "
            "select a run below to inspect persisted baseline, candidate, or historical extraction history."
        )

    metadata = [
        f"view={_run_kind_label(option.view_kind)}",
        f"run_id={_bounded_label_value(option.run_id or _UNKNOWN_LABEL)}",
        f"status={_bounded_label_value(option.status or _UNKNOWN_LABEL)}",
        f"documents={int(option.document_count)}",
        f"fields={int(option.field_count)}",
        f"trace_id={_bounded_label_value(option.trace_id or _UNKNOWN_LABEL)}",
        f"started={_bounded_label_value(option.started_at or _UNKNOWN_LABEL)}",
        f"completed={_bounded_label_value(option.completed_at or _UNKNOWN_LABEL)}",
    ]
    return "Run metadata: " + " • ".join(metadata)


def _empty_state_for_selection(option: RunSelectorOption, db_path: str) -> tuple[str, str]:
    if option.view_kind == "latest":
        return (
            "No compliance records are available yet.",
            "Ingest documents and run extraction to populate this SQLite-backed dashboard. "
            f"Looking for persisted records in `{db_path}`.",
        )

    label = _selected_view_label(option)
    return (
        f"No compliance records are available for {label}.",
        "The selected run exists in extraction history, but no compliance rows were found for this view. "
        f"Selected view: {label}; status={_bounded_label_value(option.status or _UNKNOWN_LABEL)}; "
        f"documents={int(option.document_count)}; fields={int(option.field_count)}; "
        f"trace_id={_bounded_label_value(option.trace_id or _UNKNOWN_LABEL)}.",
    )


def _run_kind_label(view_kind: str) -> str:
    if view_kind == "baseline":
        return "Baseline run"
    if view_kind == "candidate":
        return "Candidate run"
    if view_kind == "historical":
        return "Historical run"
    return _labelize(view_kind)


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


def _render_current_extraction_state(rows: list[dict[str, Any]], selected_option: RunSelectorOption) -> None:
    if selected_option.view_kind != "latest":
        st.info(
            f"Selected extraction state: showing only rows from {_selected_view_label(selected_option)}; "
            "latest-write compatibility rows are not mixed into this historical view."
        )
        return

    run_ids = sorted({str(row.get("run_id") or "").strip() for row in rows if row.get("run_id")})
    if not run_ids:
        st.info(
            "Current extraction state: latest persisted compliance rows. No extraction run IDs are recorded for these rows."
        )
        return

    if len(run_ids) == 1:
        st.info(
            "Current extraction state: latest persisted compliance rows from extraction run "
            f"`{run_ids[0]}`. Historical baselines and candidates are preserved in the Eval tab."
        )
        return

    preview = ", ".join(f"`{run_id}`" for run_id in run_ids[:5])
    suffix = "" if len(run_ids) <= 5 else f", plus {len(run_ids) - 5} more"
    st.info(
        "Current extraction state: latest persisted compliance rows spanning "
        f"{len(run_ids)} document-level extraction runs ({preview}{suffix}). "
        "This table is latest-write state; historical baselines and candidates are preserved in the Eval tab."
    )


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
