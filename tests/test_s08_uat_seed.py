"""UAT seed-helper contract tests for S08 Eval tab evidence."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from src.eval.repository import list_eval_metrics, list_eval_runs
from scripts.seed_s08_uat_eval_db import EXPECTED_METRICS, SYNTHETIC_RUNS

EXPECTED_RUN_IDS = {run_id for run_id, _pipeline_label, _metrics in SYNTHETIC_RUNS}
FORBIDDEN_RAW_CONTENT_TERMS = {
    "prompt_text",
    "raw_prompt",
    "answer_text",
    "raw_answer",
    "llm_answer",
    "snippet",
    "provider_payload",
    "payload_json",
    "file_path",
    "filepath",
    "source_text",
    "page_text",
    "verbatim",
    "content_hash",
    "image_blob",
    "secret",
}


def run_seed_helper(db_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/seed_s08_uat_eval_db.py", str(db_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_s08_seed_helper_creates_idempotent_synthetic_eval_history(tmp_path: Path) -> None:
    db_path = tmp_path / "s08-uat-eval.db"

    first = run_seed_helper(db_path)
    second = run_seed_helper(db_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert db_path.exists()

    runs = list_eval_runs(str(db_path), limit=10)
    seeded_runs = sorted((run for run in runs if run.run_id in EXPECTED_RUN_IDS), key=lambda run: run.run_id)

    assert [run.run_id for run in seeded_runs] == sorted(EXPECTED_RUN_IDS)
    assert {run.status for run in seeded_runs} == {"complete"}
    assert {run.eval_type for run in seeded_runs} == {"rag_retrieval_uat"}
    assert {run.pipeline_label for run in seeded_runs} == {
        "synthetic-uat-baseline",
        "synthetic-uat-candidate",
    }

    metrics_by_run = {
        run.run_id: {metric.metric_name: metric.metric_value for metric in list_eval_metrics(str(db_path), run.run_id)}
        for run in seeded_runs
    }
    for run_id, metrics in metrics_by_run.items():
        assert set(metrics) == set(EXPECTED_METRICS), run_id
        assert len(metrics) == len(EXPECTED_METRICS)

    baseline = metrics_by_run["s08-uat-eval-run-a"]
    candidate = metrics_by_run["s08-uat-eval-run-b"]
    differing_metrics = [
        name for name in EXPECTED_METRICS if abs(float(candidate[name]) - float(baseline[name])) > 0.0
    ]
    assert set(differing_metrics) == set(EXPECTED_METRICS)
    assert abs(float(candidate["retrieval.recall@5"]) - float(baseline["retrieval.recall@5"])) >= 0.05
    assert abs(float(candidate["rag.latency_ms.avg"]) - float(baseline["rag.latency_ms.avg"])) >= 100.0
    assert abs(float(candidate["rag.tokens.total"]) - float(baseline["rag.tokens.total"])) >= 500.0

    with sqlite3.connect(db_path) as conn:
        metric_count = conn.execute(
            "SELECT COUNT(*) FROM eval_metrics WHERE run_id IN (?, ?)",
            tuple(sorted(EXPECTED_RUN_IDS)),
        ).fetchone()[0]
        assert metric_count == len(EXPECTED_RUN_IDS) * len(EXPECTED_METRICS)


def test_s08_seed_helper_avoids_raw_content_columns_and_seeded_terms(tmp_path: Path) -> None:
    db_path = tmp_path / "s08-uat-eval.db"
    result = run_seed_helper(db_path)
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(db_path) as conn:
        eval_columns = {
            row[1].lower()
            for table in ("eval_runs", "eval_metrics")
            for row in conn.execute(f"PRAGMA table_info({table})")
        }
        assert eval_columns.isdisjoint(FORBIDDEN_RAW_CONTENT_TERMS)

        text_values: list[str] = []
        text_values.extend(
            str(value).lower()
            for row in conn.execute(
                """
                SELECT run_id, eval_type, status, pipeline_label, params_json, error_reason
                FROM eval_runs
                WHERE run_id IN (?, ?)
                """,
                tuple(sorted(EXPECTED_RUN_IDS)),
            )
            for value in row
            if value is not None
        )
        text_values.extend(
            str(value).lower()
            for row in conn.execute(
                """
                SELECT run_id, metric_name, scope_type, scope_id
                FROM eval_metrics
                WHERE run_id IN (?, ?)
                """,
                tuple(sorted(EXPECTED_RUN_IDS)),
            )
            for value in row
            if value is not None
        )

    for value in text_values:
        assert not any(forbidden in value for forbidden in FORBIDDEN_RAW_CONTENT_TERMS), value
