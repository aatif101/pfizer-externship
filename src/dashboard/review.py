"""HITL Review tab: surface low-confidence / abstained extractions for human review.

The tab reads the review queue and writes reviewer decisions only through the
06-02 repository seams (``list_review_queue`` / ``apply_field_review``). Error
text shown to the reviewer is limited to a ``ReviewInputError.reason_code`` or an
exception class name; raw exception messages never reach the browser. Each
submit runs inside a phase-tagged ``trace_session`` and flushes traces after.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable

import streamlit as st

from src.config import get_settings
from src.dashboard.ui import (
    format_percent,
    render_empty_state,
    render_section_divider,
    render_tab_header,
)
from src.db.queries import get_page_image
from src.extraction.review import (
    MAX_CORRECTED_VALUE_CHARS,
    MAX_NOTE_CHARS,
    ReviewAction,
    ReviewInputError,
    ReviewOutcome,
    ReviewQueueItem,
    apply_field_review,
    list_review_queue,
)
from src.tracing import flush_traces, trace_session

QueueFn = Callable[..., list[ReviewQueueItem]]
ApplyFn = Callable[..., ReviewOutcome]
ImageFn = Callable[[str, str, int], Any]

_REVIEW_SELECTED_KEY = "pfizer_review_selected"
_MAX_DETAIL_CHARS = 1000
_MAX_TABLE_SPAN_CHARS = 120
_NOT_AVAILABLE = "Not available"
_ABSTAINED_STATE = "abstained"
_ALL_ACTIONS: tuple[str, ...] = (
    ReviewAction.APPROVE.value,
    ReviewAction.CORRECT.value,
    ReviewAction.CONFIRM_ABSENT.value,
)
_ACTION_LABELS = {
    ReviewAction.APPROVE.value: "Approve current value",
    ReviewAction.CORRECT.value: "Correct the value",
    ReviewAction.CONFIRM_ABSENT.value: "Confirm field is absent",
}


def render_review_tab(
    db_path: str | None = None,
    *,
    queue_fn: QueueFn | None = None,
    apply_fn: ApplyFn | None = None,
    image_fn: ImageFn | None = None,
) -> None:
    """Render the HITL review queue, the selected item's evidence, and the review form."""
    settings = get_settings()
    resolved_db_path = db_path if db_path is not None else settings.db_path

    render_tab_header(
        "Human Review",
        caption="Low-confidence and abstained extractions awaiting a compliance officer's decision.",
    )

    load_queue = queue_fn or list_review_queue
    try:
        queue = list(load_queue(resolved_db_path, threshold=settings.extraction_low_confidence_threshold))
    except (sqlite3.Error, OSError):
        render_empty_state("Review queue unavailable", caption="Ingest and extract documents first.")
        return

    if not queue:
        render_empty_state("No extractions need review.")
        return

    _render_queue_metrics(queue)
    st.dataframe(_queue_table_rows(queue), hide_index=True, width="stretch")
    render_section_divider()

    selected = _select_item(queue)
    _render_detail(resolved_db_path, selected, image_fn or get_page_image)
    render_section_divider()
    _render_review_form(resolved_db_path, selected, apply_fn or apply_field_review, settings.pipeline_phase)


def _render_queue_metrics(queue: list[ReviewQueueItem]) -> None:
    abstained = sum(1 for item in queue if item.review_state == _ABSTAINED_STATE)
    total_col, abstained_col, low_col = st.columns(3)
    total_col.metric("Queued", len(queue))
    abstained_col.metric("Abstained", abstained)
    low_col.metric("Low confidence / needs review", len(queue) - abstained)


def _queue_table_rows(queue: list[ReviewQueueItem]) -> list[dict[str, Any]]:
    return [
        {
            "filename": _bounded(item.filename, _MAX_TABLE_SPAN_CHARS, empty="-"),
            "field": item.field_name,
            "value": _bounded(item.current_value, _MAX_TABLE_SPAN_CHARS, empty="-"),
            "confidence": format_percent(item.confidence),
            "review state": item.review_state,
            "page": _page_display(item.source_page),
            "span": _bounded(item.verbatim_span, _MAX_TABLE_SPAN_CHARS, empty="-"),
        }
        for item in queue
    ]


def _select_item(queue: list[ReviewQueueItem]) -> ReviewQueueItem:
    options = [_item_key(item) for item in queue]
    previous = st.session_state.get(_REVIEW_SELECTED_KEY)
    index = options.index(previous) if previous in options else 0
    selected_key = st.selectbox("Select a field to review", options=options, index=index)
    if selected_key not in options:
        selected_key = options[0]
    st.session_state[_REVIEW_SELECTED_KEY] = selected_key
    return queue[options.index(selected_key)]


def _render_detail(db_path: str, item: ReviewQueueItem, image_fn: ImageFn) -> None:
    st.subheader("Evidence")
    st.markdown(f"**Document:** {_safe_detail_text(item.filename)}")
    st.markdown(f"**Field:** {_safe_detail_text(item.field_name)}")
    st.markdown(f"**Current value:** {_safe_detail_text(item.current_value)}")
    st.markdown(f"**Confidence:** {format_percent(item.confidence)}")
    st.markdown(f"**Review state:** {_safe_detail_text(item.review_state)}")
    st.markdown(f"**Evidence type:** {_safe_detail_text(item.evidence_type)}")
    st.markdown(f"**Source page:** {_page_label(item.source_page)}")
    st.markdown(f"**Verbatim span:** {_safe_detail_text(item.verbatim_span)}")
    st.markdown(f"**Abstention reason:** {_safe_detail_text(item.abstention_reason)}")

    image = _load_source_image(db_path, item, image_fn)
    if image is None or item.source_page is None:
        st.caption("No source preview available for this page.")
    else:
        st.image(image, caption=_page_label(item.source_page))


def _load_source_image(db_path: str, item: ReviewQueueItem, image_fn: ImageFn) -> Any | None:
    if item.source_page is None:
        return None
    try:
        return image_fn(db_path, item.doc_id, int(item.source_page))
    except (OSError, TypeError, ValueError, sqlite3.Error):
        return None


def _render_review_form(db_path: str, item: ReviewQueueItem, apply_fn: ApplyFn, phase: str) -> None:
    actions = _available_actions(item)
    with st.form(key=f"review_{item.doc_id}_{item.field_name}"):
        action = st.radio("Decision", options=list(actions), format_func=_action_label)
        corrected_value = st.text_input("Corrected value", max_chars=MAX_CORRECTED_VALUE_CHARS)
        page_display = st.number_input(
            "Source page (1-based)",
            min_value=1,
            value=(item.source_page or 0) + 1,
            step=1,
        )
        note = st.text_area("Reviewer note (optional)", max_chars=MAX_NOTE_CHARS)
        submitted = st.form_submit_button("Submit review")

    if not submitted:
        return

    is_correct = action == ReviewAction.CORRECT.value
    kwargs: dict[str, Any] = {
        "doc_id": item.doc_id,
        "field_name": item.field_name,
        "action": action,
        "corrected_value": corrected_value if is_correct else None,
        "source_page": _to_zero_indexed(page_display) if is_correct else None,
        "note": note.strip() if isinstance(note, str) and note.strip() else None,
    }

    saved = False
    try:
        with trace_session(phase=phase, tags=("hitl", "review")):
            apply_fn(db_path, **kwargs)
        saved = True
    except ReviewInputError as exc:
        st.error(f"Review not saved: {_bounded_code(exc.reason_code)}")
    except Exception as exc:  # noqa: BLE001 - only the class name is rendered
        st.error(f"Review not saved: {exc.__class__.__name__}")
    finally:
        flush_traces()

    if saved:
        st.success(f"Saved {_action_label(action)} for {item.field_name}.")
        st.rerun()


def _available_actions(item: ReviewQueueItem) -> tuple[str, ...]:
    if item.review_state == _ABSTAINED_STATE:
        return tuple(a for a in _ALL_ACTIONS if a != ReviewAction.APPROVE.value)
    return _ALL_ACTIONS


def _action_label(action: str) -> str:
    return _ACTION_LABELS.get(action, str(action))


def _to_zero_indexed(display_page: Any) -> int:
    try:
        return int(display_page) - 1
    except (TypeError, ValueError):
        return -1  # rejected downstream as source_page_out_of_range


def _item_key(item: ReviewQueueItem) -> str:
    return f"{item.doc_id}::{item.field_name}"


def _page_display(source_page: int | None) -> int | str:
    if source_page is None:
        return "-"
    try:
        return int(source_page) + 1
    except (TypeError, ValueError):
        return "-"


def _page_label(source_page: int | None) -> str:
    display = _page_display(source_page)
    return "No source page" if display == "-" else f"Page {display}"


def _bounded(value: Any, limit: int, *, empty: str) -> str:
    if value is None:
        return empty
    text = str(value).strip()
    if not text:
        return empty
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def _safe_detail_text(value: Any) -> str:
    return _bounded(value, _MAX_DETAIL_CHARS, empty=_NOT_AVAILABLE)


def _bounded_code(reason_code: Any) -> str:
    return _bounded(reason_code, 64, empty="invalid_input")
