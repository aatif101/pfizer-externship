from __future__ import annotations

import builtins
import importlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.db.queries import insert_document
from src.db.schema import init_db
from src.eval import extraction_usage_eval as runner
from src.eval.operational_metrics import (
    EXTRACTION_COST_AVG_USD,
    EXTRACTION_COST_COVERAGE,
    EXTRACTION_COST_TOTAL_USD,
    EXTRACTION_CANDIDATE_TOKENS_TOTAL,
    EXTRACTION_INPUT_TOKENS_TOTAL,
    EXTRACTION_LATENCY_AVG_MS,
    EXTRACTION_LATENCY_P50_MS,
    EXTRACTION_LATENCY_P95_MS,
    EXTRACTION_OUTPUT_TOKENS_TOTAL,
    EXTRACTION_THOUGHT_TOKENS_TOTAL,
    EXTRACTION_TOTAL_TOKENS_TOTAL,
    aggregate_extraction_usage_metrics,
)
from src.eval.repository import (
    ExtractionUsageObservationRow,
    insert_extraction_usage_observation,
    list_eval_metrics,
    list_eval_runs,
)
from src.eval.extraction_eval_runner import SourceExtractionRunIncompleteError
from src.eval.extraction_usage_eval import ExtractionUsageEvalError, run_extraction_usage_eval
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


def _insert_usage_parent_rows(
    db_path: str,
    *,
    run_id: str = "extract-run-1",
    doc_id: str = "doc-a",
    status: str = "completed",
    expected: int = 1,
    succeeded: int = 1,
    failed: int = 0,
    requested_model: str = "gemini-2.5-flash",
    resolved_model: str = "gemini-2.5-flash-2026-06-17",
) -> None:
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
            INSERT INTO extraction_runs (
                run_id, status, document_count, field_count, trace_id,
                expected_document_count, attempted_document_count,
                succeeded_document_count, failed_document_count,
                provider, requested_model, resolved_model, corpus_version,
                manifest_hash, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                status,
                succeeded,
                succeeded * 6,
                f"trace-{run_id}",
                expected,
                succeeded + failed,
                succeeded,
                failed,
                "gemini",
                requested_model,
                resolved_model,
                "sdf-synthetic-v1",
                "a" * 64,
                "2026-07-15T10:00:00Z",
                "2026-07-15T10:05:00Z" if status == "completed" else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_extraction_usage_metrics_compute_percentiles_cost_and_token_totals() -> None:
    rows = [
        {
            "latency_ms": 400.0,
            "estimated_cost_usd": 0.4,
            "input_tokens": 40,
            "output_tokens": 4,
            "thought_tokens": 2,
            "total_tokens": 46,
        },
        {
            "latency_ms": 100.0,
            "estimated_cost_usd": 0.1,
            "input_tokens": 10,
            "output_tokens": 1,
            "thought_tokens": 1,
            "total_tokens": 12,
        },
        {
            "latency_ms": 300.0,
            "estimated_cost_usd": 0.3,
            "input_tokens": 30,
            "output_tokens": 3,
            "thought_tokens": 3,
            "total_tokens": 36,
        },
        {
            "latency_ms": 200.0,
            "estimated_cost_usd": 0.2,
            "input_tokens": 20,
            "output_tokens": 2,
            "thought_tokens": 2,
            "total_tokens": 24,
        },
    ]

    metrics = aggregate_extraction_usage_metrics(rows)

    assert metrics[EXTRACTION_LATENCY_AVG_MS] == 250.0
    assert metrics[EXTRACTION_LATENCY_P50_MS] == 250.0
    assert metrics[EXTRACTION_LATENCY_P95_MS] == pytest.approx(385.0)
    assert metrics[EXTRACTION_COST_TOTAL_USD] == pytest.approx(1.0)
    assert metrics[EXTRACTION_COST_AVG_USD] == pytest.approx(0.25)
    assert metrics[EXTRACTION_INPUT_TOKENS_TOTAL] == 100.0
    assert metrics[EXTRACTION_OUTPUT_TOKENS_TOTAL] == 10.0
    assert metrics[EXTRACTION_CANDIDATE_TOKENS_TOTAL] == 10.0
    assert metrics[EXTRACTION_THOUGHT_TOKENS_TOTAL] == 8.0
    assert metrics[EXTRACTION_TOTAL_TOKENS_TOTAL] == 118.0


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
                "thought_tokens": None,
                "total_tokens": None,
            },
        ]
    ) == {}

    with pytest.raises(ValueError, match="thought_tokens must be nonnegative"):
        aggregate_extraction_usage_metrics([{"thought_tokens": -1}])


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
            thought_tokens=2,
            total_tokens=17,
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
            thought_tokens=5,
            total_tokens=40,
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
            thought_tokens=999,
            total_tokens=2997,
            estimated_cost_usd=999.0,
        ),
    )

    eval_run_id = run_extraction_usage_eval(db_path, source_run_id="source-run", eval_run_id="usage-eval-run")

    assert eval_run_id == "usage-eval-run"
    runs = list_eval_runs(db_path)
    row = next(r for r in runs if r.run_id == eval_run_id)
    assert row.status == "complete"
    metric_index = {
        (metric.metric_name, metric.scope_type, metric.scope_id): metric.metric_value
        for metric in list_eval_metrics(db_path, eval_run_id)
    }

    assert metric_index[(EXTRACTION_LATENCY_AVG_MS, None, None)] == 400.0
    assert metric_index[(EXTRACTION_LATENCY_P50_MS, None, None)] == 400.0
    assert metric_index[(EXTRACTION_LATENCY_P95_MS, None, None)] == 400.0
    assert metric_index[(EXTRACTION_COST_TOTAL_USD, None, None)] == 1.0
    assert metric_index[(EXTRACTION_COST_AVG_USD, None, None)] == 1.0
    assert metric_index[(EXTRACTION_COST_COVERAGE, None, None)] == 1.0
    assert metric_index[(EXTRACTION_INPUT_TOKENS_TOTAL, None, None)] == 30.0
    assert metric_index[(EXTRACTION_OUTPUT_TOKENS_TOTAL, None, None)] == 20.0
    assert metric_index[(EXTRACTION_CANDIDATE_TOKENS_TOTAL, None, None)] == 20.0
    assert metric_index[(EXTRACTION_THOUGHT_TOKENS_TOTAL, None, None)] == 7.0
    assert metric_index[(EXTRACTION_TOTAL_TOKENS_TOTAL, None, None)] == 57.0

    final_trace_metadata = trace_updates[-1]
    assert final_trace_metadata["status"] == "complete"
    assert final_trace_metadata["boundary"] == "evaluation"
    assert final_trace_metadata["eval_type"] == "extraction_usage_eval"
    assert final_trace_metadata["run_id"] == eval_run_id
    assert final_trace_metadata["source_run_id"] == "source-run"
    assert final_trace_metadata["observation_count"] == 2
    assert final_trace_metadata["metric_count"] == 11
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


def test_extraction_usage_metrics_unknown_billable_cost_omits_cost_totals() -> None:
    metrics = aggregate_extraction_usage_metrics(
        [
            {
                "input_tokens": 10,
                "output_tokens": 3,
                "thought_tokens": 2,
                "total_tokens": 15,
                "estimated_cost_usd": 0.01,
            },
            {
                "input_tokens": 20,
                "output_tokens": 5,
                "thought_tokens": 4,
                "total_tokens": 29,
                "estimated_cost_usd": None,
            },
            {
                "input_tokens": None,
                "output_tokens": None,
                "thought_tokens": None,
                "total_tokens": None,
                "estimated_cost_usd": None,
            },
        ]
    )

    assert EXTRACTION_COST_TOTAL_USD not in metrics
    assert EXTRACTION_COST_AVG_USD not in metrics
    assert metrics[EXTRACTION_COST_COVERAGE] == 0.5
    assert metrics[EXTRACTION_INPUT_TOKENS_TOTAL] == 30.0
    assert metrics[EXTRACTION_CANDIDATE_TOKENS_TOTAL] == 8.0
    assert metrics[EXTRACTION_THOUGHT_TOKENS_TOTAL] == 6.0
    assert metrics[EXTRACTION_TOTAL_TOKENS_TOTAL] == 44.0


def test_successful_provider_row_without_usage_metadata_suppresses_cost_claims() -> None:
    metrics = aggregate_extraction_usage_metrics(
        [
            {
                "doc_id": "doc-a",
                "status": "complete",
                "provider": "gemini",
                "estimated_cost_usd": 0.01,
            },
            {
                "doc_id": "doc-b",
                "status": "complete",
                "provider": "gemini",
                "estimated_cost_usd": None,
            },
            {
                "doc_id": "doc-b",
                "status": "skipped",
                "estimated_cost_usd": None,
            },
        ]
    )

    assert EXTRACTION_COST_TOTAL_USD not in metrics
    assert EXTRACTION_COST_AVG_USD not in metrics
    assert metrics[EXTRACTION_COST_COVERAGE] == 0.5


def test_fractional_token_counters_fail_closed_during_aggregation() -> None:
    with pytest.raises(ValueError, match="thought_tokens must be an integer"):
        aggregate_extraction_usage_metrics([{"thought_tokens": 1.5}])


def test_extraction_usage_eval_rerun_clears_stale_cost_when_pricing_becomes_unknown(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-run", doc_id="doc-a")
    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc-a",
            input_tokens=10,
            output_tokens=2,
            thought_tokens=1,
            total_tokens=13,
            estimated_cost_usd=0.01,
        ),
    )

    run_extraction_usage_eval(
        db_path,
        source_run_id="source-run",
        eval_run_id="reused-usage-eval",
    )
    first_metric_names = {
        metric.metric_name for metric in list_eval_metrics(db_path, "reused-usage-eval")
    }
    assert EXTRACTION_COST_TOTAL_USD in first_metric_names

    insert_extraction_usage_observation(
        db_path,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc-a",
            requested_model="gemini-future-alias",
            input_tokens=10,
            output_tokens=2,
            thought_tokens=1,
            total_tokens=13,
            estimated_cost_usd=None,
        ),
    )
    run_extraction_usage_eval(
        db_path,
        source_run_id="source-run",
        eval_run_id="reused-usage-eval",
    )

    rerun_metric_names = {
        metric.metric_name for metric in list_eval_metrics(db_path, "reused-usage-eval")
    }
    assert EXTRACTION_COST_TOTAL_USD not in rerun_metric_names
    assert EXTRACTION_COST_AVG_USD not in rerun_metric_names


def test_extraction_usage_eval_refuses_running_source_and_writes_no_metrics(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(
        db_path,
        run_id="running-source",
        doc_id="doc-a",
        status="running",
        expected=1,
        succeeded=0,
    )

    with pytest.raises(SourceExtractionRunIncompleteError):
        run_extraction_usage_eval(
            db_path,
            source_run_id="running-source",
            eval_run_id="running-source-eval",
        )

    row = next(item for item in list_eval_runs(db_path) if item.run_id == "running-source-eval")
    assert row.status == "error"
    assert row.error_reason == "source_extraction_run_incomplete"
    assert list_eval_metrics(db_path, "running-source-eval") == []


def test_extraction_usage_eval_reuse_replaces_source_provenance_and_metrics(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-a", doc_id="doc-a")
    _insert_usage_parent_rows(db_path, run_id="source-b", doc_id="doc-b")
    for source_run_id, doc_id, token_count in (("source-a", "doc-a", 10), ("source-b", "doc-b", 30)):
        insert_extraction_usage_observation(
            db_path,
            ExtractionUsageObservationRow(
                run_id=source_run_id,
                doc_id=doc_id,
                stage="text_extraction",
                provider="gemini",
                status="complete",
                input_tokens=token_count,
                estimated_cost_usd=0.01,
            ),
        )

    run_extraction_usage_eval(db_path, source_run_id="source-a", eval_run_id="reused-source-eval")
    run_extraction_usage_eval(db_path, source_run_id="source-b", eval_run_id="reused-source-eval")

    row = next(item for item in list_eval_runs(db_path) if item.run_id == "reused-source-eval")
    assert json.loads(row.params_json or "{}") == {
        "max_observations": 10_000,
        "source_run_id": "source-b",
    }
    metrics = {metric.metric_name: metric.metric_value for metric in list_eval_metrics(db_path, "reused-source-eval")}
    assert metrics[EXTRACTION_INPUT_TOKENS_TOTAL] == 30.0


def test_extraction_usage_eval_refuses_truncated_totals(tmp_path: Path) -> None:
    db_path = str(tmp_path / "usage-eval.db")
    init_db(db_path)
    _insert_usage_parent_rows(db_path, run_id="source-run", doc_id="doc-a")
    for stage in ("text_extraction", "visual_fallback"):
        insert_extraction_usage_observation(
            db_path,
            ExtractionUsageObservationRow(
                run_id="source-run",
                doc_id="doc-a",
                stage=stage,
                provider="gemini",
                status="complete",
                input_tokens=10,
                estimated_cost_usd=0.01,
            ),
        )

    with pytest.raises(ExtractionUsageEvalError):
        run_extraction_usage_eval(
            db_path,
            source_run_id="source-run",
            eval_run_id="truncated-usage-eval",
            max_observations=1,
        )

    row = next(item for item in list_eval_runs(db_path) if item.run_id == "truncated-usage-eval")
    assert row.status == "error"
    assert row.error_reason == "extraction_usage_eval_error"
    assert list_eval_metrics(db_path, "truncated-usage-eval") == []


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

    with pytest.raises(ExtractionUsageEvalError, match="^extraction_usage_eval_error$") as error:
        run_extraction_usage_eval(db_path, source_run_id="source-run", eval_run_id="malformed-usage-eval")

    row = next(r for r in list_eval_runs(db_path) if r.run_id == "malformed-usage-eval")
    assert row.status == "error"
    assert row.error_reason == "extraction_usage_eval_error"

    error_trace_metadata = trace_updates[-1]
    assert error_trace_metadata["status"] == "error"
    assert error_trace_metadata["error_class"] == "ValueError"
    assert error_trace_metadata["reason_code"] == "extraction_usage_eval_error"
    assert error_trace_metadata["source_run_id"] == "source-run"
    error_metadata_repr = repr(error_trace_metadata).lower()
    assert "slow" not in error_metadata_repr
    assert "raw prompt" not in error_metadata_repr
    assert "secret" not in error_metadata_repr
    assert "raw prompt" not in str(error.value).lower()


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
