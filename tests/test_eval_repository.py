from __future__ import annotations

import json

import pytest

from src.db.schema import init_db
from src.eval.repository import (
    RAGEvalObservationRow,
    create_eval_run,
    insert_rag_eval_observation,
    list_eval_metrics,
    list_eval_runs,
    list_gold_extraction_labels,
    list_gold_retrieval_queries,
    list_gold_retrieval_targets,
    list_rag_eval_observations,
    mark_eval_run_complete,
    mark_eval_run_error,
    upsert_eval_metric,
)


def test_eval_run_create_and_list_is_idempotent(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    create_eval_run(
        db_path,
        run_id="run-1",
        eval_type="extraction",
        pipeline_label="baseline",
        params={"a": 1, "b": 2},
    )
    # Streamlit rerun simulation
    create_eval_run(
        db_path,
        run_id="run-1",
        eval_type="extraction",
        pipeline_label="baseline",
        params={"b": 2, "a": 1},
    )

    runs = list_eval_runs(db_path)
    assert [r.run_id for r in runs] == ["run-1"]
    assert runs[0].status == "running"
    assert runs[0].pipeline_label == "baseline"
    assert json.loads(runs[0].params_json or "{}") == {"a": 1, "b": 2}

    mark_eval_run_complete(db_path, "run-1")
    runs2 = list_eval_runs(db_path)
    assert runs2[0].status == "complete"
    assert runs2[0].completed_at is not None


def test_eval_run_error_sets_status_and_reason(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    create_eval_run(db_path, "run-err", "retrieval", "pl", params={})
    mark_eval_run_error(db_path, "run-err", "boom")

    runs = list_eval_runs(db_path)
    assert runs[0].run_id == "run-err"
    assert runs[0].status == "error"
    assert runs[0].error_reason == "boom"
    assert runs[0].completed_at is not None


def test_eval_metric_upsert_dedupes(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)
    create_eval_run(db_path, "run-1", "rag", None, params={})

    upsert_eval_metric(db_path, "run-1", "faithfulness", 0.5)
    upsert_eval_metric(db_path, "run-1", "faithfulness", 0.7)

    metrics = list_eval_metrics(db_path, "run-1")
    assert len(metrics) == 1
    assert metrics[0].metric_name == "faithfulness"
    assert metrics[0].metric_value == 0.7

    upsert_eval_metric(db_path, "run-1", "ndcg@5", 0.8, scope_type="query", scope_id="q1")
    upsert_eval_metric(db_path, "run-1", "ndcg@5", 0.9, scope_type="query", scope_id="q1")

    metrics2 = list_eval_metrics(db_path, "run-1")
    assert len(metrics2) == 2
    by_key = {(m.metric_name, m.scope_type, m.scope_id): m for m in metrics2}
    assert by_key[("ndcg@5", "query", "q1")].metric_value == 0.9


def test_gold_list_helpers_return_empty_lists_on_empty_db(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    assert list_gold_extraction_labels(db_path) == []
    assert list_gold_retrieval_queries(db_path) == []
    assert list_gold_retrieval_targets(db_path, "missing") == []


def test_rag_eval_observation_insert_and_list_multiple_rows(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    first_id = insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(
            source_run_id="rag-run-1",
            query_id="q1",
            status="complete",
            latency_ms="123.5",
            input_tokens="10",
            output_tokens=20,
            total_tokens=30,
            cost_usd="0.0042",
            faithfulness="0.9",
            answer_relevancy=0.8,
            cited_doc_id="doc-a",
            cited_page_num="2",
        ),
    )
    second_id = insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(
            source_run_id="rag-run-2",
            query_id="q2",
            status="weak_evidence",
            latency_ms=50,
            input_tokens=5,
            output_tokens=6,
            total_tokens=11,
            cost_usd=0.001,
            faithfulness=None,
            answer_relevancy=None,
            cited_doc_id=None,
            cited_page_num=None,
        ),
    )

    assert first_id != second_id
    observations = list_rag_eval_observations(db_path)
    assert [row.observation_id for row in observations] == [first_id, second_id]
    assert observations[0].source_run_id == "rag-run-1"
    assert observations[0].query_id == "q1"
    assert observations[0].latency_ms == 123.5
    assert observations[0].input_tokens == 10
    assert observations[0].output_tokens == 20
    assert observations[0].total_tokens == 30
    assert observations[0].cost_usd == 0.0042
    assert observations[0].faithfulness == 0.9
    assert observations[0].answer_relevancy == 0.8
    assert observations[0].cited_doc_id == "doc-a"
    assert observations[0].cited_page_num == 2
    assert observations[0].created_at is not None

    by_source = list_rag_eval_observations(db_path, source_run_id="rag-run-2")
    assert [row.query_id for row in by_source] == ["q2"]

    by_query = list_rag_eval_observations(db_path, query_id="q1")
    assert [row.source_run_id for row in by_query] == ["rag-run-1"]


def test_rag_eval_observation_empty_and_nullable_numeric_fields(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    assert list_rag_eval_observations(db_path, source_run_id="missing") == []

    row_id = insert_rag_eval_observation(
        db_path,
        RAGEvalObservationRow(source_run_id="rag-run-null", query_id="q-null", status="error"),
    )

    observations = list_rag_eval_observations(db_path)
    assert len(observations) == 1
    assert observations[0].observation_id == row_id
    assert observations[0].latency_ms is None
    assert observations[0].input_tokens is None
    assert observations[0].output_tokens is None
    assert observations[0].total_tokens is None
    assert observations[0].cost_usd is None
    assert observations[0].faithfulness is None
    assert observations[0].answer_relevancy is None
    assert observations[0].cited_page_num is None


def test_rag_eval_observation_rejects_malformed_numeric_values(tmp_path):
    db_path = str(tmp_path / "eval.db")
    init_db(db_path)

    with pytest.raises(ValueError, match="latency_ms"):
        insert_rag_eval_observation(
            db_path,
            RAGEvalObservationRow(status="complete", latency_ms="slow"),
        )

    with pytest.raises(ValueError, match="input_tokens"):
        insert_rag_eval_observation(
            db_path,
            RAGEvalObservationRow(status="complete", input_tokens=True),
        )

    assert list_rag_eval_observations(db_path) == []
