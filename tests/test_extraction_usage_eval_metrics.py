from __future__ import annotations

import builtins
import importlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.db.queries import insert_document
from src.db.schema import init_db
from src.eval import extraction_usage_eval as runner
from src.eval.operational_metrics import (
    EXTRACTION_COST_AVG_USD,
    EXTRACTION_COST_TOTAL_USD,
    EXTRACTION_INPUT_TOKENS_TOTAL,
    EXTRACTION_LATENCY_AVG_MS,
    EXTRACTION_LATENCY_P50_MS,
    EXTRACTION_LATENCY_P95_MS,
    EXTRACTION_OUTPUT_TOKENS_TOTAL,
    EXTRACTION_TOTAL_TOKENS_TOTAL,
    aggregate_extraction_usage_metrics,
)
from src.eval.repository import (
    ExtractionUsageObservationRow,
    insert_extraction_usage_observation,
    list_eval_metrics,
    list_eval_runs,
)
from src.eval.extraction_usage_eval import run_extraction_usage_eval
from src.tracing import filter_trace_metadata


def _capture_safe_trace_updates(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []

    def fake_safe_update_current_trace(**kwargs: Any) -> bool:
        updates.append(
            filter_trace_metadata(kwargs.get("metadata"), kwargs.get("allowed_metadata_keys") or frozenset())
        )
        return True

    monkeypatch.setattr(runner, "safe_update_current_trace", fake_safe_update_current_trace)
    return updates


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
            (run_id, "complete", 1, 0, f"trace-{run_id}"),
        )
        conn.commit()
    finally:
        conn.close()


def test_extraction_usage_metrics_compute_percentiles_cost_and_token_totals() -> None:
    rows = [
        {"latency_ms": 400.0, "estimated_cost_usd": 0.4, "input_tokens": 40, "output_tokens": 4, "total_tokens": 44},
        {"latency_ms": 100.0, "estimated_cost_usd": 0.1, "input_tokens": 10, "output_tokens": 1, "total_tokens": 11},
        {"latency_ms": 300.0, "estimated_cost_usd": 0.3, "input_tokens": 30, "output_tokens": 3, "total_tokens": 33},
        {"latency_ms": 200.0, "estimated_cost_usd": 0.2, "input_tokens": 20, "output_tokens": 2, "total_tokens": 22},
    ]

    metrics = aggregate_extraction_usage_metrics(rows)

    assert metrics[EXTRACTION_LATENCY_AVG_MS] == 250.0
    assert metrics[EXTRACTION_LATENCY_P50_MS] == 250.0
    assert metrics[EXTRACTION_LATENCY_P95_MS] == pytest.approx(385.0)
    assert metrics[EXTRACTION_COST_TOTAL_USD] == pytest.approx(1.0)
    assert metrics[EXTRACTION_COST_AVG_USD] == pytest.approx(0.25)
    assert metrics[EXTRACTION_INPUT_TOKENS_TOTAL] == 100.0
    assert metrics[EXTRACTION_OUTPUT_TOKENS_TOTAL] == 10.0
    assert metrics[EXTRACTION_TOTAL_TOKENS_TOTAL] == 110.0


def test_extraction_usage_metrics_empty_null_and_missing_values_emit_no_metrics() -> None:
    assert aggregate_extraction_usage_metrics([]) == {}
    assert aggregate_extraction_usage_metrics(
        [
            {},
            ExtractionUsageObservationRow(run_id="run-a", doc_id="doc-a", status="skipped"),
            {
                "latency_ms": None,
                "estimated_cost_usd": None,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            },
        ]
    ) == {}


def test_extraction_usage_eval_persists_global_metrics_for_selected_source_run(tmp_path: Path, monkeypatch):
    trace_updates = _capture_safe_trace_updates(monkeypatch)
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-run", doc_id="doc-a")
    _insert_usage_parent_rows(db_path, run_id="unrelated-run", doc_id="doc-b")

    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc-a",
            stage="text_extraction",
            provider="gemini",
            model="gemini-2.5-flash",
            status="complete",
            latency_ms=100.0,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd=0.25,
        ),
    )
    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc-a",
            stage="text_extraction",
            provider="gemini",
            model="gemini-2.5-flash",
            status="complete",
            latency_ms=300.0,
            input_tokens=20,
            output_tokens=15,
            total_tokens=35,
            estimated_cost_usd=0.75,
        ),
    )
    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="unrelated-run",
            doc_id="doc-b",
            stage="text_extraction",
            provider="gemini",
            model="gemini-2.5-flash",
            status="complete",
            latency_ms=999.0,
            input_tokens=999,
            output_tokens=999,
            total_tokens=1998,
            estimated_cost_usd=999.0,
        ),
    )

    eval_run_id = run_extraction_usage_eval(db_path, source_run_id="source-run", eval_run_id="usage-eval-run")

    assert eval_run_id == "usage-eval-run"
    runs = list_eval_runs(db_path)
    row = next(r for r in runs if r.run_id == eval_run_id)
    assert row.status == "complete"
    metric_index = {(m.metric_name, m.scope_type, m.scope_id): m.metric_value for m in list_eval_metrics(db_path, eval_run_id)}

    assert metric_index[(EXTRACTION_LATENCY_AVG_MS, None, None)] == 200.0
    assert metric_index[(EXTRACTION_LATENCY_P50_MS, None, None)] == 200.0
    assert metric_index[(EXTRACTION_LATENCY_P95_MS, None, None)] == pytest.approx(290.0)
    assert metric_index[(EXTRACTION_COST_TOTAL_USD, None, None)] == 1.0
    assert metric_index[(EXTRACTION_COST_AVG_USD, None, None)] == 0.5
    assert metric_index[(EXTRACTION_INPUT_TOKENS_TOTAL, None, None)] == 30.0
    assert metric_index[(EXTRACTION_OUTPUT_TOKENS_TOTAL, None, None)] == 20.0
    assert metric_index[(EXTRACTION_TOTAL_TOKENS_TOTAL, None, None)] == 50.0

    final_trace_metadata = trace_updates[-1]
    assert final_trace_metadata["status"] == "complete"
    assert final_trace_metadata["boundary"] == "evaluation"
    assert final_trace_metadata["eval_type"] == "extraction_usage_eval"
    assert final_trace_metadata["run_id"] == eval_run_id
    assert final_trace_metadata["source_run_id"] == "source-run"
    assert final_trace_metadata["observation_count"] == 2
    assert final_trace_metadata["metric_count"] == 8
    assert set(final_trace_metadata).issubset(runner._EXTRACTION_USAGE_TRACE_ALLOWED_KEYS)
    assert "gemini" not in repr(trace_updates).lower()


def test_extraction_usage_eval_empty_observations_complete_without_metrics(tmp_path: Path):
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-run", doc_id="doc-a")

    eval_run_id = run_extraction_usage_eval(db_path, source_run_id="source-run", eval_run_id="empty-usage-eval")

    row = next(r for r in list_eval_runs(db_path) if r.run_id == eval_run_id)
    assert row.status == "complete"
    assert list_eval_metrics(db_path, eval_run_id) == []


def test_extraction_usage_eval_null_fields_emit_no_zero_metrics(tmp_path: Path):
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-run", doc_id="doc-a")

    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(run_id="source-run", doc_id="doc-a", stage="text_extraction", status="skipped"),
    )

    eval_run_id = run_extraction_usage_eval(db_path, source_run_id="source-run", eval_run_id="null-usage-eval")

    assert list_eval_metrics(db_path, eval_run_id) == []


def test_extraction_usage_eval_missing_observation_table_is_optional_noop(tmp_path: Path):
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-run", doc_id="doc-a")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE extraction_usage_observations")
        conn.commit()
    finally:
        conn.close()

    eval_run_id = run_extraction_usage_eval(db_path, source_run_id="source-run", eval_run_id="missing-table-eval")

    row = next(r for r in list_eval_runs(db_path) if r.run_id == eval_run_id)
    assert row.status == "complete"
    assert list_eval_metrics(db_path, eval_run_id) == []


def test_extraction_usage_eval_malformed_numeric_marks_sanitized_error(tmp_path: Path, monkeypatch):
    trace_updates = _capture_safe_trace_updates(monkeypatch)
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-run", doc_id="doc-a")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO extraction_usage_observations (run_id, doc_id, stage, status, latency_ms)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("source-run", "doc-a", "text_extraction", "complete", "slow <raw prompt should not leak>"),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="latency_ms"):
        run_extraction_usage_eval(db_path, source_run_id="source-run", eval_run_id="malformed-usage-eval")

    row = next(r for r in list_eval_runs(db_path) if r.run_id == "malformed-usage-eval")
    assert row.status == "error"
    assert row.error_reason is not None
    assert "ValueError: latency_ms must be numeric or None" in row.error_reason
    assert "<" not in row.error_reason
    assert "raw prompt" not in row.error_reason

    error_trace_metadata = trace_updates[-1]
    assert error_trace_metadata["status"] == "error"
    assert error_trace_metadata["error_class"] == "ValueError"
    assert error_trace_metadata["source_run_id"] == "source-run"
    error_metadata_repr = repr(error_trace_metadata).lower()
    assert "slow" not in error_metadata_repr
    assert "raw prompt" not in error_metadata_repr
    assert "secret" not in error_metadata_repr


def test_extraction_usage_eval_import_is_provider_free(monkeypatch: pytest.MonkeyPatch):
    original_import = builtins.__import__
    blocked_prefixes = ("google", "google_genai", "anthropic", "ragas", "streamlit")

    def fail_on_provider_import(name, *args, **kwargs):
        if name == blocked_prefixes or name.startswith(tuple(f"{prefix}." for prefix in blocked_prefixes)):
            raise AssertionError(f"provider-free helper imported optional dependency: {name}")
        if name in blocked_prefixes:
            raise AssertionError(f"provider-free helper imported optional dependency: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_provider_import)
    importlib.reload(runner)
