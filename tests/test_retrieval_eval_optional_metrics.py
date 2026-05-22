from __future__ import annotations

import sqlite3

from src.db.schema import init_db
from src.eval.repository import list_eval_metrics
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


def test_retrieval_eval_runner_optional_flags_do_not_crash_on_minimal_db(tmp_path):
    """Enabling optional flags should degrade gracefully when prerequisites are absent.

    This DB has:
    - retrieval index + gold queries (so core metrics are computed)
    - no trace/observability tables
    - no gold answers/contexts and no ragas installed

    The runner should still finish and persist core retrieval metrics.
    """

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
