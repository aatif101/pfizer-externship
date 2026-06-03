from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from src.db.queries import insert_document
from src.db.schema import init_db
from src.eval.repository import (
    ExtractionUsageObservationRow,
    insert_extraction_usage_observation,
    list_extraction_usage_observations,
)


def _insert_usage_parent_rows(db_path: str, *, run_id: str = "extract-run-1", doc_id: str = "doc-a") -> None:
    insert_document(
        db_path,
        doc_id=doc_id,
        filename=f"{doc_id}.pdf",
        file_path=f"/tmp/{doc_id}.pdf",
        page_count=1,
        docling_json=None,
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO extraction_runs (run_id, status, document_count, field_count, trace_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, "running", 1, 0, f"trace-{run_id}"),
        )
        conn.commit()
    finally:
        conn.close()


def test_extraction_usage_observation_insert_and_filter_multiple_rows(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="run-1", doc_id="doc-a")
    _insert_usage_parent_rows(db_path, run_id="run-2", doc_id="doc-b")

    first_id = insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="run-1",
            doc_id="doc-a",
            stage="field_extraction",
            provider="gemini",
            model="gemini-2.5-flash",
            status="complete",
            latency_ms="125.5",
            input_tokens="100",
            output_tokens=25,
            total_tokens=125,
            estimated_cost_usd="0.000045",
            trace_id="trace-run-1",
            error_reason=None,
        ),
    )
    second_id = insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="run-1",
            doc_id="doc-a",
            stage="field_extraction",
            provider="gemini",
            model="gemini-2.5-flash",
            status="error",
            latency_ms=10,
            input_tokens=8,
            output_tokens=0,
            total_tokens=8,
            estimated_cost_usd=0.0,
            trace_id="trace-run-1b",
            error_reason="rate_limited",
        ),
    )
    third_id = insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="run-2",
            doc_id="doc-b",
            stage="compliance_scoring",
            provider="gemini",
            model="gemini-2.5-flash",
            status="complete",
            input_tokens=50,
            output_tokens=10,
            total_tokens=60,
            estimated_cost_usd=0.00002,
        ),
    )

    rows = list_extraction_usage_observations(db_path)
    assert [row.observation_id for row in rows] == [first_id, second_id, third_id]
    assert rows[0].run_id == "run-1"
    assert rows[0].doc_id == "doc-a"
    assert rows[0].stage == "field_extraction"
    assert rows[0].provider == "gemini"
    assert rows[0].model == "gemini-2.5-flash"
    assert rows[0].status == "complete"
    assert rows[0].latency_ms == 125.5
    assert rows[0].input_tokens == 100
    assert rows[0].output_tokens == 25
    assert rows[0].total_tokens == 125
    assert rows[0].estimated_cost_usd == 0.000045
    assert rows[0].trace_id == "trace-run-1"
    assert rows[0].error_reason is None
    assert rows[0].created_at is not None

    assert [row.observation_id for row in list_extraction_usage_observations(db_path, run_id="run-1")] == [
        first_id,
        second_id,
    ]
    assert [row.observation_id for row in list_extraction_usage_observations(db_path, doc_id="doc-b")] == [third_id]
    assert [row.observation_id for row in list_extraction_usage_observations(db_path, stage="field_extraction")] == [
        first_id,
        second_id,
    ]
    assert [row.observation_id for row in list_extraction_usage_observations(db_path, status="error")] == [
        second_id
    ]
    assert [row.observation_id for row in list_extraction_usage_observations(db_path, run_id="run-1", doc_id="doc-a", stage="field_extraction", status="complete")] == [
        first_id
    ]


def test_extraction_usage_observation_nullable_metrics_stay_null(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path)

    row_id = insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="extract-run-1",
            doc_id="doc-a",
            stage="field_extraction",
            status="skipped",
        ),
    )

    rows = list_extraction_usage_observations(db_path)
    assert len(rows) == 1
    assert rows[0].observation_id == row_id
    assert rows[0].latency_ms is None
    assert rows[0].input_tokens is None
    assert rows[0].output_tokens is None
    assert rows[0].total_tokens is None
    assert rows[0].estimated_cost_usd is None
    assert rows[0].provider is None
    assert rows[0].model is None
    assert rows[0].trace_id is None
    assert rows[0].error_reason is None


def test_extraction_usage_observation_default_limit_and_missing_filters(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path)

    for index in range(105):
        insert_extraction_usage_observation(
            db_path,
            ExtractionUsageObservationRow(
                run_id="extract-run-1",
                doc_id="doc-a",
                stage="field_extraction",
                status="complete",
                total_tokens=index,
            ),
        )

    default_rows = list_extraction_usage_observations(db_path)
    all_rows = list_extraction_usage_observations(db_path, limit=200)

    assert len(default_rows) == 100
    assert len(all_rows) == 105
    assert [row.observation_id for row in default_rows] == [row.observation_id for row in all_rows[:100]]
    assert list_extraction_usage_observations(db_path, run_id="missing") == []


def test_extraction_usage_observation_rejects_malformed_numeric_values_without_writing(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path)

    invalid_rows = [
        ExtractionUsageObservationRow(run_id="extract-run-1", doc_id="doc-a", latency_ms="slow"),
        ExtractionUsageObservationRow(run_id="extract-run-1", doc_id="doc-a", input_tokens=True),
        ExtractionUsageObservationRow(run_id="extract-run-1", doc_id="doc-a", output_tokens="many"),
        ExtractionUsageObservationRow(run_id="extract-run-1", doc_id="doc-a", total_tokens=False),
        ExtractionUsageObservationRow(run_id="extract-run-1", doc_id="doc-a", estimated_cost_usd=math.inf),
    ]

    for row in invalid_rows:
        with pytest.raises(ValueError):
            insert_extraction_usage_observation(db_path, row)

    assert list_extraction_usage_observations(db_path) == []


def test_extraction_usage_observation_fk_failure_rolls_back(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="run-ok", doc_id="doc-ok")

    with pytest.raises(sqlite3.IntegrityError):
        insert_extraction_usage_observation(
            db_path,
            ExtractionUsageObservationRow(
                run_id="missing-run",
                doc_id="doc-ok",
                stage="field_extraction",
                status="error",
                input_tokens=5,
            ),
        )

    assert list_extraction_usage_observations(db_path) == []


def test_extraction_usage_observation_limit_rejects_bool(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage.db")
    init_db(db_path)

    with pytest.raises(ValueError, match="limit"):
        list_extraction_usage_observations(db_path, limit=True)  # type: ignore[arg-type]
