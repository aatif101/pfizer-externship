"""Tests for the compliance dashboard read/format adapter."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from src.dashboard.compliance import format_compliance_rows, load_compliance_rows, render_compliance_tab
from src.db.queries import insert_document
from src.db.schema import init_db
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.repository import upsert_extraction_record


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


def make_record() -> SDFExtractionRecord:
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
                "Acme Pharma",
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
                "2026-01-31",
                normalized_date=date(2026, 1, 31),
                confidence=0.78,
                page_num=2,
                verbatim_span="Expiry Date: 2026-01-31",
            ),
        },
        trace_id="trace-dashboard-001",
        run_id="run-dashboard-001",
        extracted_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
        risk_level="amber",
        risk_reason="Oldest relevant date is between 2 and 3 years old.",
        compliance_status="needs_review",
        age_days=865,
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
    monkeypatch.setattr("src.dashboard.compliance.load_compliance_rows", lambda db_path: [])

    render_compliance_tab("empty-dashboard.db")

    assert fake_st.info_messages == [
        "No compliance records are available yet. Ingest documents and run extraction "
        "to populate this SQLite-backed dashboard."
    ]
    assert fake_st.caption_messages == ["Looking for persisted records in `empty-dashboard.db`."]
    assert fake_st.dataframes == []


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
    monkeypatch.setattr("src.dashboard.compliance.load_compliance_rows", lambda db_path: rows)

    def fake_get_page_image(db_path: str, doc_id: str, page_num: int):
        image_calls.append((db_path, doc_id, page_num))
        return None

    monkeypatch.setattr("src.dashboard.compliance.get_page_image", fake_get_page_image)

    render_compliance_tab("populated-dashboard.db")

    assert fake_st.metrics[("Total documents", 1)] == 1
    assert fake_st.metrics[("Red", 1)] == 1
    assert fake_st.metrics[("Needs review", 1)] == 1
    assert fake_st.dataframes[0][0]["Risk"] == "Red"
    assert fake_st.dataframes[0][0]["Vendor"] == "Acme Pharma"
    assert "**Risk reason:** Document is expired." in fake_st.markdown_messages
    assert "**Source page:** Page 3" in fake_st.markdown_messages
    assert "**Source verbatim span:** Expiry Date: 2026-01-31" in fake_st.markdown_messages
    assert fake_st.caption_messages == ["No source preview available for the selected document/page."]
    assert fake_st.images == []
    assert image_calls == [("populated-dashboard.db", "doc-render-001", 2)]


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

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def caption(self, message: str) -> None:
        self.caption_messages.append(message)

    def columns(self, count: int) -> list[FakeMetricColumn]:
        return [FakeMetricColumn(self) for _ in range(count)]

    def dataframe(self, rows, *, hide_index: bool, use_container_width: bool) -> None:
        assert hide_index is True
        assert use_container_width is True
        self.dataframes.append(rows)

    def subheader(self, message: str) -> None:
        self.subheaders.append(message)

    def selectbox(self, label: str, *, options: list[str]) -> str:
        assert label == "Select a document"
        return options[0]

    def markdown(self, message: str) -> None:
        self.markdown_messages.append(message)

    def image(self, image, *, caption: str) -> None:
        self.images.append((image, caption))
