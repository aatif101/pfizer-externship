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


# ---------------------------------------------------------------------------
# Task 2: apply_field_review
# ---------------------------------------------------------------------------

TODAY = date(2026, 9, 23)
_LATEST_TABLES = ("extractions", "compliance_records", "extraction_reviews")
_HISTORY_TABLES = ("extraction_history", "compliance_record_history")


def snapshot(db_path: str, tables: tuple[str, ...]) -> dict[str, list[tuple]]:
    return {table: dump_table(db_path, table) for table in tables}


def extraction_row(db_path: str, field_name: str, doc_id: str = "doc-001") -> sqlite3.Row:
    row = fetch_one(db_path, "SELECT * FROM extractions WHERE doc_id = ? AND field_name = ?", (doc_id, field_name))
    assert row is not None
    return row


def compliance_row(db_path: str, doc_id: str = "doc-001") -> sqlite3.Row:
    row = fetch_one(db_path, "SELECT * FROM compliance_records WHERE doc_id = ?", (doc_id,))
    assert row is not None
    return row


def test_correct_updates_compliance_db(tmp_db_path: str) -> None:
    from src.extraction.review import apply_field_review, list_review_queue

    init_db(tmp_db_path)
    seed_record(tmp_db_path)

    outcome = apply_field_review(
        tmp_db_path,
        doc_id="doc-001",
        field_name="expiry_date",
        action="correct",
        corrected_value="2020-01-01",
        source_page=0,
        today=TODAY,
    )

    field = extraction_row(tmp_db_path, "expiry_date")
    assert field["review_state"] == "reviewed"
    assert field["evidence_type"] == "human"
    assert field["confidence"] == pytest.approx(1.0)
    assert field["normalized_value"] == "2020-01-01"
    assert field["source_page"] == 0
    assert field["needs_review"] == 0
    assert field["abstention_reason"] is None

    compliance = compliance_row(tmp_db_path)
    assert compliance["expiry_date"] == "2020-01-01"
    assert compliance["risk_level"] == "red"
    assert compliance["compliance_status"] == "at_risk"
    assert compliance["needs_review"] == 0

    audits = dump_table(tmp_db_path, "extraction_reviews")
    assert len(audits) == 1
    audit = fetch_one(tmp_db_path, "SELECT * FROM extraction_reviews")
    assert audit["action"] == "correct"
    assert audit["doc_id"] == "doc-001"
    assert audit["field_name"] == "expiry_date"
    assert audit["previous_value"] == "2027-06-01"
    assert audit["new_value"] == "2020-01-01"
    assert audit["previous_confidence"] == pytest.approx(0.6)
    assert audit["previous_review_state"] == "needs_review"
    assert audit["source_page"] == 0
    assert audit["reviewer"] == "demo-reviewer"
    assert audit["run_id"] == "run-001"
    assert audit["reviewed_at"] is not None

    assert outcome.review_id == audit["review_id"]
    assert outcome.action == "correct"
    assert outcome.field_name == "expiry_date"
    assert outcome.new_review_state == "reviewed"
    assert outcome.risk_level == "red"
    assert outcome.compliance_needs_review is False
    assert list_review_queue(tmp_db_path, threshold=0.75) == []


def test_correct_accepts_pharma_date_format(tmp_db_path: str) -> None:
    from src.extraction.review import apply_field_review

    init_db(tmp_db_path)
    seed_record(tmp_db_path)

    apply_field_review(
        tmp_db_path,
        doc_id="doc-001",
        field_name="expiry_date",
        action="correct",
        corrected_value="01-JAN-2024",
        source_page=2,
        today=TODAY,
    )

    assert extraction_row(tmp_db_path, "expiry_date")["normalized_value"] == "2024-01-01"
    assert compliance_row(tmp_db_path)["expiry_date"] == "2024-01-01"


def test_correct_text_field_keeps_reviewer_text(tmp_db_path: str) -> None:
    from src.extraction.review import apply_field_review

    init_db(tmp_db_path)
    seed_record(tmp_db_path)

    apply_field_review(
        tmp_db_path,
        doc_id="doc-001",
        field_name="vendor_name",
        action="correct",
        corrected_value="  Acme Pharma GmbH  ",
        source_page=1,
        today=TODAY,
    )

    field = extraction_row(tmp_db_path, "vendor_name")
    assert field["field_value"] == "Acme Pharma GmbH"
    assert field["verbatim_span"] == "Acme Pharma GmbH"
    assert field["source_page"] == 1
    assert compliance_row(tmp_db_path)["vendor_name"] == "Acme Pharma GmbH"


@pytest.mark.parametrize("bad_value", ["not a date", "2024-05", "31-FEB-2024", "1850-01-01"])
def test_invalid_date_rolls_back(tmp_db_path: str, bad_value: str) -> None:
    from src.extraction.review import ReviewInputError, apply_field_review

    init_db(tmp_db_path)
    seed_record(tmp_db_path)
    before = snapshot(tmp_db_path, _LATEST_TABLES)

    with pytest.raises(ReviewInputError) as exc_info:
        apply_field_review(
            tmp_db_path,
            doc_id="doc-001",
            field_name="expiry_date",
            action="correct",
            corrected_value=bad_value,
            source_page=0,
            today=TODAY,
        )

    assert exc_info.value.reason_code == "invalid_date"
    assert snapshot(tmp_db_path, _LATEST_TABLES) == before


@pytest.mark.parametrize(
    ("kwargs", "reason_code"),
    [
        ({"field_name": "lot_number", "action": "approve"}, "unknown_field"),
        ({"field_name": "expiry_date", "action": "delete"}, "unknown_action"),
        ({"field_name": "expiry_date", "action": "correct", "source_page": 0}, "value_required"),
        ({"field_name": "expiry_date", "action": "correct", "corrected_value": "   ", "source_page": 0}, "value_required"),
        ({"field_name": "expiry_date", "action": "correct", "corrected_value": "2020-01-01"}, "source_page_required"),
        ({"field_name": "expiry_date", "action": "correct", "corrected_value": "2020-01-01", "source_page": -1}, "source_page_required"),
        ({"field_name": "expiry_date", "action": "correct", "corrected_value": "2020-01-01", "source_page": 3}, "source_page_out_of_range"),
        ({"field_name": "vendor_name", "action": "correct", "corrected_value": "x" * 201, "source_page": 0}, "value_too_long"),
        ({"field_name": "expiry_date", "action": "approve", "note": "n" * 1001}, "note_too_long"),
        ({"field_name": "expiry_date", "action": "approve", "doc_id": "doc-missing"}, "record_not_found"),
    ],
)
def test_input_validation(tmp_db_path: str, kwargs: dict, reason_code: str) -> None:
    from src.extraction.review import ReviewInputError, apply_field_review

    init_db(tmp_db_path)
    seed_record(tmp_db_path)
    before = snapshot(tmp_db_path, _LATEST_TABLES + _HISTORY_TABLES)
    call_kwargs = {"doc_id": "doc-001", "today": TODAY, **kwargs}

    with pytest.raises(ReviewInputError) as exc_info:
        apply_field_review(tmp_db_path, **call_kwargs)

    assert exc_info.value.reason_code == reason_code
    assert snapshot(tmp_db_path, _LATEST_TABLES + _HISTORY_TABLES) == before


def test_approve(tmp_db_path: str) -> None:
    from src.extraction.review import ReviewAction, ReviewInputError, apply_field_review

    init_db(tmp_db_path)
    seed_record(
        tmp_db_path,
        overrides={SDFFieldName.EFFECTIVE_DATE: abstained_field(SDFFieldName.EFFECTIVE_DATE)},
    )

    outcome = apply_field_review(
        tmp_db_path, doc_id="doc-001", field_name=SDFFieldName.EXPIRY_DATE, action="approve", today=TODAY
    )

    field = extraction_row(tmp_db_path, "expiry_date")
    assert field["review_state"] == "reviewed"
    assert field["confidence"] == pytest.approx(1.0)
    assert field["normalized_value"] == "2027-06-01"
    assert field["field_value"] == "2027-06-01"
    assert field["evidence_type"] == "text"
    assert outcome.new_review_state == "reviewed"
    audit = fetch_one(tmp_db_path, "SELECT * FROM extraction_reviews")
    assert audit["action"] == "approve"
    assert audit["previous_value"] == "2027-06-01"
    assert audit["new_value"] == "2027-06-01"
    # effective_date is still abstained (unresolved), so the document still needs review.
    assert compliance_row(tmp_db_path)["needs_review"] == 1
    assert outcome.compliance_needs_review is True

    before = snapshot(tmp_db_path, _LATEST_TABLES)
    with pytest.raises(ReviewInputError) as exc_info:
        apply_field_review(tmp_db_path, doc_id="doc-001", field_name="effective_date", action=ReviewAction.APPROVE, today=TODAY)
    assert exc_info.value.reason_code == "approve_requires_value"
    assert snapshot(tmp_db_path, _LATEST_TABLES) == before


def test_confirm_absent(tmp_db_path: str) -> None:
    from src.extraction.review import CONFIRMED_ABSENT_PREFIX, apply_field_review, list_review_queue

    init_db(tmp_db_path)
    seed_record(
        tmp_db_path,
        overrides={
            SDFFieldName.EXPIRY_DATE: abstained_field(SDFFieldName.EXPIRY_DATE, confidence=0.2),
        },
    )
    assert [item.field_name for item in list_review_queue(tmp_db_path, threshold=0.75)] == ["expiry_date"]
    assert compliance_row(tmp_db_path)["needs_review"] == 1

    outcome = apply_field_review(
        tmp_db_path, doc_id="doc-001", field_name="expiry_date", action="confirm_absent", today=TODAY
    )

    field = extraction_row(tmp_db_path, "expiry_date")
    assert field["review_state"] == "abstained"
    assert field["abstention_reason"].startswith(CONFIRMED_ABSENT_PREFIX)
    assert list_review_queue(tmp_db_path, threshold=0.75) == []
    compliance = compliance_row(tmp_db_path)
    assert compliance["needs_review"] == 0
    assert compliance["review_state"] == "pending"
    assert outcome.new_review_state == "abstained"
    assert outcome.compliance_needs_review is False
    audit = fetch_one(tmp_db_path, "SELECT * FROM extraction_reviews")
    assert audit["action"] == "confirm_absent"
    assert audit["previous_value"] is None
    assert audit["new_value"] is None
    assert audit["previous_review_state"] == "abstained"


def test_all_fields_resolved_marks_document_reviewed(tmp_db_path: str) -> None:
    from src.extraction.review import apply_field_review

    init_db(tmp_db_path)
    seed_record(
        tmp_db_path,
        overrides={SDFFieldName.EFFECTIVE_DATE: abstained_field(SDFFieldName.EFFECTIVE_DATE)},
    )
    for name in SDFFieldName:
        action = "confirm_absent" if name == SDFFieldName.EFFECTIVE_DATE else "approve"
        apply_field_review(tmp_db_path, doc_id="doc-001", field_name=name, action=action, today=TODAY)

    compliance = compliance_row(tmp_db_path)
    assert compliance["review_state"] == "reviewed"
    assert compliance["needs_review"] == 0
    assert table_count(tmp_db_path, "extraction_reviews") == 6


def test_history_untouched(tmp_db_path: str) -> None:
    from src.extraction.review import apply_field_review

    init_db(tmp_db_path)
    seed_record(
        tmp_db_path,
        overrides={SDFFieldName.EFFECTIVE_DATE: abstained_field(SDFFieldName.EFFECTIVE_DATE)},
    )
    before = snapshot(tmp_db_path, _HISTORY_TABLES)
    assert before["extraction_history"] and before["compliance_record_history"]

    apply_field_review(
        tmp_db_path,
        doc_id="doc-001",
        field_name="expiry_date",
        action="correct",
        corrected_value="2020-01-01",
        source_page=0,
        today=TODAY,
    )
    apply_field_review(tmp_db_path, doc_id="doc-001", field_name="vendor_name", action="approve", today=TODAY)
    apply_field_review(tmp_db_path, doc_id="doc-001", field_name="effective_date", action="confirm_absent", today=TODAY)

    assert snapshot(tmp_db_path, _HISTORY_TABLES) == before
    assert table_count(tmp_db_path, "extraction_reviews") == 3


def _state_without_updated_at(db_path: str, table: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    finally:
        conn.close()
    return [{key: row[key] for key in row.keys() if key != "updated_at"} for row in rows]


def test_reapply_same_review_is_state_idempotent(tmp_db_path: str) -> None:
    from src.extraction.review import apply_field_review

    init_db(tmp_db_path)
    seed_record(tmp_db_path)
    kwargs = {
        "doc_id": "doc-001",
        "field_name": "expiry_date",
        "action": "correct",
        "corrected_value": "2020-01-01",
        "source_page": 0,
        "today": TODAY,
    }

    apply_field_review(tmp_db_path, **kwargs)
    first = {table: _state_without_updated_at(tmp_db_path, table) for table in ("extractions", "compliance_records")}
    apply_field_review(tmp_db_path, **kwargs)
    second = {table: _state_without_updated_at(tmp_db_path, table) for table in ("extractions", "compliance_records")}

    assert first == second
    assert table_count(tmp_db_path, "extraction_reviews") == 2


def test_mid_transaction_failure_rolls_back(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.extraction import review

    init_db(tmp_db_path)
    seed_record(tmp_db_path)
    before = snapshot(tmp_db_path, _LATEST_TABLES + _HISTORY_TABLES)

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("risk recompute failed")

    monkeypatch.setattr(review, "compute_record_risk", _boom)

    with pytest.raises(RuntimeError):
        review.apply_field_review(
            tmp_db_path,
            doc_id="doc-001",
            field_name="expiry_date",
            action="correct",
            corrected_value="2020-01-01",
            source_page=0,
            today=TODAY,
        )

    assert snapshot(tmp_db_path, _LATEST_TABLES + _HISTORY_TABLES) == before
    assert table_count(tmp_db_path, "extraction_reviews") == 0


class _FakeLangfuseContext:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def update_current_trace(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_review_trace_metadata_allowlist(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.extraction import review

    init_db(tmp_db_path)
    seed_record(tmp_db_path)
    fake_context = _FakeLangfuseContext()
    monkeypatch.setattr(review, "_LANGFUSE_AVAILABLE", True)
    monkeypatch.setattr(review, "langfuse_context", fake_context)

    secret_value = "SECRET VENDOR CORRECTION"
    secret_note = "confidential reviewer note text"
    review.apply_field_review(
        tmp_db_path,
        doc_id="doc-001",
        field_name="vendor_name",
        action="correct",
        corrected_value=secret_value,
        source_page=0,
        note=secret_note,
        reviewer="alice-reviewer",
        today=TODAY,
    )
    with pytest.raises(review.ReviewInputError):
        review.apply_field_review(
            tmp_db_path,
            doc_id="doc-001",
            field_name="expiry_date",
            action="correct",
            corrected_value="not a date " + secret_value,
            source_page=0,
            note=secret_note,
            today=TODAY,
        )

    assert len(fake_context.calls) == 2
    allowed = {"boundary", "doc_id", "field_name", "action", "previous_review_state", "review_id", "error_class"}
    for call in fake_context.calls:
        assert set(call.get("metadata", {})) <= allowed
        assert "hitl" in call.get("tags", [])
        rendered = repr(call).lower()
        assert secret_value.lower() not in rendered
        assert secret_note.lower() not in rendered
        assert "alice-reviewer" not in rendered

    success, failure = fake_context.calls
    assert success["metadata"]["boundary"] == "hitl.review"
    assert success["metadata"]["action"] == "correct"
    assert isinstance(success["metadata"]["review_id"], int)
    assert failure["metadata"]["error_class"] == "invalid_date"
