from __future__ import annotations

from src.db.schema import init_db
from src.eval.extraction_metrics import (
    compute_extraction_field_scores,
    compute_macro_averages,
    normalize_extracted_value,
)
from src.eval.repository import list_predicted_extractions


def test_normalize_extracted_value_whitespace_and_casefold() -> None:
    assert normalize_extracted_value("vendor_name", None) is None
    assert normalize_extracted_value("vendor_name", "   ") is None
    assert normalize_extracted_value("vendor_name", "  Pfizer   Inc  ") == "pfizer inc"


def test_normalize_extracted_value_dates_best_effort() -> None:
    # Parses common ISO formats.
    assert normalize_extracted_value("expiry_date", "2024-01-05") == "2024-01-05"
    # Falls back deterministically when parse fails (still cleaned + casefolded).
    assert normalize_extracted_value("expiry_date", "not a date") == "not a date"


def test_compute_extraction_field_scores_counts_tp_fp_fn() -> None:
    gold_rows = [
        {"doc_id": "d1", "field_name": "vendor_name", "expected_value": "Acme"},
        {"doc_id": "d1", "field_name": "expiry_date", "expected_value": "2024-01-05"},
        {"doc_id": "d2", "field_name": "vendor_name", "expected_value": "ACME"},
    ]

    pred_rows = [
        {"doc_id": "d1", "field_name": "vendor_name", "normalized_value": "acme", "review_state": "accepted"},
        # Wrong date -> FP + FN for expiry_date
        {
            "doc_id": "d1",
            "field_name": "expiry_date",
            "normalized_value": "2024-01-06",
            "review_state": "accepted",
        },
        # Abstained => FN for vendor_name on d2
        {"doc_id": "d2", "field_name": "vendor_name", "normalized_value": None, "review_state": "abstained"},
    ]

    scores = compute_extraction_field_scores(gold_rows, pred_rows)

    vendor = scores["vendor_name"]
    assert vendor.tp == 1
    assert vendor.fp == 0
    assert vendor.fn == 1

    expiry = scores["expiry_date"]
    assert expiry.tp == 0
    assert expiry.fp == 1
    assert expiry.fn == 1


def test_compute_macro_averages_empty_and_nonempty() -> None:
    assert compute_macro_averages({"x": type("S", (), {"precision": 1.0, "recall": 0.0, "f1": 0.0})()}) == {
        "precision": 1.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    assert compute_macro_averages({}) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_list_predicted_extractions_reads_sqlite(tmp_path) -> None:
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    # Minimal rows to satisfy FKs.
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO documents(doc_id, filename, file_path, page_count) VALUES (?,?,?,?)",
            ("d1", "f.pdf", "f.pdf", 1),
        )
        conn.execute(
            "INSERT INTO extractions(doc_id, field_name, normalized_value, review_state) VALUES (?,?,?,?)",
            ("d1", "vendor_name", "acme", "accepted"),
        )
        conn.commit()
    finally:
        conn.close()

    rows = list_predicted_extractions(db_path)
    assert rows == [
        {"doc_id": "d1", "field_name": "vendor_name", "normalized_value": "acme", "review_state": "accepted"}
    ]
