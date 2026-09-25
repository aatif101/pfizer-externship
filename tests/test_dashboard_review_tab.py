"""FakeStreamlit tests for the HITL Review tab (06-06, HITL-01 / OBS-01)."""
from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager, contextmanager
from types import SimpleNamespace, TracebackType
from typing import Any

import pytest

from src.dashboard.review import render_review_tab
from src.extraction.review import ReviewInputError, ReviewOutcome, ReviewQueueItem

_PHASE = "phase-6-test"
_THRESHOLD = 0.75
_DB = "review-test.db"


class FakeContext(AbstractContextManager["FakeContext"]):
    def __init__(self, fake_st: "FakeStreamlit", kind: str, label: str) -> None:
        self.fake_st = fake_st
        self.kind = kind
        self.label = label

    def __enter__(self) -> "FakeContext":
        self.fake_st.context_stack.append((self.kind, self.label))
        self.fake_st.context_entries.append((self.kind, self.label))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.fake_st.context_stack.pop()


class FakeMetricColumn:
    def __init__(self, parent: "FakeStreamlit") -> None:
        self.parent = parent

    def metric(self, label: str, value: int) -> None:
        self.parent.metrics[label] = value


class FakeStreamlit:
    def __init__(
        self,
        *,
        radio: str | None = None,
        text_input: str = "",
        number_input: int = 1,
        text_area: str = "",
        submit: bool = False,
        select: str | None = None,
    ) -> None:
        self.session_state: dict[str, Any] = {}
        self.context_stack: list[tuple[str, str]] = []
        self.context_entries: list[tuple[str, str]] = []
        self.headers: list[str] = []
        self.subheaders: list[str] = []
        self.info_messages: list[str] = []
        self.caption_messages: list[str] = []
        self.markdown_messages: list[str] = []
        self.error_messages: list[str] = []
        self.success_messages: list[str] = []
        self.dataframes: list[list[dict[str, Any]]] = []
        self.images: list[tuple[Any, str]] = []
        self.metrics: dict[str, int] = {}
        self.selectboxes: list[dict[str, Any]] = []
        self.radios: list[dict[str, Any]] = []
        self.number_inputs: list[dict[str, Any]] = []
        self.text_inputs: list[dict[str, Any]] = []
        self.text_areas: list[dict[str, Any]] = []
        self.forms: list[str] = []
        self.submit_buttons: list[str] = []
        self.rerun_count = 0
        self.divider_count = 0
        self._radio = radio
        self._text_input = text_input
        self._number_input = number_input
        self._text_area = text_area
        self._submit = submit
        self._select = select

    # --- layout / text ---
    def header(self, message: str) -> None:
        self.headers.append(message)

    def subheader(self, message: str) -> None:
        self.subheaders.append(message)

    def divider(self) -> None:
        self.divider_count += 1

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def caption(self, message: str) -> None:
        self.caption_messages.append(message)

    def markdown(self, message: str) -> None:
        self.markdown_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def success(self, message: str) -> None:
        self.success_messages.append(message)

    def rerun(self) -> None:
        self.rerun_count += 1

    def columns(self, count: int) -> list[FakeMetricColumn]:
        return [FakeMetricColumn(self) for _ in range(count)]

    def dataframe(self, rows, *, hide_index: bool, width: str) -> None:
        assert hide_index is True
        assert width == "stretch"
        self.dataframes.append(list(rows))

    def image(self, image, *, caption: str) -> None:
        self.images.append((image, caption))

    # --- widgets ---
    def selectbox(self, label: str, *, options: list[str], format_func=None, key: str | None = None) -> str:
        self.selectboxes.append({"label": label, "options": list(options), "key": key})
        selected = self._select if self._select is not None else options[0]
        assert selected in options
        if key is not None:
            self.session_state[key] = selected
        return selected

    def form(self, key: str, **_kwargs: Any) -> FakeContext:
        self.forms.append(key)
        return FakeContext(self, "form", key)

    def radio(self, label: str, *, options: list[str], format_func=None, **_kwargs: Any) -> str:
        labels = [format_func(o) if format_func else o for o in options]
        self.radios.append({"label": label, "options": list(options), "labels": labels})
        selected = self._radio if self._radio is not None else options[0]
        assert selected in options
        return selected

    def text_input(self, label: str, *, max_chars: int | None = None, **kwargs: Any) -> str:
        self.text_inputs.append({"label": label, "max_chars": max_chars, **kwargs})
        return self._text_input

    def number_input(self, label: str, *, min_value: int, value: int, step: int, **kwargs: Any) -> int:
        self.number_inputs.append({"label": label, "min_value": min_value, "value": value, "step": step})
        return self._number_input

    def text_area(self, label: str, *, max_chars: int | None = None, **kwargs: Any) -> str:
        self.text_areas.append({"label": label, "max_chars": max_chars})
        return self._text_area

    def form_submit_button(self, label: str, **_kwargs: Any) -> bool:
        assert self.context_stack and self.context_stack[-1][0] == "form"
        self.submit_buttons.append(label)
        return self._submit

    def all_rendered_text(self) -> str:
        return "\n".join(
            [
                *self.headers,
                *self.info_messages,
                *self.caption_messages,
                *self.markdown_messages,
                *self.error_messages,
                *self.success_messages,
            ]
        )


def _item(
    doc_id: str,
    field_name: str,
    *,
    review_state: str = "needs_review",
    confidence: float = 0.4,
    source_page: int | None = 2,
    current_value: str | None = "2024-01-01",
    verbatim_span: str | None = "Expiry: 2024-01-01",
    abstention_reason: str | None = None,
    filename: str | None = None,
) -> ReviewQueueItem:
    return ReviewQueueItem(
        doc_id=doc_id,
        filename=filename or f"{doc_id}.pdf",
        field_name=field_name,
        current_value=current_value,
        confidence=confidence,
        source_page=source_page,
        verbatim_span=verbatim_span,
        evidence_type="text",
        review_state=review_state,
        abstention_reason=abstention_reason,
    )


def _default_queue() -> list[ReviewQueueItem]:
    return [
        _item("docA", "expiry_date", source_page=2),
        _item(
            "docA",
            "vendor_name",
            review_state="abstained",
            confidence=0.0,
            current_value=None,
            verbatim_span=None,
            source_page=None,
            abstention_reason="No vendor name on page",
        ),
        _item("docB", "expiry_date", confidence=0.6, verbatim_span="X" * 400),
    ]


class Recorder:
    def __init__(self, *, result: Any = None, exc: BaseException | None = None) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.result = result
        self.exc = exc

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.exc is not None:
            raise self.exc
        return self.result


def _outcome(field_name: str = "expiry_date", action: str = "correct") -> ReviewOutcome:
    return ReviewOutcome(
        review_id=1,
        doc_id="docA",
        field_name=field_name,
        action=action,
        new_review_state="reviewed",
        risk_level="red",
        compliance_needs_review=False,
    )


@pytest.fixture
def trace_spy(monkeypatch):
    spy: dict[str, Any] = {"sessions": [], "flushes": 0, "inside": []}

    @contextmanager
    def fake_trace_session(**kwargs: Any):
        spy["sessions"].append(kwargs)
        spy["inside"].append(True)
        try:
            yield
        finally:
            spy["inside"].pop()

    def fake_flush() -> bool:
        spy["flushes"] += 1
        return True

    monkeypatch.setattr("src.dashboard.review.trace_session", fake_trace_session)
    monkeypatch.setattr("src.dashboard.review.flush_traces", fake_flush)
    monkeypatch.setattr(
        "src.dashboard.review.get_settings",
        lambda: SimpleNamespace(
            db_path=_DB,
            pipeline_phase=_PHASE,
            extraction_low_confidence_threshold=_THRESHOLD,
        ),
    )
    return spy


def _install(monkeypatch, fake_st: FakeStreamlit) -> None:
    monkeypatch.setattr("src.dashboard.review.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)


def _render(fake_st, *, queue=None, apply_fn=None, image_fn=None, queue_fn=None) -> None:
    render_review_tab(
        _DB,
        queue_fn=queue_fn or (lambda db_path, *, threshold: list(queue if queue is not None else _default_queue())),
        apply_fn=apply_fn or Recorder(result=_outcome()),
        image_fn=image_fn or (lambda db_path, doc_id, page: None),
    )


def test_empty_queue_shows_empty_state(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(submit=True)
    _install(monkeypatch, fake_st)
    seen: dict[str, Any] = {}

    def queue_fn(db_path, *, threshold):
        seen["args"] = (db_path, threshold)
        return []

    _render(fake_st, queue_fn=queue_fn)

    assert seen["args"] == (_DB, _THRESHOLD)
    assert any("No extractions need review" in m for m in fake_st.info_messages)
    assert fake_st.forms == []
    assert fake_st.dataframes == []
    assert fake_st.error_messages == []


def test_queue_metrics_and_table(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st)

    _render(fake_st)

    assert fake_st.metrics == {"Queued": 3, "Abstained": 1, "Low confidence / needs review": 2}
    assert len(fake_st.dataframes) == 1
    rows = fake_st.dataframes[0]
    assert len(rows) == 3
    first = rows[0]
    for key in ("filename", "field", "value", "confidence", "review state", "page"):
        assert key in first
    assert first["filename"] == "docA.pdf"
    assert first["field"] == "expiry_date"
    assert first["confidence"] == "40%"
    assert first["page"] == 3
    assert rows[1]["page"] == "-"
    for row in rows:
        span = row.get("span")
        assert span is None or len(span) <= 121  # 120 chars + ellipsis
    assert all("X" * 121 not in str(row) for row in rows)


def test_selector_options_unique(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(select="docA::vendor_name")
    _install(monkeypatch, fake_st)

    _render(fake_st)

    assert len(fake_st.selectboxes) == 1
    assert fake_st.selectboxes[0]["options"] == ["docA::expiry_date", "docA::vendor_name", "docB::expiry_date"]
    assert fake_st.session_state["pfizer_review_selected"] == "docA::vendor_name"
    # Abstained item: approve is not offered.
    assert fake_st.radios[0]["options"] == ["correct", "confirm_absent"]
    assert any("No vendor name on page" in m for m in fake_st.markdown_messages)
    assert fake_st.forms == ["review_docA_vendor_name"]


def test_detail_shows_source_image(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st)
    sentinel = object()
    image_calls: list[tuple[str, str, int]] = []

    def image_fn(db_path, doc_id, page):
        image_calls.append((db_path, doc_id, page))
        return sentinel

    _render(fake_st, image_fn=image_fn)

    assert image_calls == [(_DB, "docA", 2)]
    assert len(fake_st.images) == 1
    assert fake_st.images[0][0] is sentinel
    assert "Page 3" in fake_st.images[0][1]
    text = fake_st.all_rendered_text()
    assert "2024-01-01" in text
    assert "Expiry: 2024-01-01" in text
    assert "40%" in text
    assert fake_st.radios[0]["options"] == ["approve", "correct", "confirm_absent"]
    assert fake_st.number_inputs[0]["value"] == 3
    assert fake_st.number_inputs[0]["min_value"] == 1


def test_detail_image_error_is_safe(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st)

    def image_fn(db_path, doc_id, page):
        raise OSError("disk exploded at /secret/path")

    _render(fake_st, image_fn=image_fn)

    assert fake_st.images == []
    assert any("No source preview available" in c for c in fake_st.caption_messages)
    assert "/secret/path" not in fake_st.all_rendered_text()


def test_submit_correct_calls_apply_fn(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(radio="correct", text_input="2020-01-01", number_input=3, text_area="note", submit=True)
    _install(monkeypatch, fake_st)
    apply_fn = Recorder(result=_outcome())

    _render(fake_st, apply_fn=apply_fn)

    assert len(apply_fn.calls) == 1
    args, kwargs = apply_fn.calls[0]
    assert args == (_DB,)
    assert kwargs == {
        "doc_id": "docA",
        "field_name": "expiry_date",
        "action": "correct",
        "corrected_value": "2020-01-01",
        "source_page": 2,
        "note": "note",
    }
    assert len(fake_st.success_messages) == 1
    assert fake_st.rerun_count == 1
    assert fake_st.error_messages == []


def test_submit_approve_omits_value(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(radio="approve", text_input="ignored", number_input=5, text_area="   ", submit=True)
    _install(monkeypatch, fake_st)
    apply_fn = Recorder(result=_outcome(action="approve"))

    _render(fake_st, apply_fn=apply_fn)

    assert len(apply_fn.calls) == 1
    _args, kwargs = apply_fn.calls[0]
    assert kwargs["action"] == "approve"
    assert kwargs["corrected_value"] is None
    assert kwargs["source_page"] is None
    assert kwargs["note"] is None
    assert fake_st.rerun_count == 1


def test_no_submit_no_write(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(radio="correct", text_input="2020-01-01", submit=False)
    _install(monkeypatch, fake_st)
    apply_fn = Recorder(result=_outcome())

    _render(fake_st, apply_fn=apply_fn)

    assert apply_fn.calls == []
    assert trace_spy["sessions"] == []
    assert fake_st.submit_buttons == ["Submit review"]


def test_submit_invalid_shows_reason_code_only(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(radio="correct", text_input="not-a-date", number_input=3, submit=True)
    _install(monkeypatch, fake_st)

    class LeakyReviewError(ReviewInputError):
        def __str__(self) -> str:  # would leak if str(exc) were rendered
            return "leaky details /secret"

    apply_fn = Recorder(exc=LeakyReviewError("invalid_date"))

    _render(fake_st, apply_fn=apply_fn)

    assert len(fake_st.error_messages) == 1
    assert "invalid_date" in fake_st.error_messages[0]
    assert "leaky" not in fake_st.all_rendered_text()
    assert fake_st.success_messages == []
    assert fake_st.rerun_count == 0
    assert trace_spy["flushes"] == 1


def test_submit_unexpected_error_bounded(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(radio="correct", text_input="2020-01-01", number_input=3, submit=True)
    _install(monkeypatch, fake_st)
    apply_fn = Recorder(exc=RuntimeError("secret /path/db"))

    _render(fake_st, apply_fn=apply_fn)

    assert len(fake_st.error_messages) == 1
    assert "RuntimeError" in fake_st.error_messages[0]
    assert "/path/db" not in fake_st.all_rendered_text()
    assert fake_st.rerun_count == 0
    assert trace_spy["flushes"] == 1


def test_submit_opens_trace_session(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(radio="confirm_absent", submit=True)
    _install(monkeypatch, fake_st)
    inside_flags: list[bool] = []

    def apply_fn(*args, **kwargs):
        inside_flags.append(bool(trace_spy["inside"]))
        return _outcome(action="confirm_absent")

    _render(fake_st, apply_fn=apply_fn)

    assert inside_flags == [True]
    assert len(trace_spy["sessions"]) == 1
    session = trace_spy["sessions"][0]
    assert session["phase"] == _PHASE
    assert "review" in session["tags"]
    assert "hitl" in session["tags"]
    assert trace_spy["flushes"] == 1


def test_missing_table_is_safe(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit(submit=True)
    _install(monkeypatch, fake_st)

    def queue_fn(db_path, *, threshold):
        raise sqlite3.OperationalError("no such table: extractions")

    _render(fake_st, queue_fn=queue_fn)

    assert any("Review queue unavailable" in m for m in fake_st.info_messages)
    assert "no such table" not in fake_st.all_rendered_text()
    assert fake_st.error_messages == []
    assert fake_st.forms == []


def test_default_db_path_resolves_from_settings(monkeypatch, trace_spy) -> None:
    fake_st = FakeStreamlit()
    _install(monkeypatch, fake_st)
    seen: list[str] = []

    def queue_fn(db_path, *, threshold):
        seen.append(db_path)
        return []

    render_review_tab(queue_fn=queue_fn)

    assert seen == [_DB]
