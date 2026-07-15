"""Offline unit tests for extraction_eval_runner.run_extraction_eval."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from src.db.schema import init_db
from src.eval import extraction_eval_runner as runner
from src.eval.extraction_eval_runner import (
    ExtractionEvalError,
    SourceExtractionRunIncompleteError,
    run_extraction_eval,
)
from src.eval.repository import (
    ExtractionUsageObservationRow,
    create_eval_run,
    insert_extraction_usage_observation,
    list_eval_metrics,
    list_eval_runs,
    upsert_eval_metric,
)
from src.tracing import filter_trace_metadata


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


def _insert_extraction_run(
    db_path: str,
    run_id: str,
    *,
    status: str = "completed",
    expected: int = 1,
    attempted: int = 1,
    succeeded: int = 1,
    failed: int = 0,
    requested_model: str = "gemini-2.5-flash",
    resolved_model: str | None = "gemini-2.5-flash-2026-06-17",
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        INSERT OR REPLACE INTO extraction_runs (
            run_id, status, document_count, field_count,
            expected_document_count, attempted_document_count,
            succeeded_document_count, failed_document_count,
            provider, requested_model, resolved_model, corpus_version,
            manifest_hash, started_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            status,
            succeeded,
            succeeded * 6,
            expected,
            attempted,
            succeeded,
            failed,
            "gemini",
            requested_model,
            resolved_model,
            "sdf-synthetic-v1",
            "a" * 64,
            "2026-07-15T10:00:00Z",
            None if status == "running" else "2026-07-15T10:05:00Z",
        ),
    )
    conn.commit()
    conn.close()


def _insert_history(
    db_path: str,
    run_id: str,
    doc_id: str,
    field_name: str,
    normalized_value: str | None,
    review_state: str = "extracted",
) -> None:
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


def _insert_gold(
    db_path: str,
    doc_id: str,
    field_name: str,
    expected_value: str,
    normalized_value: str | None = None,
) -> None:
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


def _capture_safe_trace_updates(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []

    def fake_safe_update_current_trace(**kwargs: Any) -> bool:
        updates.append(
            filter_trace_metadata(
                kwargs.get("metadata"),
                kwargs.get("allowed_metadata_keys") or frozenset(),
            )
        )
        return True

    monkeypatch.setattr(runner, "safe_update_current_trace", fake_safe_update_current_trace)
    return updates


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


@pytest.mark.parametrize(
    ("status", "expected", "succeeded", "failed"),
    [
        (None, 0, 0, 0),
        ("running", 1, 0, 0),
        ("partial", 2, 1, 1),
        ("failed", 1, 0, 1),
        ("completed", 0, 0, 0),
        ("completed", 2, 1, 0),
        ("completed", 1, 1, 1),
    ],
)
def test_run_extraction_eval_refuses_every_incomplete_source_before_loading_predictions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    status: str | None,
    expected: int,
    succeeded: int,
    failed: int,
) -> None:
    db = _db(tmp_path)
    if status is not None:
        _insert_extraction_run(
            db,
            "source-run",
            status=status,
            expected=expected,
            attempted=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
        )

    loader_calls: list[str] = []

    def fail_gold_loader(_db_path: str) -> list[dict]:
        loader_calls.append("gold")
        return []

    def fail_prediction_loader(_db_path: str, _source_run_id: str) -> list[dict]:
        loader_calls.append("predictions")
        return []

    monkeypatch.setattr(runner, "_load_optional_gold_labels", fail_gold_loader)
    monkeypatch.setattr(runner, "_load_optional_predicted_extractions", fail_prediction_loader)

    with pytest.raises(
        SourceExtractionRunIncompleteError,
        match="^source_extraction_run_incomplete$",
    ):
        run_extraction_eval(
            db,
            source_run_id="source-run",
            eval_run_id="refused-eval",
        )

    assert loader_calls == []
    eval_row = next(row for row in list_eval_runs(db) if row.run_id == "refused-eval")
    assert eval_row.status == "error"
    assert eval_row.error_reason == "source_extraction_run_incomplete"
    assert list_eval_metrics(db, "refused-eval") == []


def test_run_extraction_eval_refusal_clears_stale_metrics_from_existing_eval_run(tmp_path) -> None:
    db = _db(tmp_path)
    _insert_extraction_run(db, "source-run", status="running", expected=1, attempted=0, succeeded=0)
    create_eval_run(
        db,
        run_id="existing-eval",
        eval_type="extraction_eval",
        pipeline_label="old-label",
        params={"stale": "provenance"},
    )
    upsert_eval_metric(db, "existing-eval", "extraction.macro.f1", 1.0)

    with pytest.raises(SourceExtractionRunIncompleteError):
        run_extraction_eval(db, source_run_id="source-run", eval_run_id="existing-eval")

    eval_row = next(row for row in list_eval_runs(db) if row.run_id == "existing-eval")
    assert eval_row.status == "error"
    assert eval_row.pipeline_label == "extraction_eval"
    assert eval_row.error_reason == "source_extraction_run_incomplete"
    assert json.loads(eval_row.params_json or "{}") == {
        "pipeline_label": "extraction_eval",
        "source_run_id": "source-run",
    }
    assert list_eval_metrics(db, "existing-eval") == []


def test_run_extraction_eval_refuses_completed_legacy_run_without_manifest_provenance(tmp_path) -> None:
    db = _db(tmp_path)
    _insert_extraction_run(db, "legacy-run")
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            UPDATE extraction_runs
            SET provider = NULL, requested_model = NULL, corpus_version = NULL,
                manifest_hash = NULL
            WHERE run_id = ?
            """,
            ("legacy-run",),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(SourceExtractionRunIncompleteError):
        run_extraction_eval(db, source_run_id="legacy-run", eval_run_id="legacy-eval")

    eval_row = next(row for row in list_eval_runs(db) if row.run_id == "legacy-eval")
    assert eval_row.error_reason == "source_extraction_run_incomplete"
    assert list_eval_metrics(db, "legacy-eval") == []


def test_run_extraction_eval_refuses_completed_run_without_resolved_model(tmp_path) -> None:
    db = _db(tmp_path)
    _insert_extraction_run(db, "source-run", resolved_model=None)

    with pytest.raises(SourceExtractionRunIncompleteError):
        run_extraction_eval(db, source_run_id="source-run", eval_run_id="missing-model-eval")

    eval_row = next(row for row in list_eval_runs(db) if row.run_id == "missing-model-eval")
    assert eval_row.status == "error"
    assert eval_row.error_reason == "source_extraction_run_incomplete"
    assert list_eval_metrics(db, "missing-model-eval") == []


def test_run_extraction_eval_complete_source_persists_bounded_reproducibility_provenance(
    tmp_path,
) -> None:
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "source-run")
    _insert_history(db, "source-run", "doc1", "vendor_name", "SENTINEL_RAW_PAGE_SECRET")
    _insert_gold(db, "doc1", "vendor_name", "SENTINEL_RAW_PAGE_SECRET")
    insert_extraction_usage_observation(
        db,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc1",
            stage="text_extraction",
            provider="gemini",
            model="gemini-2.5-flash-2026-06-17",
            requested_model="gemini-2.5-flash",
            resolved_model="gemini-2.5-flash-2026-06-17",
            pricing_model="gemini-2.5-flash",
            status="complete",
            input_tokens=100,
            output_tokens=20,
            thought_tokens=5,
            total_tokens=125,
            estimated_cost_usd=0.000105,
            trace_id="trace-private-provider-payload-not-copied",
        ),
    )
    insert_extraction_usage_observation(
        db,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc1",
            stage="visual_fallback",
            provider="gemini",
            model="gemini-2.5-flash-2026-06-17",
            requested_model="gemini-2.5-flash",
            resolved_model="gemini-2.5-flash-2026-06-17",
            pricing_model="gemini-2.5-flash",
            status="complete",
            input_tokens=50,
            output_tokens=10,
            thought_tokens=3,
            total_tokens=63,
            estimated_cost_usd=0.000055,
        ),
    )
    insert_extraction_usage_observation(
        db,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc1",
            stage="visual_fallback",
            status="skipped",
        ),
    )

    eval_run_id = run_extraction_eval(
        db,
        source_run_id="source-run",
        eval_run_id="provenance-eval",
        pipeline_label="strict-extraction-v2",
    )

    assert eval_run_id == "provenance-eval"
    eval_row = next(row for row in list_eval_runs(db) if row.run_id == eval_run_id)
    params = json.loads(eval_row.params_json or "{}")
    assert params == {
        "candidate_tokens": 30,
        "corpus_version": "sdf-synthetic-v1",
        "cost_coverage": 1.0,
        "estimated_cost_usd": pytest.approx(0.00016),
        "expected_document_count": 1,
        "extraction_completed_at": "2026-07-15T10:05:00Z",
        "extraction_run_date": "2026-07-15",
        "extraction_started_at": "2026-07-15T10:00:00Z",
        "failed_document_count": 0,
        "input_tokens": 150,
        "manifest_hash": "a" * 64,
        "pipeline_label": "strict-extraction-v2",
        "pricing_model": "gemini-2.5-flash",
        "pricing_models": ["gemini-2.5-flash"],
        "provider": "gemini",
        "requested_model": "gemini-2.5-flash",
        "resolved_model": "gemini-2.5-flash-2026-06-17",
        "source_run_id": "source-run",
        "source_run_status": "completed",
        "succeeded_document_count": 1,
        "thought_tokens": 8,
        "total_tokens": 188,
        "usage_observation_count": 3,
    }
    serialized_params = json.dumps(params, sort_keys=True).lower()
    for forbidden in (
        "sentinel_raw_page_secret",
        "private-provider-payload",
        "file_path",
        "verbatim_span",
        "page_text",
        "api_key",
    ):
        assert forbidden not in serialized_params


def test_run_extraction_eval_unknown_billable_pricing_keeps_aggregate_cost_null(tmp_path) -> None:
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(
        db,
        "source-run",
        requested_model="gemini-future-alias",
        resolved_model="gemini-future-001",
    )
    insert_extraction_usage_observation(
        db,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc1",
            stage="text_extraction",
            requested_model="gemini-future-alias",
            resolved_model="gemini-future-001",
            pricing_model=None,
            input_tokens=10,
            output_tokens=3,
            thought_tokens=2,
            total_tokens=15,
            estimated_cost_usd=None,
        ),
    )

    run_extraction_eval(db, source_run_id="source-run", eval_run_id="unknown-price-eval")

    eval_row = next(row for row in list_eval_runs(db) if row.run_id == "unknown-price-eval")
    params = json.loads(eval_row.params_json or "{}")
    assert params["candidate_tokens"] == 3
    assert params["thought_tokens"] == 2
    assert params["estimated_cost_usd"] is None
    assert params["cost_coverage"] == 0.0
    assert params["pricing_model"] is None
    assert params["pricing_models"] == []


def test_run_extraction_eval_rejects_primary_usage_model_mismatch(tmp_path) -> None:
    db = _db(tmp_path)
    _insert_document(db, "doc1")
    _insert_extraction_run(db, "source-run")
    insert_extraction_usage_observation(
        db,
        ExtractionUsageObservationRow(
            run_id="source-run",
            doc_id="doc1",
            stage="text_extraction",
            provider="gemini",
            requested_model="gemini-future-alias",
            resolved_model="gemini-future-001",
            status="complete",
            input_tokens=10,
            estimated_cost_usd=None,
        ),
    )

    with pytest.raises(ExtractionEvalError):
        run_extraction_eval(db, source_run_id="source-run", eval_run_id="model-mismatch-eval")

    eval_row = next(row for row in list_eval_runs(db) if row.run_id == "model-mismatch-eval")
    assert eval_row.status == "error"
    assert eval_row.error_reason == "extraction_eval_error"
    assert list_eval_metrics(db, "model-mismatch-eval") == []


def test_run_extraction_eval_generic_failure_persists_only_stable_reason_code(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_updates = _capture_safe_trace_updates(monkeypatch)
    db = _db(tmp_path)
    _insert_extraction_run(db, "source-run")

    def fail_with_sensitive_exception(_db_path: str) -> list[dict]:
        raise RuntimeError("SENTINEL_RAW_PROMPT_SECRET C:/private/source.pdf provider payload")

    monkeypatch.setattr(runner, "_load_optional_gold_labels", fail_with_sensitive_exception)

    with pytest.raises(ExtractionEvalError, match="^extraction_eval_error$") as error:
        run_extraction_eval(db, source_run_id="source-run", eval_run_id="safe-error-eval")

    eval_row = next(row for row in list_eval_runs(db) if row.run_id == "safe-error-eval")
    assert eval_row.status == "error"
    assert eval_row.error_reason == "extraction_eval_error"
    assert list_eval_metrics(db, "safe-error-eval") == []
    persisted_repr = repr(eval_row).lower()
    trace_repr = repr(trace_updates).lower()
    for forbidden in ("sentinel_raw_prompt_secret", "private/source", "provider payload"):
        assert forbidden not in persisted_repr
        assert forbidden not in trace_repr
        assert forbidden not in str(error.value).lower()
    assert trace_updates[-1]["reason_code"] == "extraction_eval_error"
    assert set(trace_updates[-1]).issubset(runner._EXTRACTION_EVAL_TRACE_ALLOWED_KEYS)
