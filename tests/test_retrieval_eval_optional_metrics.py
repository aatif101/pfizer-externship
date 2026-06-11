from __future__ import annotations

import builtins
import sqlite3
from typing import Any

import pytest

from src.db.schema import init_db
from src.eval import retrieval_eval_runner as runner
from src.eval.operational_metrics import (
    ANSWER_RELEVANCY_AVG,
    COST_AVG_USD,
    COST_TOTAL_USD,
    FAITHFULNESS_AVG,
    INPUT_TOKENS_TOTAL,
    LATENCY_AVG_MS,
    LATENCY_P50_MS,
    LATENCY_P95_MS,
    OUTPUT_TOKENS_TOTAL,
    TOTAL_TOKENS_TOTAL,
    aggregate_observation_metrics,
)
from src.eval.repository import RAGEvalObservationRow, insert_rag_eval_observation, list_eval_metrics, list_eval_runs
from src.eval.retrieval_eval_runner import run_retrieval_eval
from src.retrieval.indexer import build_retrieval_index
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


def _insert_document(conn: sqlite3.Connection, doc_id: str, filename: str, page_texts: list[str]) -> None:
    conn.execute(
        "INSERT INTO documents (doc_id, filename, file_path, page_count, status) VALUES (?, ?, ?, ?, ?)",
        (doc_id, filename, f"/tmp/{filename}", len(page_texts), "ingested"),
    )
    for idx, text in enumerate(page_texts):
        conn.execute(
            "INSERT INTO pages (doc_id, page_num, page_text) VALUES (?, ?, ?)",
            (doc_id, idx, text),
        )


def _insert_gold_query(conn: sqlite3.Connection, query_id: str, query_text: str) -> None:
    conn.execute(
        "INSERT INTO gold_retrieval_queries (query_id, query_text) VALUES (?, ?)",
        (query_id, query_text),
    )


def _insert_gold_target(conn: sqlite3.Connection, query_id: str, doc_id: str, page_num: int) -> None:
    conn.execute(
        "INSERT INTO gold_retrieval_targets (query_id, doc_id, page_num) VALUES (?, ?, ?)",
        (query_id, doc_id, page_num),
    )


def test_operational_metrics_compute_latency_percentiles_from_unsorted_rows() -> None:
    rows = [
        {"latency_ms": 400.0},
        {"latency_ms": 100.0},
        {"latency_ms": 300.0},
        {"latency_ms": 200.0},
    ]

    metrics = aggregate_observation_metrics(rows)

    assert metrics[LATENCY_AVG_MS] == 250.0
    assert metrics[LATENCY_P50_MS] == 250.0
    assert metrics[LATENCY_P95_MS] == pytest.approx(385.0)


def test_operational_metrics_one_row_latency_percentile_boundaries() -> None:
    metrics = aggregate_observation_metrics([RAGEvalObservationRow(latency_ms=123.0)])

    assert metrics[LATENCY_AVG_MS] == 123.0
    assert metrics[LATENCY_P50_MS] == 123.0
    assert metrics[LATENCY_P95_MS] == 123.0


def test_operational_metrics_empty_null_and_missing_inputs_emit_no_metrics() -> None:
    assert aggregate_observation_metrics([]) == {}
    assert aggregate_observation_metrics([
        {},
        {
            "latency_ms": None,
            "cost_usd": None,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "faithfulness": None,
            "answer_relevancy": None,
        },
        RAGEvalObservationRow(status="error"),
    ]) == {}


def test_operational_metrics_compute_cost_and_token_totals_without_zero_fill() -> None:
    rows = [
        {"cost_usd": 1.25, "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        {"cost_usd": 0.75, "input_tokens": 7, "total_tokens": None},
        {"output_tokens": 3},
    ]

    metrics = aggregate_observation_metrics(rows)

    assert metrics[COST_TOTAL_USD] == 2.0
    assert metrics[COST_AVG_USD] == 1.0
    assert metrics[INPUT_TOKENS_TOTAL] == 17.0
    assert metrics[OUTPUT_TOKENS_TOTAL] == 8.0
    assert metrics[TOTAL_TOKENS_TOTAL] == 15.0


def test_operational_metrics_compute_quality_averages_from_precomputed_scores() -> None:
    rows = [
        RAGEvalObservationRow(faithfulness=0.8, answer_relevancy=0.7),
        RAGEvalObservationRow(faithfulness=None, answer_relevancy=0.9),
        RAGEvalObservationRow(faithfulness=1.0, answer_relevancy=None),
    ]

    metrics = aggregate_observation_metrics(rows)

    assert metrics[FAITHFULNESS_AVG] == pytest.approx(0.9)
    assert metrics[ANSWER_RELEVANCY_AVG] == pytest.approx(0.8)


def test_operational_metrics_reject_malformed_non_null_numeric_values() -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        aggregate_observation_metrics([{"latency_ms": "slow"}])

    with pytest.raises(ValueError, match="input_tokens"):
        aggregate_observation_metrics([{"input_tokens": True}])


def test_retrieval_eval_runner_optional_flags_do_not_crash_on_minimal_db(tmp_path, monkeypatch):
    """Enabling optional flags should degrade gracefully when prerequisites are absent.

    This DB has:
    - retrieval index + gold queries (so core metrics are computed)
    - no trace/observability tables
    - no gold answers/contexts and no ragas installed

    The runner should still finish and persist core retrieval metrics.
    """

    original_import = builtins.__import__

    def fail_on_ragas_import(name, *args, **kwargs):
        if name == "ragas" or name.startswith("ragas."):
            raise AssertionError("optional metric aggregation must not import RAGAS")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_ragas_import)

    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _insert_document(conn, "d1", "doc1.pdf", ["alpha beta", "gamma delta"])
        _insert_document(conn, "d2", "doc2.pdf", ["epsilon zeta", "alpha omega"])

        _insert_gold_query(conn, "q1", "alpha")
        _insert_gold_target(conn, "q1", "d1", 0)

        conn.commit()
    finally:
        conn.close()

    build_retrieval_index(db_path)

    run_id = run_retrieval_eval(db_path, k_values=(5,), include_latency_cost=True, include_ragas=True)

    metrics = list_eval_metrics(db_path, run_id)
    metric_names = {m.metric_name for m in metrics}

    assert "retrieval.recall@5" in metric_names
    assert "retrieval.citation_accuracy@5" in metric_names

    # Optional metrics are not required to exist; this just ensures no crash + core persisted.


def test_retrieval_eval_runner_persists_optional_rag_metrics_from_observations(tmp_path, monkeypatch):
    trace_updates = _capture_safe_trace_updates(monkeypatch)
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _insert_document(conn, "d1", "doc1.pdf", ["alpha beta", "gamma delta"])
        _insert_gold_query(conn, "q1", "alpha")
        _insert_gold_target(conn, "q1", "d1", 0)
        conn.commit()
    finally:
        conn.close()

    index_result = build_retrieval_index(db_path)
    source_run_id = index_result.run.run_id
    insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(
            source_run_id=source_run_id,
            query_id="q1",
            status="answered",
            latency_ms=100.0,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost_usd=0.25,
            faithfulness=0.8,
            answer_relevancy=0.6,
            cited_doc_id="d1",
            cited_page_num=0,
        ),
    )
    insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(
            source_run_id=source_run_id,
            query_id="q1",
            status="answered",
            latency_ms=300.0,
            input_tokens=20,
            output_tokens=15,
            total_tokens=35,
            cost_usd=0.75,
            faithfulness=1.0,
            answer_relevancy=0.8,
            cited_doc_id="d1",
            cited_page_num=0,
        ),
    )
    insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(
            source_run_id="unrelated-run",
            query_id="q1",
            status="answered",
            latency_ms=999.0,
            cost_usd=999.0,
            faithfulness=0.0,
            answer_relevancy=0.0,
        ),
    )

    run_id = run_retrieval_eval(db_path, k_values=(5,), include_latency_cost=True, include_ragas=True)

    metric_index = {(m.metric_name, m.scope_type, m.scope_id): m.metric_value for m in list_eval_metrics(db_path, run_id)}

    assert metric_index[("retrieval.recall@5", None, None)] == 1.0
    assert metric_index[(LATENCY_AVG_MS, None, None)] == 200.0
    assert metric_index[(LATENCY_P50_MS, None, None)] == 200.0
    assert metric_index[(LATENCY_P95_MS, None, None)] == pytest.approx(290.0)
    assert metric_index[(COST_TOTAL_USD, None, None)] == 1.0
    assert metric_index[(COST_AVG_USD, None, None)] == 0.5
    assert metric_index[(INPUT_TOKENS_TOTAL, None, None)] == 30.0
    assert metric_index[(OUTPUT_TOKENS_TOTAL, None, None)] == 20.0
    assert metric_index[(TOTAL_TOKENS_TOTAL, None, None)] == 50.0
    assert metric_index[(FAITHFULNESS_AVG, None, None)] == pytest.approx(0.9)
    assert metric_index[(ANSWER_RELEVANCY_AVG, None, None)] == pytest.approx(0.7)

    final_trace_metadata = trace_updates[-1]
    assert final_trace_metadata["status"] == "complete"
    assert final_trace_metadata["boundary"] == "evaluation"
    assert final_trace_metadata["eval_type"] == "retrieval_eval"
    assert final_trace_metadata["run_id"] == run_id
    assert final_trace_metadata["retrieval_run_id"] == source_run_id
    assert final_trace_metadata["query_count"] == 1
    assert final_trace_metadata["k_values"] == [5]
    assert final_trace_metadata["metric_count"] == 14
    assert final_trace_metadata["include_latency_cost"] is True
    assert final_trace_metadata["include_ragas"] is True
    assert set(final_trace_metadata).issubset(runner._EVALUATION_TRACE_ALLOWED_KEYS)
    assert "answered" not in repr(trace_updates).lower()


def test_retrieval_eval_runner_missing_observation_table_is_optional_noop(tmp_path):
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _insert_document(conn, "d1", "doc1.pdf", ["alpha beta"])
        _insert_gold_query(conn, "q1", "alpha")
        _insert_gold_target(conn, "q1", "d1", 0)
        conn.commit()
    finally:
        conn.close()

    build_retrieval_index(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE rag_eval_observations")
        conn.commit()
    finally:
        conn.close()

    run_id = run_retrieval_eval(db_path, k_values=(5,), include_latency_cost=True, include_ragas=True)

    metric_names = {m.metric_name for m in list_eval_metrics(db_path, run_id)}
    assert "retrieval.recall@5" in metric_names
    assert LATENCY_AVG_MS not in metric_names
    assert FAITHFULNESS_AVG not in metric_names


def test_retrieval_eval_runner_malformed_observation_marks_sanitized_error(tmp_path, monkeypatch):
    trace_updates = _capture_safe_trace_updates(monkeypatch)
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _insert_document(conn, "d1", "doc1.pdf", ["alpha beta"])
        _insert_gold_query(conn, "q1", "alpha")
        _insert_gold_target(conn, "q1", "d1", 0)
        conn.commit()
    finally:
        conn.close()

    index_result = build_retrieval_index(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO rag_eval_observations (source_run_id, query_id, status, latency_ms)
            VALUES (?, ?, ?, ?)
            """,
            (index_result.run.run_id, "q1", "answered", "slow <raw prompt should not leak>"),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="latency_ms"):
        run_retrieval_eval(db_path, k_values=(5,), include_latency_cost=True)

    runs = list_eval_runs(db_path)
    row = next(r for r in runs if r.eval_type == "retrieval_eval")
    assert row.status == "error"
    assert row.error_reason is not None
    assert "ValueError: latency_ms must be numeric or None" in row.error_reason
    assert "<" not in row.error_reason
    assert "raw prompt" not in row.error_reason

    error_trace_metadata = trace_updates[-1]
    assert error_trace_metadata["status"] == "error"
    assert error_trace_metadata["boundary"] == "evaluation"
    assert error_trace_metadata["eval_type"] == "retrieval_eval"
    assert error_trace_metadata["run_id"] == row.run_id
    assert error_trace_metadata["retrieval_run_id"] == index_result.run.run_id
    assert error_trace_metadata["query_count"] == 1
    assert error_trace_metadata["metric_count"] == 4
    assert error_trace_metadata["error_class"] == "ValueError"
    error_metadata_repr = repr(error_trace_metadata).lower()
    assert "slow" not in error_metadata_repr
    assert "raw prompt" not in error_metadata_repr
    assert "secret" not in error_metadata_repr


def test_run_retrieval_eval_wires_injected_ragas_scorer(tmp_path, monkeypatch):
    """An injected ragas_scorer flows through include_ragas and lights up aggregates.

    This proves the producer wiring without installing ragas: a fake scorer and a
    fake answer_fn keep everything offline while the real run_retrieval_eval path
    produces observation rows that the existing aggregation averages.
    """

    from src.eval import ragas_quality
    from src.rag.models import (
        AnswerCitation,
        AnswerDiagnostics,
        AnswerReasonCode,
        AnswerResult,
        AnswerStatus,
    )

    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _insert_document(conn, "d1", "doc1.pdf", ["alpha beta", "gamma delta"])
        _insert_gold_query(conn, "q1", "alpha")
        _insert_gold_target(conn, "q1", "d1", 0)
        conn.commit()
    finally:
        conn.close()

    build_retrieval_index(db_path)

    def fake_answer_fn(db, question, *, provider=None, **kwargs):
        citation = AnswerCitation(
            doc_id="d1",
            filename="doc1.pdf",
            page_num=0,
            display_page_num=1,
            snippet="alpha beta",
            score=0.9,
        )
        return AnswerResult(
            status=AnswerStatus.ANSWERED,
            answer_text="alpha is present",
            citations=(citation,),
            diagnostics=AnswerDiagnostics(
                status=AnswerStatus.ANSWERED,
                reason_code=AnswerReasonCode.ANSWERED,
                run_id="run-1",
                provider_name="fake",
                trace_id=None,
                top_score=0.9,
                citation_count=1,
                evidence_reason="ok",
            ),
        )

    # Patch the producer's default answer_fn resolution so no live RAG call runs.
    original_compute = ragas_quality.compute_ragas_quality

    def patched_compute(db, *, source_run_id, scorer, answer_fn=None, provider=None):
        return original_compute(
            db,
            source_run_id=source_run_id,
            scorer=scorer,
            answer_fn=fake_answer_fn,
            provider=object(),
        )

    monkeypatch.setattr("src.eval.ragas_quality.compute_ragas_quality", patched_compute)

    def fake_scorer(sample):
        return (0.75, 0.65)

    run_id = run_retrieval_eval(db_path, k_values=(5,), include_ragas=True, ragas_scorer=fake_scorer)

    metric_index = {
        (m.metric_name, m.scope_type, m.scope_id): m.metric_value for m in list_eval_metrics(db_path, run_id)
    }
    assert metric_index[(FAITHFULNESS_AVG, None, None)] == pytest.approx(0.75)
    assert metric_index[(ANSWER_RELEVANCY_AVG, None, None)] == pytest.approx(0.65)
