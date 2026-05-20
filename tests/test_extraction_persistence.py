"""Tests for idempotent SDF extraction persistence."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest

from src.db.queries import insert_document
from src.db.schema import init_db
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
from src.extraction.repository import (
    get_extraction_record,
    list_compliance_records,
    upsert_extraction_field,
    upsert_extraction_record,
)


def make_field(
    field_name: SDFFieldName,
    raw_value: str | None,
    *,
    normalized_value: str | None = None,
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
        normalized_value=normalized_value if normalized_value is not None else raw_value,
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
    doc_id: str = "doc-001",
    filename: str = "supplier-sdf.pdf",
    vendor_name: str = "Acme Pharma",
    expiry_date: date | None = date(2026, 1, 31),
    expiry_state: ReviewState = ReviewState.PENDING,
    expiry_reason: str | None = None,
    trace_id: str = "trace-001",
    risk_level: str | None = None,
    risk_reason: str | None = None,
    compliance_status: str | None = None,
    age_days: int | None = None,
) -> SDFExtractionRecord:
    fields = {
        SDFFieldName.DOC_TYPE: make_field(SDFFieldName.DOC_TYPE, "Supplier Declaration Form", normalized_value="SDF", confidence=0.96),
        SDFFieldName.VENDOR_NAME: make_field(SDFFieldName.VENDOR_NAME, vendor_name, confidence=0.92),
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
            expiry_date.isoformat() if expiry_date else None,
            normalized_date=expiry_date,
            confidence=0.78 if expiry_date else 0.0,
            page_num=2,
            review_state=expiry_state,
            abstention_reason=expiry_reason,
            verbatim_span=expiry_date.isoformat() if expiry_date else None,
        ),
    }
    return SDFExtractionRecord(
        doc_id=doc_id,
        filename=filename,
        fields=fields,
        trace_id=trace_id,
        run_id="run-001",
        extracted_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
        risk_level=risk_level,
        risk_reason=risk_reason,
        compliance_status=compliance_status,
        age_days=age_days,
    )


def prepare_db(db_path: str, *doc_ids: str) -> None:
    init_db(db_path)
    for doc_id in doc_ids:
        insert_document(
            db_path,
            doc_id=doc_id,
            filename=f"{doc_id}.pdf",
            file_path=f"/tmp/{doc_id}.pdf",
            page_count=3,
            docling_json=None,
        )


def table_count(db_path: str, table_name: str) -> int:
    conn = sqlite3.connect(db_path)
    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    conn.close()
    return count


def test_upsert_record_round_trips_field_and_compliance_rows(tmp_db_path: str) -> None:
    prepare_db(tmp_db_path, "doc-001")
    record = make_record(
        risk_level="amber",
        risk_reason="Oldest relevant date 2024-01-05 is 865 days old, between 2 and 3 years.",
        compliance_status="needs_review",
        age_days=865,
    )

    upsert_extraction_record(tmp_db_path, record)

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert stored.doc_id == record.doc_id
    assert stored.filename == "doc-001.pdf"
    assert stored.trace_id == "trace-001"
    assert stored.fields[SDFFieldName.EXPIRY_DATE].evidence.page_num == 2
    assert stored.fields[SDFFieldName.EXPIRY_DATE].evidence.bbox == {"x": 12, "y": 20, "width": 100, "height": 30}
    assert stored.dashboard_values[SDFFieldName.EXPIRY_DATE.value] == "2026-01-31"
    assert stored.risk_level == "amber"
    assert stored.risk_reason == "Oldest relevant date 2024-01-05 is 865 days old, between 2 and 3 years."
    assert stored.compliance_status == "needs_review"
    assert stored.age_days == 865

    rows = list_compliance_records(tmp_db_path)
    assert rows == [
        {
            "doc_id": "doc-001",
            "doc_type": "SDF",
            "vendor_name": "Acme Pharma",
            "manufacturing_date": "2024-01-05",
            "effective_date": "2024-02-01",
            "revision_date": "2024-03-15",
            "expiry_date": "2026-01-31",
            "aggregate_confidence": pytest.approx(record.aggregate_confidence),
            "review_state": "pending",
            "needs_review": 0,
            "trace_id": "trace-001",
            "run_id": "run-001",
            "extracted_at": "2026-05-19T12:00:00+00:00",
            "risk_level": "amber",
            "risk_reason": "Oldest relevant date 2024-01-05 is 865 days old, between 2 and 3 years.",
            "compliance_status": "needs_review",
            "age_days": 865,
            "source_page": 2,
            "source_bbox": '{"height":30,"width":100,"x":12,"y":20}',
            "source_verbatim_span": "2026-01-31",
        }
    ]


def test_unknown_parent_document_raises_fk_integrity_error(tmp_db_path: str) -> None:
    init_db(tmp_db_path)

    with pytest.raises(sqlite3.IntegrityError):
        upsert_extraction_record(tmp_db_path, make_record(doc_id="missing-doc"))


def test_record_upsert_is_idempotent_and_replaces_existing_values(tmp_db_path: str) -> None:
    prepare_db(tmp_db_path, "doc-001")

    upsert_extraction_record(tmp_db_path, make_record(vendor_name="Old Vendor", trace_id="trace-old"))
    upsert_extraction_record(tmp_db_path, make_record(vendor_name="Updated Vendor", trace_id="trace-new"))

    assert table_count(tmp_db_path, "extractions") == 6
    assert table_count(tmp_db_path, "compliance_records") == 1

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert stored.fields[SDFFieldName.VENDOR_NAME].raw_value == "Updated Vendor"
    assert stored.trace_id == "trace-new"
    assert list_compliance_records(tmp_db_path)[0]["vendor_name"] == "Updated Vendor"


def test_sql_metacharacters_round_trip_safely(tmp_db_path: str) -> None:
    prepare_db(tmp_db_path, "doc-001")
    hostile_vendor = "O'Brien Labs'); DROP TABLE documents; --"

    upsert_extraction_record(tmp_db_path, make_record(vendor_name=hostile_vendor))

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    assert stored.fields[SDFFieldName.VENDOR_NAME].raw_value == hostile_vendor
    assert list_compliance_records(tmp_db_path)[0]["vendor_name"] == hostile_vendor
    assert table_count(tmp_db_path, "documents") == 1


def test_abstention_persists_null_value_reason_and_document_review_state(tmp_db_path: str) -> None:
    prepare_db(tmp_db_path, "doc-001")
    record = make_record(
        expiry_date=None,
        expiry_state=ReviewState.ABSTAINED,
        expiry_reason="Expiry date was not present on the supplied page.",
    )

    upsert_extraction_record(tmp_db_path, record)

    stored = get_extraction_record(tmp_db_path, "doc-001")
    assert stored is not None
    expiry = stored.fields[SDFFieldName.EXPIRY_DATE]
    assert expiry.raw_value is None
    assert expiry.normalized_value is None
    assert expiry.review_state == ReviewState.ABSTAINED
    assert expiry.abstention_reason == "Expiry date was not present on the supplied page."
    assert expiry.needs_review is True

    compliance = list_compliance_records(tmp_db_path)[0]
    assert compliance["expiry_date"] is None
    assert compliance["review_state"] == "needs_review"
    assert compliance["needs_review"] == 1
    assert compliance["source_page"] == 0


def test_single_field_upsert_replaces_value_without_duplicate_rows(tmp_db_path: str) -> None:
    prepare_db(tmp_db_path, "doc-001")

    upsert_extraction_field(tmp_db_path, "doc-001", make_field(SDFFieldName.VENDOR_NAME, "Vendor A"), "trace-a")
    upsert_extraction_field(tmp_db_path, "doc-001", make_field(SDFFieldName.VENDOR_NAME, "Vendor B"), "trace-b")

    conn = sqlite3.connect(tmp_db_path)
    rows = conn.execute(
        "SELECT field_value, trace_id FROM extractions WHERE doc_id = ? AND field_name = ?",
        ("doc-001", "vendor_name"),
    ).fetchall()
    conn.close()

    assert rows == [("Vendor B", "trace-b")]


def test_list_compliance_records_orders_expiring_docs_before_nulls(tmp_db_path: str) -> None:
    prepare_db(tmp_db_path, "doc-late", "doc-null", "doc-early")

    upsert_extraction_record(
        tmp_db_path,
        make_record(doc_id="doc-late", filename="late.pdf", vendor_name="Late Vendor", expiry_date=date(2027, 1, 1)),
    )
    upsert_extraction_record(
        tmp_db_path,
        make_record(
            doc_id="doc-null",
            filename="null.pdf",
            vendor_name="Null Vendor",
            expiry_date=None,
            expiry_state=ReviewState.ABSTAINED,
            expiry_reason="No expiry date.",
        ),
    )
    upsert_extraction_record(
        tmp_db_path,
        make_record(doc_id="doc-early", filename="early.pdf", vendor_name="Early Vendor", expiry_date=date(2025, 1, 1)),
    )

    rows = list_compliance_records(tmp_db_path)

    assert [row["doc_id"] for row in rows] == ["doc-early", "doc-late", "doc-null"]
    assert set(rows[0]) == {
        "doc_id",
        "doc_type",
        "vendor_name",
        "manufacturing_date",
        "effective_date",
        "revision_date",
        "expiry_date",
        "aggregate_confidence",
        "review_state",
        "needs_review",
        "trace_id",
        "run_id",
        "extracted_at",
        "risk_level",
        "risk_reason",
        "compliance_status",
        "age_days",
        "source_page",
        "source_bbox",
        "source_verbatim_span",
    }
