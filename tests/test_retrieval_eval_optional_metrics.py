from __future__ import annotations

import builtins
import sqlite3

import pytest

from src.db.schema import init_db
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
from src.eval.repository import RAGEvalObservationRow, list_eval_metrics
from src.eval.retrieval_eval_runner import run_retrieval_eval
from src.retrieval.indexer import build_retrieval_index


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
