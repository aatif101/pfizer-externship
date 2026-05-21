from __future__ import annotations

import sqlite3

from src.db.schema import init_db
from src.eval.extraction_metrics import (
    FieldScore,
    compute_extraction_field_scores,
    compute_macro_averages,
    normalize_extracted_value,
)
from src.eval.repository import (
    create_eval_run,
    list_eval_metrics,
    list_predicted_extractions,
    upsert_eval_metric,
)


def test_normalize_extracted_value_whitespace_and_casefold() -> None:
    assert normalize_extracted_value("vendor_name", None) is None
    assert normalize_extracted_value("vendor_name", "   ") is None
    assert normalize_extracted_value("vendor_name", "  Pfizer   Inc  ") == "pfizer inc"


def test_normalize_extracted_value_dates_best_effort() -> None:
    # Parses common ISO formats.
    assert normalize_extracted_value("expiry_date", "2024-01-05") == "2024-01-05"
    # Parses non-ISO formats with dateutil.
    assert normalize_extracted_value("expiry_date", "01-JAN-2024") == "2024-01-01"
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
    assert compute_macro_averages({"x": FieldScore(tp=0, fp=0, fn=0, precision=1.0, recall=0.0, f1=0.0)}) == {
        "precision": 1.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    assert compute_macro_averages({}) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_list_predicted_extractions_reads_sqlite(tmp_path) -> None:
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

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


def test_extraction_eval_persistence_integration_and_deduping(tmp_path) -> None:
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        # Minimal rows to satisfy FKs.
        conn.execute(
            "INSERT INTO documents(doc_id, filename, file_path, page_count) VALUES (?,?,?,?)",
            ("d1", "f.pdf", "f.pdf", 1),
        )
        conn.execute(
            "INSERT INTO documents(doc_id, filename, file_path, page_count) VALUES (?,?,?,?)",
            ("d2", "g.pdf", "g.pdf", 1),
        )

        # Gold labels.
        conn.execute(
            "INSERT INTO gold_extraction_labels(doc_id, field_name, expected_value) VALUES (?,?,?)",
            ("d1", "vendor_name", "Acme"),
        )
        conn.execute(
            "INSERT INTO gold_extraction_labels(doc_id, field_name, expected_value) VALUES (?,?,?)",
            ("d1", "expiry_date", "2024-01-05"),
        )
        conn.execute(
            "INSERT INTO gold_extraction_labels(doc_id, field_name, expected_value) VALUES (?,?,?)",
            ("d2", "vendor_name", "ACME"),
        )

        # Predicted extractions.
        conn.execute(
            "INSERT INTO extractions(doc_id, field_name, normalized_value, review_state) VALUES (?,?,?,?)",
            ("d1", "vendor_name", "acme", "accepted"),
        )
        conn.execute(
            "INSERT INTO extractions(doc_id, field_name, normalized_value, review_state) VALUES (?,?,?,?)",
            ("d1", "expiry_date", "2024-01-06", "accepted"),
        )
        # d2 abstains on vendor_name => FN.
        conn.execute(
            "INSERT INTO extractions(doc_id, field_name, normalized_value, review_state) VALUES (?,?,?,?)",
            ("d2", "vendor_name", None, "abstained"),
        )
        conn.commit()
    finally:
        conn.close()

    run_id = "run-1"
    create_eval_run(db_path, run_id=run_id, eval_type="extraction", pipeline_label="unit-test", params=None)

    # Compute scores from DB rows.
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        gold_rows = [dict(r) for r in conn.execute("SELECT doc_id, field_name, expected_value FROM gold_extraction_labels")]
        pred_rows = [dict(r) for r in conn.execute("SELECT doc_id, field_name, normalized_value, review_state FROM extractions")]
    finally:
        conn.close()

    per_field = compute_extraction_field_scores(gold_rows, pred_rows)
    macro = compute_macro_averages(per_field)

    # Upsert per-field metrics and macro averages.
    for field_name, score in per_field.items():
        upsert_eval_metric(db_path, run_id, "precision", score.precision, scope_type="field", scope_id=field_name)
        upsert_eval_metric(db_path, run_id, "recall", score.recall, scope_type="field", scope_id=field_name)
        upsert_eval_metric(db_path, run_id, "f1", score.f1, scope_type="field", scope_id=field_name)
        upsert_eval_metric(db_path, run_id, "tp", float(score.tp), scope_type="field", scope_id=field_name)
        upsert_eval_metric(db_path, run_id, "fp", float(score.fp), scope_type="field", scope_id=field_name)
        upsert_eval_metric(db_path, run_id, "fn", float(score.fn), scope_type="field", scope_id=field_name)

    upsert_eval_metric(db_path, run_id, "precision", macro["precision"])
    upsert_eval_metric(db_path, run_id, "recall", macro["recall"])
    upsert_eval_metric(db_path, run_id, "f1", macro["f1"])

    # Re-upsert the same keys with a sentinel update to prove deduping/overwrite.
    upsert_eval_metric(db_path, run_id, "precision", macro["precision"])

    metrics = list_eval_metrics(db_path, run_id)

    # Assert there is exactly one unscoped 'precision' row and it has expected value.
    global_precision = [m for m in metrics if m.metric_name == "precision" and m.scope_type is None and m.scope_id is None]
    assert len(global_precision) == 1
    assert global_precision[0].metric_value == macro["precision"]

    # Spot-check a field-scoped metric row exists.
    vendor_f1 = [
        m
        for m in metrics
        if m.metric_name == "f1" and m.scope_type == "field" and m.scope_id == "vendor_name"
    ]
    assert len(vendor_f1) == 1
    assert vendor_f1[0].metric_value == per_field["vendor_name"].f1
