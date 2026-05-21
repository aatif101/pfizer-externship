from __future__ import annotations

import json

from src.db.schema import init_db
from src.eval.repository import (
    create_eval_run,
    list_eval_metrics,
    list_eval_runs,
    list_gold_extraction_labels,
    list_gold_retrieval_queries,
    list_gold_retrieval_targets,
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
