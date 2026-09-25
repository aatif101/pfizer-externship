"""Tests for the HITL review repository (src/extraction/review.py).

All tests run against a temporary SQLite database. Records are seeded through the
normal extraction repository (run-scoped, so history rows exist) and review
actions are then applied through ``apply_field_review``.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest

from src.db.queries import insert_document
from src.db.schema import init_db
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.repository import upsert_extraction_record


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/test_extraction_persistence.py)
# ---------------------------------------------------------------------------


def make_field(
    field_name: SDFFieldName,
    raw_value: str | None,
    *,
    normalized_date: date | None = None,
    confidence: float = 0.9,
    page_num: int = 0,
    review_state: ReviewState = ReviewState.PENDING,
    abstention_reason: str | None = None,
) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=raw_value,
        normalized_date=normalized_date,
        confidence=confidence,
        evidence=SourceEvidence(
            page_num=page_num,
            bbox={"x": 10 + page_num, "y": 20, "width": 100, "height": 30},
            verbatim_span=raw_value,
        ),
        review_state=review_state,
        abstention_reason=abstention_reason,
    )


def abstained_field(field_name: SDFFieldName, reason: str = "Provider returned no value.", *, confidence: float = 0.0) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        confidence=confidence,
        evidence=SourceEvidence(page_num=0),
        review_state=ReviewState.ABSTAINED,
        abstention_reason=reason,
    )


def default_fields() -> dict[SDFFieldName, ExtractedField]:
    return {
        SDFFieldName.DOC_TYPE: make_field(SDFFieldName.DOC_TYPE, "Certificate of Analysis", confidence=0.96),
        SDFFieldName.VENDOR_NAME: make_field(SDFFieldName.VENDOR_NAME, "Acme Pharma", confidence=0.92),
        SDFFieldName.MANUFACTURING_DATE: make_field(
            SDFFieldName.MANUFACTURING_DATE, "2025-06-01", normalized_date=date(2025, 6, 1), confidence=0.88, page_num=1
        ),
        SDFFieldName.EFFECTIVE_DATE: make_field(
            SDFFieldName.EFFECTIVE_DATE, "2025-06-15", normalized_date=date(2025, 6, 15), confidence=0.9, page_num=1
        ),
        SDFFieldName.REVISION_DATE: make_field(
            SDFFieldName.REVISION_DATE, "2025-07-01", normalized_date=date(2025, 7, 1), confidence=0.91, page_num=1
        ),
        SDFFieldName.EXPIRY_DATE: make_field(
            SDFFieldName.EXPIRY_DATE,
            "2027-06-01",
            normalized_date=date(2027, 6, 1),
            confidence=0.6,
            page_num=2,
            review_state=ReviewState.NEEDS_REVIEW,
        ),
    }


def seed_record(
    db_path: str,
    *,
    doc_id: str = "doc-001",
    filename: str | None = None,
    overrides: dict[SDFFieldName, ExtractedField] | None = None,
    run_id: str | None = "run-001",
    page_count: int = 3,
) -> SDFExtractionRecord:
    """Insert a document plus a run-scoped extraction record (history rows included)."""

    insert_document(
        db_path,
        doc_id=doc_id,
        filename=filename or f"{doc_id}.pdf",
        file_path=f"/tmp/{doc_id}.pdf",
        page_count=page_count,
        docling_json=None,
    )
    fields = default_fields()
    fields.update(overrides or {})
    record = SDFExtractionRecord(
        doc_id=doc_id,
        filename=filename or f"{doc_id}.pdf",
        fields=fields,
        trace_id="trace-extract-001",
        run_id=run_id,
        extracted_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
        risk_level="green",
        risk_reason="seeded",
        compliance_status="compliant",
        age_days=100,
    )
    upsert_extraction_record(db_path, record)
    return record


def dump_table(db_path: str, table_name: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT * FROM {table_name} ORDER BY rowid").fetchall()
    finally:
        conn.close()


def fetch_one(db_path: str, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def table_count(db_path: str, table_name: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Task 1: human evidence tier + review queue
# ---------------------------------------------------------------------------


def test_source_evidence_accepts_human_tier() -> None:
    evidence = SourceEvidence(page_num=0, verbatim_span="x", evidence_type="human")
    assert evidence.evidence_type == "human"
    with pytest.raises(ValueError):
        SourceEvidence(page_num=0, verbatim_span="x", evidence_type="other")


def test_queue_empty_db(tmp_db_path: str) -> None:
    from src.extraction.review import list_review_queue

    init_db(tmp_db_path)
    assert list_review_queue(tmp_db_path, threshold=0.75) == []


def _queue_selection_overrides() -> dict[SDFFieldName, ExtractedField]:
    return {
        SDFFieldName.DOC_TYPE: make_field(SDFFieldName.DOC_TYPE, "Certificate of Analysis", confidence=0.95),
        SDFFieldName.VENDOR_NAME: make_field(SDFFieldName.VENDOR_NAME, "Acme Pharma", confidence=0.60),
        SDFFieldName.MANUFACTURING_DATE: make_field(
            SDFFieldName.MANUFACTURING_DATE,
            "2025-06-01",
            normalized_date=date(2025, 6, 1),
            confidence=0.80,
            page_num=1,
            review_state=ReviewState.NEEDS_REVIEW,
        ),
        SDFFieldName.EFFECTIVE_DATE: abstained_field(SDFFieldName.EFFECTIVE_DATE, confidence=0.1),
        SDFFieldName.REVISION_DATE: make_field(
            SDFFieldName.REVISION_DATE,
            "2025-07-01",
            normalized_date=date(2025, 7, 1),
            confidence=0.50,
            page_num=1,
            review_state=ReviewState.REVIEWED,
        ),
        SDFFieldName.EXPIRY_DATE: abstained_field(
            SDFFieldName.EXPIRY_DATE, "Reviewer confirmed: field not present in document", confidence=0.0
        ),
    }


def test_queue_selection(tmp_db_path: str) -> None:
    from src.extraction.review import list_review_queue

    init_db(tmp_db_path)
    seed_record(tmp_db_path, overrides=_queue_selection_overrides())

    queue = list_review_queue(tmp_db_path, threshold=0.75)

    assert [item.field_name for item in queue] == ["effective_date", "vendor_name", "manufacturing_date"]
    confidences = [item.confidence for item in queue]
    assert confidences == sorted(confidences)


def test_queue_orders_ties_by_filename_then_field(tmp_db_path: str) -> None:
    from src.extraction.review import list_review_queue

    init_db(tmp_db_path)
    low_vendor = {SDFFieldName.VENDOR_NAME: make_field(SDFFieldName.VENDOR_NAME, "Acme Pharma", confidence=0.5)}
    seed_record(tmp_db_path, doc_id="doc-b", filename="b.pdf", overrides=low_vendor)
    seed_record(tmp_db_path, doc_id="doc-a", filename="a.pdf", overrides=low_vendor)

    queue = list_review_queue(tmp_db_path, threshold=0.75)

    assert [(item.filename, item.field_name) for item in queue] == [
        ("a.pdf", "vendor_name"),
        ("b.pdf", "vendor_name"),
        ("a.pdf", "expiry_date"),
        ("b.pdf", "expiry_date"),
    ]


def test_queue_item_shape(tmp_db_path: str) -> None:
    from src.extraction.review import ReviewQueueItem, list_review_queue

    init_db(tmp_db_path)
    seed_record(tmp_db_path, overrides=_queue_selection_overrides())

    queue = list_review_queue(tmp_db_path, threshold=0.75)
    by_field = {item.field_name: item for item in queue}

    vendor = by_field["vendor_name"]
    assert isinstance(vendor, ReviewQueueItem)
    assert vendor.doc_id == "doc-001"
    assert vendor.filename == "doc-001.pdf"
    assert vendor.current_value == "Acme Pharma"
    assert vendor.confidence == pytest.approx(0.60)
    assert vendor.source_page == 0
    assert vendor.verbatim_span == "Acme Pharma"
    assert vendor.evidence_type == "text"
    assert vendor.review_state == "pending"
    assert vendor.abstention_reason is None

    manufacturing = by_field["manufacturing_date"]
    assert manufacturing.current_value == "2025-06-01"
    assert manufacturing.source_page == 1
    assert manufacturing.review_state == "needs_review"

    effective = by_field["effective_date"]
    assert effective.current_value is None
    assert effective.review_state == "abstained"
    assert effective.abstention_reason == "Provider returned no value."

    with pytest.raises(Exception):
        vendor.confidence = 1.0  # type: ignore[misc]  # frozen dataclass
