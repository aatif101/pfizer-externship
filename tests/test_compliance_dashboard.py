"""Tests for the compliance dashboard read/format adapter."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from src.dashboard.compliance import (
    build_run_selector_options,
    format_compliance_rows,
    load_compliance_rows,
    load_compliance_rows_for_selection,
    load_extraction_run_summaries,
    render_compliance_tab,
)
from src.db.queries import insert_document
from src.db.schema import init_db
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.repository import ExtractionRunSummary, upsert_extraction_record


def make_field(
    field_name: SDFFieldName,
    raw_value: str | None,
    *,
    normalized_date: date | None = None,
    confidence: float = 0.9,
    page_num: int = 0,
    review_state: ReviewState = ReviewState.PENDING,
    abstention_reason: str | None = None,
    verbatim_span: str | None = None,
) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=None if normalized_date is not None else raw_value,
        normalized_date=normalized_date,
        confidence=confidence,
        evidence=SourceEvidence(
            page_num=page_num,
            bbox={"x": 10 + page_num, "y": 20, "width": 100, "height": 30},
            verbatim_span=verbatim_span if verbatim_span is not None else raw_value,
        ),
        review_state=review_state,
        abstention_reason=abstention_reason,
    )


def make_record(
    *,
    vendor_name: str = "Acme Pharma",
    expiry_date: date = date(2026, 1, 31),
    trace_id: str = "trace-dashboard-001",
    run_id: str | None = "run-dashboard-001",
    risk_level: str = "amber",
    risk_reason: str = "Oldest relevant date is between 2 and 3 years old.",
    compliance_status: str = "needs_review",
    age_days: int = 865,
) -> SDFExtractionRecord:
    return SDFExtractionRecord(
        doc_id="doc-dashboard-001",
        filename="supplier-sdf.pdf",
        fields={
            SDFFieldName.DOC_TYPE: make_field(
                SDFFieldName.DOC_TYPE,
                "Supplier Declaration Form",
                confidence=0.96,
            ),
            SDFFieldName.VENDOR_NAME: make_field(
                SDFFieldName.VENDOR_NAME,
                vendor_name,
                confidence=0.92,
            ),
            SDFFieldName.MANUFACTURING_DATE: make_field(
                SDFFieldName.MANUFACTURING_DATE,
                "2024-01-05",
                normalized_date=date(2024, 1, 5),
                confidence=0.88,
                page_num=1,
            ),
            SDFFieldName.EFFECTIVE_DATE: make_field(
                SDFFieldName.EFFECTIVE_DATE,
                "2024-02-01",
                normalized_date=date(2024, 2, 1),
                confidence=0.84,
                page_num=1,
            ),
            SDFFieldName.REVISION_DATE: make_field(
                SDFFieldName.REVISION_DATE,
                "2024-03-15",
                normalized_date=date(2024, 3, 15),
                confidence=0.8,
                page_num=1,
                review_state=ReviewState.REVIEWED,
            ),
            SDFFieldName.EXPIRY_DATE: make_field(
                SDFFieldName.EXPIRY_DATE,
                expiry_date.isoformat(),
                normalized_date=expiry_date,
                confidence=0.78,
                page_num=2,
                verbatim_span=f"Expiry Date: {expiry_date.isoformat()}",
            ),
        },
        trace_id=trace_id,
        run_id=run_id,
        extracted_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
        risk_level=risk_level,
        risk_reason=risk_reason,
        compliance_status=compliance_status,
        age_days=age_days,
    )


def prepare_compliance_db(db_path: str) -> None:
    init_db(db_path)
    insert_document(
        db_path,
        doc_id="doc-dashboard-001",
        filename="supplier-sdf.pdf",
        file_path="/tmp/supplier-sdf.pdf",
        page_count=3,
        docling_json=None,
    )


def test_load_and_format_compliance_rows_exposes_dashboard_fields(tmp_db_path: str) -> None:
    prepare_compliance_db(tmp_db_path)
    upsert_extraction_record(tmp_db_path, make_record())

    rows = load_compliance_rows(tmp_db_path)
    formatted = format_compliance_rows(rows)

    assert len(formatted) == 1
    row = formatted[0]

    assert row["vendor_name"] == "Acme Pharma"
    assert row["doc_type"] == "Supplier Declaration Form"
    assert row["manufacturing_date"] == "2024-01-05"
    assert row["effective_date"] == "2024-02-01"
    assert row["revision_date"] == "2024-03-15"
    assert row["expiry_date"] == "2026-01-31"
    assert row["risk_level"] == "amber"
    assert row["risk_reason"] == "Oldest relevant date is between 2 and 3 years old."
    assert row["compliance_status"] == "needs_review"
    assert row["age_days"] == 865
    assert row["aggregate_confidence"] == make_record().aggregate_confidence
    assert row["review_state"] == "pending"
    assert row["needs_review"] == 0
    assert row["run_id"] == "run-dashboard-001"
    assert row["trace_id"] == "trace-dashboard-001"
    assert row["source_verbatim_span"] == "Expiry Date: 2026-01-31"

    assert row["source_page"] == 2
    assert row["source_page_display"] == 3
    assert row["source_page_label"] == "Page 3"
    assert row["source_evidence_label"] == "Page 3"
    assert row["needs_review_display"] == "No review needed"
    assert row["aggregate_confidence_display"] == "86%"
    assert row["risk_level_label"] == "Amber"
    assert row["review_state_label"] == "Pending"
    assert row["compliance_status_label"] == "Needs Review"


def test_load_compliance_rows_returns_empty_for_missing_database(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing-dashboard.db"

    assert load_compliance_rows(str(missing_db)) == []


def test_load_compliance_rows_returns_empty_for_missing_table(tmp_db_path: str) -> None:
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    assert load_compliance_rows(tmp_db_path) == []


def test_load_run_selector_options_and_rows_for_latest_and_explicit_runs(tmp_db_path: str) -> None:
    prepare_compliance_db(tmp_db_path)
    upsert_extraction_record(
        tmp_db_path,
        make_record(
            vendor_name="Baseline Vendor",
            expiry_date=date(2026, 1, 31),
            trace_id="trace-baseline",
            run_id="run-baseline-001",
            risk_level="green",
            risk_reason="Baseline document is in date.",
            compliance_status="compliant",
            age_days=100,
        ),
    )
    upsert_extraction_record(
        tmp_db_path,
        make_record(
            vendor_name="Candidate Vendor",
            expiry_date=date(2027, 2, 28),
            trace_id="trace-candidate",
            run_id="run-candidate-001",
            risk_level="amber",
            risk_reason="Candidate document needs review.",
            compliance_status="needs_review",
            age_days=400,
        ),
    )

    summaries = load_extraction_run_summaries(tmp_db_path)
    options = build_run_selector_options(summaries)

    assert options[0].option_id == "latest"
    assert options[0].display_label == "Latest compatibility state"
    assert options[0].view_kind == "latest"
    assert {option.view_kind for option in options[1:]} == {"baseline", "candidate"}
    assert {option.document_count for option in options[1:]} == {1}
    assert {option.field_count for option in options[1:]} == {6}
    assert all("Vendor" not in option.display_label for option in options)
    assert any("Baseline run: run-baseline-001" in option.display_label for option in options)
    assert any("Candidate run: run-candidate-001" in option.display_label for option in options)

    latest_rows = load_compliance_rows_for_selection(tmp_db_path, "latest")
    baseline_rows = load_compliance_rows_for_selection(tmp_db_path, "run:run-baseline-001")
    candidate_rows = load_compliance_rows_for_selection(tmp_db_path, "run:run-candidate-001")

    assert [row["vendor_name"] for row in latest_rows] == ["Candidate Vendor"]
    assert [row["run_id"] for row in latest_rows] == ["run-candidate-001"]
    assert [row["vendor_name"] for row in baseline_rows] == ["Baseline Vendor"]
    assert [row["run_id"] for row in baseline_rows] == ["run-baseline-001"]
    assert [row["vendor_name"] for row in candidate_rows] == ["Candidate Vendor"]
    assert [row["run_id"] for row in candidate_rows] == ["run-candidate-001"]


def test_run_selector_missing_history_tables_returns_latest_only_state(tmp_db_path: str) -> None:
    init_db(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("DROP TABLE extraction_runs")
    conn.execute("DROP TABLE extraction_history")
    conn.execute("DROP TABLE compliance_record_history")
    conn.commit()
    conn.close()

    assert load_extraction_run_summaries(tmp_db_path) == []
    options = build_run_selector_options(load_extraction_run_summaries(tmp_db_path))

    assert len(options) == 1
    assert options[0].option_id == "latest"
    assert options[0].view_kind == "latest"
    assert load_compliance_rows_for_selection(tmp_db_path, "run:missing-history") == []


def test_unknown_selector_id_falls_back_to_latest_compatibility_rows(tmp_db_path: str) -> None:
    prepare_compliance_db(tmp_db_path)
    upsert_extraction_record(
        tmp_db_path,
        make_record(vendor_name="Latest Vendor", trace_id="trace-latest", run_id="run-latest-001"),
    )

    rows = load_compliance_rows_for_selection(tmp_db_path, "run:not-a-known-run")

    assert [row["vendor_name"] for row in rows] == ["Latest Vendor"]
    assert [row["run_id"] for row in rows] == ["run-latest-001"]


def test_explicit_run_selector_with_no_compliance_rows_does_not_fall_back_to_latest(tmp_db_path: str) -> None:
    prepare_compliance_db(tmp_db_path)
    upsert_extraction_record(tmp_db_path, make_record(vendor_name="Latest Vendor", run_id="run-latest-001"))
    conn = sqlite3.connect(tmp_db_path)
    conn.execute(
        """
        INSERT INTO extraction_runs (
            run_id, status, document_count, field_count, trace_id,
            started_at, completed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-candidate-empty",
            "completed",
            0,
            0,
            "trace-empty",
            "2026-05-19T12:30:00+00:00",
            "2026-05-19T12:31:00+00:00",
            "2026-05-19T12:30:00+00:00",
            "2026-05-19T12:31:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    rows = load_compliance_rows_for_selection(tmp_db_path, "run:run-candidate-empty")

    assert rows == []


def test_format_compliance_rows_handles_null_source_evidence_without_exceptions() -> None:
    formatted = format_compliance_rows(
        [
            {
                "doc_id": "doc-null-evidence",
                "vendor_name": "Null Evidence Labs",
                "source_page": None,
                "source_verbatim_span": None,
                "aggregate_confidence": None,
                "needs_review": None,
                "risk_level": None,
                "review_state": None,
                "compliance_status": None,
            }
        ]
    )

    row = formatted[0]
    assert row["source_page_display"] == ""
    assert row["source_page_label"] == "No source page"
    assert row["source_evidence_label"] == "No source evidence"
    assert row["aggregate_confidence_display"] == "Unknown"
    assert row["needs_review_display"] == "Unknown"
    assert row["risk_level_label"] == "Unknown"
    assert row["review_state_label"] == "Unknown"
    assert row["compliance_status_label"] == "Unknown"


def test_render_compliance_tab_empty_state_does_not_crash(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr("src.dashboard.compliance.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)
    monkeypatch.setattr("src.dashboard.compliance.render_empty_state", fake_st.render_empty_state)
    monkeypatch.setattr("src.dashboard.compliance.load_compliance_rows", lambda db_path: [])

    render_compliance_tab("empty-dashboard.db")

    assert fake_st.info_messages == [
        "Selected extraction view: current latest-write compatibility state.",
        "No compliance records are available yet.",
    ]
    assert fake_st.caption_messages == [
        "Review extracted compliance status and risk signals with source evidence.",
        "View metadata: latest compatibility state reflects the current rows in `compliance_records`; "
        "select a run below to inspect persisted baseline, candidate, or historical extraction history.",
        "Ingest documents and run extraction to populate this SQLite-backed dashboard. "
        "Looking for persisted records in `empty-dashboard.db`.",
    ]
    assert fake_st.dataframes == []
    assert fake_st.selectboxes[0]["label"] == "Extraction run view"


def test_render_compliance_tab_populated_source_detail_is_lazy_and_tolerates_missing_image(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    image_calls: list[tuple[str, str, int]] = []
    rows = [
        {
            "doc_id": "doc-render-001",
            "doc_type": "Supplier Declaration Form",
            "vendor_name": "Acme Pharma",
            "manufacturing_date": "2024-01-05",
            "effective_date": "2024-02-01",
            "revision_date": "2024-03-15",
            "expiry_date": "2026-01-31",
            "aggregate_confidence": 0.86,
            "review_state": "pending",
            "needs_review": 1,
            "trace_id": "trace-render-001",
            "run_id": "run-render-001",
            "risk_level": "red",
            "risk_reason": "Document is expired.",
            "compliance_status": "needs_review",
            "age_days": 900,
            "source_page": 2,
            "source_bbox": '{"height":30,"width":100,"x":10,"y":20}',
            "source_verbatim_span": "Expiry Date: 2026-01-31",
        }
    ]

    monkeypatch.setattr("src.dashboard.compliance.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)
    monkeypatch.setattr("src.dashboard.compliance.load_compliance_rows", lambda db_path: rows)

    def fake_get_page_image(db_path: str, doc_id: str, page_num: int):
        image_calls.append((db_path, doc_id, page_num))
        return None

    monkeypatch.setattr("src.dashboard.compliance.get_page_image", fake_get_page_image)

    render_compliance_tab("populated-dashboard.db")

    assert fake_st.metrics[("Total documents", 1)] == 1
    assert fake_st.metrics[("Red", 1)] == 1
    assert fake_st.metrics[("Needs review", 1)] == 1
    assert fake_st.info_messages == [
        "Selected extraction view: current latest-write compatibility state.",
        "Current extraction state: latest persisted compliance rows from extraction run "
        "`run-render-001`. Historical baselines and candidates are preserved in the Eval tab.",
    ]
    assert fake_st.dataframes[0][0]["Risk"] == "Red"
    assert fake_st.dataframes[0][0]["Vendor"] == "Acme Pharma"
    assert "**Risk reason:** Document is expired." in fake_st.markdown_messages
    assert "**Source page:** Page 3" in fake_st.markdown_messages
    assert "**Source verbatim span:** Expiry Date: 2026-01-31" in fake_st.markdown_messages
    assert fake_st.caption_messages == [
        "Review extracted compliance status and risk signals with source evidence.",
        "View metadata: latest compatibility state reflects the current rows in `compliance_records`; "
        "select a run below to inspect persisted baseline, candidate, or historical extraction history.",
        "No source preview available for the selected document/page.",
    ]
    assert fake_st.images == []
    assert image_calls == [("populated-dashboard.db", "doc-render-001", 2)]


def test_render_compliance_tab_selected_run_labels_and_rows_change(tmp_db_path: str, monkeypatch) -> None:
    prepare_compliance_db(tmp_db_path)
    upsert_extraction_record(
        tmp_db_path,
        make_record(
            vendor_name="Baseline Vendor",
            trace_id="trace-baseline",
            run_id="run-baseline-001",
            risk_level="green",
            risk_reason="Baseline document is in date.",
            compliance_status="compliant",
            age_days=100,
        ),
    )
    upsert_extraction_record(
        tmp_db_path,
        make_record(
            vendor_name="Candidate Vendor",
            trace_id="trace-candidate",
            run_id="run-candidate-001",
            risk_level="red",
            risk_reason="Candidate document is expired.",
            compliance_status="needs_review",
            age_days=900,
        ),
    )
    fake_st = FakeStreamlit()
    fake_st.selected_options_by_label["Extraction run view"] = "run:run-baseline-001"

    monkeypatch.setattr("src.dashboard.compliance.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)

    render_compliance_tab(tmp_db_path)

    extraction_selector = fake_st.selectboxes[0]
    assert extraction_selector["label"] == "Extraction run view"
    assert extraction_selector["options"] == ["latest", "run:run-baseline-001", "run:run-candidate-001"]
    assert any("Baseline run: run-baseline-001" in label for label in extraction_selector["labels"])
    assert any("Candidate run: run-candidate-001" in label for label in extraction_selector["labels"])
    assert fake_st.info_messages[0] == "Selected extraction view: Baseline run `run-baseline-001`."
    assert "view=Baseline run" in fake_st.caption_messages[1]
    assert "trace_id=trace-baseline" in fake_st.caption_messages[1]
    assert fake_st.dataframes[0][0]["Vendor"] == "Baseline Vendor"
    assert fake_st.dataframes[0][0]["Run ID"] == "run-baseline-001"
    assert fake_st.dataframes[0][0]["Trace ID"] == "trace-baseline"
    assert all(row["Vendor"] != "Candidate Vendor" for row in fake_st.dataframes[0])
    assert fake_st.info_messages[1] == (
        "Selected extraction state: showing only rows from Baseline run `run-baseline-001`; "
        "latest-write compatibility rows are not mixed into this historical view."
    )


def test_render_compliance_tab_unknown_historical_empty_state_names_selected_run(tmp_db_path: str, monkeypatch) -> None:
    prepare_compliance_db(tmp_db_path)
    upsert_extraction_record(tmp_db_path, make_record(vendor_name="Latest Vendor", run_id="run-latest-001"))
    conn = sqlite3.connect(tmp_db_path)
    conn.execute(
        """
        INSERT INTO extraction_runs (
            run_id, status, document_count, field_count, trace_id,
            started_at, completed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-qa-archive-001",
            "completed",
            0,
            0,
            "trace-archive",
            "2026-05-19T12:30:00+00:00",
            "2026-05-19T12:31:00+00:00",
            "2026-05-19T12:30:00+00:00",
            "2026-05-19T12:31:00+00:00",
        ),
    )
    conn.commit()
    conn.close()
    fake_st = FakeStreamlit()
    fake_st.selected_options_by_label["Extraction run view"] = "run:run-qa-archive-001"

    monkeypatch.setattr("src.dashboard.compliance.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)
    monkeypatch.setattr("src.dashboard.compliance.render_empty_state", fake_st.render_empty_state)

    render_compliance_tab(tmp_db_path)

    assert fake_st.info_messages == [
        "Selected extraction view: Historical run `run-qa-archive-001`.",
        "No compliance records are available for Historical run `run-qa-archive-001`.",
    ]
    assert "Selected view: Historical run `run-qa-archive-001`" in fake_st.caption_messages[-1]
    assert "trace_id=trace-archive" in fake_st.caption_messages[-1]
    assert fake_st.dataframes == []


def test_render_compliance_tab_source_detail_image_lookup_uses_selected_run_row(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.selected_options_by_label["Extraction run view"] = "run:run-candidate-visual"
    fake_st.selected_options_by_label["Select a document"] = "doc-selected"
    image_calls: list[tuple[str, str, int]] = []
    summaries = [
        ExtractionRunSummary(
            run_id="run-candidate-visual",
            status="completed",
            document_count=2,
            field_count=12,
            trace_id="trace-candidate-visual",
            started_at="2026-05-19T12:30:00+00:00",
            completed_at="2026-05-19T12:31:00+00:00",
            created_at="2026-05-19T12:30:00+00:00",
            updated_at="2026-05-19T12:31:00+00:00",
        )
    ]
    rows = [
        {
            "doc_id": "doc-unselected",
            "doc_type": "Supplier Declaration Form",
            "vendor_name": "Unselected Vendor",
            "trace_id": "trace-candidate-visual",
            "run_id": "run-candidate-visual",
            "risk_level": "green",
            "risk_reason": "Unselected row.",
            "compliance_status": "compliant",
            "source_page": 1,
            "source_bbox": "{}",
            "source_verbatim_span": "Unselected span",
        },
        {
            "doc_id": "doc-selected",
            "doc_type": "Supplier Declaration Form",
            "vendor_name": "Selected Vendor",
            "trace_id": "trace-candidate-visual",
            "run_id": "run-candidate-visual",
            "risk_level": "amber",
            "risk_reason": "Selected row.",
            "compliance_status": "needs_review",
            "source_page": 4,
            "source_bbox": "{}",
            "source_verbatim_span": "Selected span",
        },
    ]

    monkeypatch.setattr("src.dashboard.compliance.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)
    monkeypatch.setattr("src.dashboard.compliance.load_extraction_run_summaries", lambda db_path: summaries)
    monkeypatch.setattr("src.dashboard.compliance._load_compliance_rows_for_selection", lambda *args: rows)

    def fake_get_page_image(db_path: str, doc_id: str, page_num: int):
        image_calls.append((db_path, doc_id, page_num))
        return b"image-bytes"

    monkeypatch.setattr("src.dashboard.compliance.get_page_image", fake_get_page_image)

    render_compliance_tab("visual-dashboard.db")

    assert fake_st.dataframes[0][0]["Vendor"] == "Unselected Vendor"
    assert fake_st.dataframes[0][1]["Vendor"] == "Selected Vendor"
    assert "**Risk reason:** Selected row." in fake_st.markdown_messages
    assert image_calls == [("visual-dashboard.db", "doc-selected", 4)]
    assert fake_st.images == [(b"image-bytes", "Page 5")]


class FakeMetricColumn:
    def __init__(self, parent: "FakeStreamlit") -> None:
        self.parent = parent

    def metric(self, label: str, value: int) -> None:
        self.parent.metrics[(label, value)] = self.parent.metrics.get((label, value), 0) + 1


class FakeStreamlit:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.caption_messages: list[str] = []
        self.dataframes: list[list[dict[str, object]]] = []
        self.markdown_messages: list[str] = []
        self.images: list[object] = []
        self.metrics: dict[tuple[str, int], int] = {}
        self.subheaders: list[str] = []
        self.headers: list[str] = []
        self.divider_count = 0
        self.selectboxes: list[dict[str, object]] = []
        self.selected_options_by_label: dict[str, str] = {}

    def header(self, message: str) -> None:
        self.headers.append(message)

    def divider(self) -> None:
        self.divider_count += 1

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def caption(self, message: str) -> None:
        self.caption_messages.append(message)

    def render_empty_state(self, message: str, *, caption: str | None = None) -> None:
        self.info_messages.append(message)
        if caption:
            self.caption_messages.append(caption)

    def columns(self, count: int) -> list[FakeMetricColumn]:
        return [FakeMetricColumn(self) for _ in range(count)]

    def dataframe(self, rows, *, hide_index: bool, width: str) -> None:
        assert hide_index is True
        assert width == "stretch"
        self.dataframes.append(rows)

    def subheader(self, message: str) -> None:
        self.subheaders.append(message)

    def selectbox(self, label: str, *, options: list[str], format_func=None) -> str:
        assert label in {"Extraction run view", "Select a document"}
        labels = [format_func(option) if format_func is not None else option for option in options]
        self.selectboxes.append({"label": label, "options": list(options), "labels": labels})
        selected = self.selected_options_by_label.get(label, options[0])
        assert selected in options
        return selected

    def markdown(self, message: str) -> None:
        self.markdown_messages.append(message)

    def image(self, image, *, caption: str) -> None:
        self.images.append((image, caption))
