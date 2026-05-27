from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from src.db.schema import init_db
from src.eval import retrieval_eval_runner as runner
from src.eval.repository import list_eval_metrics, list_eval_runs
from src.eval.retrieval_eval_runner import run_retrieval_eval
from src.retrieval.indexer import build_retrieval_index
from src.tracing import filter_trace_metadata


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


def _capture_safe_trace_updates(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []

    def fake_safe_update_current_trace(**kwargs: Any) -> bool:
        updates.append(
            {
                "tags": kwargs.get("tags"),
                "metadata": filter_trace_metadata(
                    kwargs.get("metadata"),
                    kwargs.get("allowed_metadata_keys") or frozenset(),
                ),
            }
        )
        return True

    monkeypatch.setattr(runner, "safe_update_current_trace", fake_safe_update_current_trace)
    return updates


def _assert_eval_trace_metadata_safe(metadata: dict[str, Any]) -> None:
    assert metadata["boundary"] == "evaluation"
    assert metadata["eval_type"] == "retrieval_eval"
    assert set(metadata).issubset(runner._EVALUATION_TRACE_ALLOWED_KEYS)
    metadata_repr = repr(metadata).lower()
    forbidden_fragments = (
        "query_text",
        "alpha beta",
        "gamma delta",
        "raw prompt",
        "secret",
        "sk-test",
        "snippet",
        "page_text",
        "provider_payload",
        "content_hash",
    )
    for forbidden in forbidden_fragments:
        assert forbidden not in metadata_repr


def test_retrieval_eval_runner_persists_eval_run_and_metrics(tmp_path):
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _insert_document(conn, "d1", "doc1.pdf", ["alpha beta", "gamma delta"])
        _insert_document(conn, "d2", "doc2.pdf", ["epsilon zeta", "alpha omega"])

        _insert_gold_query(conn, "q1", "alpha")
        _insert_gold_target(conn, "q1", "d1", 0)

        _insert_gold_query(conn, "q2", "gamma")
        _insert_gold_target(conn, "q2", "d1", 1)

        conn.commit()
    finally:
        conn.close()

    # Build a retrieval index so retrieval_eval has a run_id to reference.
    build_retrieval_index(db_path)

    run_id = run_retrieval_eval(db_path, k_values=(5, 10))

    runs = list_eval_runs(db_path)
    assert any(r.run_id == run_id and r.eval_type == "retrieval_eval" and r.status == "complete" for r in runs)

    metrics = list_eval_metrics(db_path, run_id)
    metric_index = {(m.metric_name, m.scope_type, m.scope_id): m.metric_value for m in metrics}

    # Summary metrics
    assert metric_index[("retrieval.recall@5", None, None)] == 1.0
    assert metric_index[("retrieval.recall@10", None, None)] == 1.0
    assert metric_index[("retrieval.citation_accuracy@5", None, None)] == 1.0

    # Per-query metrics
    assert metric_index[("retrieval.recall@5", "query", "q1")] == 1.0
    assert metric_index[("retrieval.recall@5", "query", "q2")] == 1.0

    # Ensure we didn't create duplicates for global rows.
    assert sum(1 for key in metric_index if key == ("retrieval.recall@5", None, None)) == 1


def test_retrieval_eval_runner_empty_state_marks_complete(tmp_path):
    db_path = str(tmp_path / "empty.sqlite")
    init_db(db_path)

    run_id = run_retrieval_eval(db_path, k_values=(5,))

    runs = list_eval_runs(db_path)
    row = next(r for r in runs if r.run_id == run_id)
    assert row.status == "complete"

    metrics = list_eval_metrics(db_path, run_id)
    assert metrics == []


def test_retrieval_eval_trace_metadata_for_complete_run_is_bounded(tmp_path, monkeypatch):
    trace_updates = _capture_safe_trace_updates(monkeypatch)
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _insert_document(conn, "d1", "doc1.pdf", ["alpha beta", "gamma delta"])
        _insert_gold_query(conn, "q1", "alpha SECRET_QUERY_TEXT_SHOULD_NOT_APPEAR")
        _insert_gold_target(conn, "q1", "d1", 0)
        conn.commit()
    finally:
        conn.close()

    index_result = build_retrieval_index(db_path)
    run_id = run_retrieval_eval(db_path, k_values=(5,))

    metadata_updates = [update["metadata"] for update in trace_updates]
    assert [metadata["status"] for metadata in metadata_updates] == ["started", "complete"]
    for metadata in metadata_updates:
        _assert_eval_trace_metadata_safe(metadata)
        assert metadata["run_id"] == run_id
        assert metadata["retrieval_run_id"] == index_result.run.run_id
        assert metadata["k_values"] == [5]
        assert metadata["include_latency_cost"] is False
        assert metadata["include_ragas"] is False
    assert metadata_updates[-1]["query_count"] == 1
    assert metadata_updates[-1]["metric_count"] == 4


def test_retrieval_eval_trace_metadata_for_empty_run_is_bounded(tmp_path, monkeypatch):
    trace_updates = _capture_safe_trace_updates(monkeypatch)
    db_path = str(tmp_path / "empty.sqlite")
    init_db(db_path)

    run_id = run_retrieval_eval(db_path, k_values=(5, 10))

    metadata_updates = [update["metadata"] for update in trace_updates]
    assert [metadata["status"] for metadata in metadata_updates] == ["started", "empty"]
    for metadata in metadata_updates:
        _assert_eval_trace_metadata_safe(metadata)
        assert metadata["run_id"] == run_id
        assert metadata["query_count"] == 0
        assert metadata["metric_count"] == 0
        assert metadata["k_values"] == [5, 10]


def test_retrieval_eval_trace_backend_failure_does_not_change_runner_behavior(tmp_path, monkeypatch):
    calls: list[dict[str, Any]] = []

    def failed_safe_update_current_trace(**kwargs: Any) -> bool:
        calls.append(kwargs)
        return False

    monkeypatch.setattr(runner, "safe_update_current_trace", failed_safe_update_current_trace)
    db_path = str(tmp_path / "empty.sqlite")
    init_db(db_path)

    run_id = run_retrieval_eval(db_path, k_values=(5,))

    row = next(r for r in list_eval_runs(db_path) if r.run_id == run_id)
    assert row.status == "complete"
    assert len(calls) == 2
