"""Offline unit tests for extraction_eval_runner.run_extraction_eval."""

from __future__ import annotations

import sqlite3

import pytest

from src.db.schema import init_db
from src.eval.extraction_eval_runner import run_extraction_eval
from src.eval.repository import list_eval_metrics, list_eval_runs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(tmp_path):
    path = str(tmp_path / "db.sqlite")
    init_db(path)
    return path


def _insert_document(db_path: str, doc_id: str = "doc1") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO documents(doc_id, filename, file_path, page_count) VALUES (?,?,?,?)",
        (doc_id, f"{doc_id}.pdf", f"/data/{doc_id}.pdf", 1),
    )
    conn.commit()
    conn.close()


def _insert_extraction_run(db_path: str, run_id: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO extraction_runs(run_id, status, document_count, field_count) VALUES (?,?,?,?)",
        (run_id, "complete", 1, 1),
    )
    conn.commit()
    conn.close()


def _insert_history(db_path: str, run_id: str, doc_id: str, field_name: str, normalized_value: str | None, review_state: str = "extracted") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        INSERT OR IGNORE INTO extraction_history(run_id, doc_id, field_name, normalized_value, review_state)
        VALUES (?,?,?,?,?)
        """,
        (run_id, doc_id, field_name, normalized_value, review_state),
    )
    conn.commit()
    conn.close()


def _insert_gold(db_path: str, doc_id: str, field_name: str, expected_value: str, normalized_value: str | None = None) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        INSERT OR REPLACE INTO gold_extraction_labels(doc_id, field_name, expected_value, normalized_value)
        VALUES (?,?,?,?)
        """,
        (doc_id, field_name, expected_value, normalized_value),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_run_extraction_eval_produces_macro_and_field_metrics(tmp_path):
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "run1")
    _insert_history(db, "run1", "doc1", "vendor_name", "acme corp")
    _insert_gold(db, "doc1", "vendor_name", "Acme Corp", "acme corp")

    eval_run_id = run_extraction_eval(db, source_run_id="run1")

    metrics = list_eval_metrics(db, eval_run_id)
    metric_names = {m.metric_name for m in metrics}

    assert "extraction.macro.f1" in metric_names
    assert "extraction.macro.precision" in metric_names
    assert "extraction.macro.recall" in metric_names
    assert "extraction.f1" in metric_names

    macro_f1 = next(m for m in metrics if m.metric_name == "extraction.macro.f1")
    assert macro_f1.metric_value == pytest.approx(1.0)

    field_metric = next(
        m for m in metrics if m.metric_name == "extraction.f1" and m.scope_id == "vendor_name"
    )
    assert field_metric.scope_type == "field"
    assert field_metric.metric_value == pytest.approx(1.0)


def test_run_extraction_eval_with_no_gold_labels_completes_with_no_metrics(tmp_path):
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "run1")
    _insert_history(db, "run1", "doc1", "vendor_name", "acme corp")
    # No gold labels inserted

    eval_run_id = run_extraction_eval(db, source_run_id="run1")

    runs = list_eval_runs(db)
    run = next(r for r in runs if r.run_id == eval_run_id)
    assert run.status == "complete"

    metrics = list_eval_metrics(db, eval_run_id)
    assert metrics == []


def test_run_extraction_eval_with_no_predicted_rows_completes_with_no_metrics(tmp_path):
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "run1")
    _insert_gold(db, "doc1", "vendor_name", "Acme Corp", "acme corp")
    # No extraction_history rows for run1

    eval_run_id = run_extraction_eval(db, source_run_id="run1")

    runs = list_eval_runs(db)
    run = next(r for r in runs if r.run_id == eval_run_id)
    assert run.status == "complete"

    metrics = list_eval_metrics(db, eval_run_id)
    assert metrics == []


def test_run_extraction_eval_is_idempotent_on_repeated_calls(tmp_path):
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "run1")
    _insert_history(db, "run1", "doc1", "vendor_name", "acme corp")
    _insert_gold(db, "doc1", "vendor_name", "Acme Corp", "acme corp")

    fixed_eval_id = "fixed-eval-idempotent"
    id1 = run_extraction_eval(db, source_run_id="run1", eval_run_id=fixed_eval_id)
    id2 = run_extraction_eval(db, source_run_id="run1", eval_run_id=fixed_eval_id)

    assert id1 == id2 == fixed_eval_id

    # Metrics should not duplicate — upsert semantics
    metrics = list_eval_metrics(db, fixed_eval_id)
    macro_f1_rows = [m for m in metrics if m.metric_name == "extraction.macro.f1"]
    assert len(macro_f1_rows) == 1


def test_run_extraction_eval_marks_run_complete_on_success(tmp_path):
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "run1")
    _insert_history(db, "run1", "doc1", "vendor_name", "acme corp")
    _insert_gold(db, "doc1", "vendor_name", "Acme Corp", "acme corp")

    eval_run_id = run_extraction_eval(db, source_run_id="run1")

    runs = list_eval_runs(db)
    run = next(r for r in runs if r.run_id == eval_run_id)
    assert run.status == "complete"
    assert run.completed_at is not None


def test_run_extraction_eval_persists_per_field_scoped_metrics(tmp_path):
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "run1")
    # Two fields: vendor_name (correct), expiry_date (wrong)
    _insert_history(db, "run1", "doc1", "vendor_name", "acme corp")
    _insert_history(db, "run1", "doc1", "expiry_date", "2024-01-01")
    _insert_gold(db, "doc1", "vendor_name", "Acme Corp", "acme corp")
    _insert_gold(db, "doc1", "expiry_date", "2025-01-01", "2025-01-01")

    eval_run_id = run_extraction_eval(db, source_run_id="run1")

    metrics = list_eval_metrics(db, eval_run_id)

    vendor_f1 = next(
        (m for m in metrics if m.metric_name == "extraction.f1" and m.scope_id == "vendor_name"), None
    )
    expiry_f1 = next(
        (m for m in metrics if m.metric_name == "extraction.f1" and m.scope_id == "expiry_date"), None
    )

    assert vendor_f1 is not None
    assert vendor_f1.scope_type == "field"
    assert vendor_f1.metric_value == pytest.approx(1.0)

    assert expiry_f1 is not None
    assert expiry_f1.scope_type == "field"
    assert expiry_f1.metric_value == pytest.approx(0.0)  # wrong prediction -> FP+FN -> F1=0
