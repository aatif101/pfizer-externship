"""Seed a deterministic synthetic Eval-tab UAT database for S08.

This script intentionally writes only synthetic run identifiers, pipeline labels,
and metric names/values. It does not read documents, call providers, write raw
prompts/answers/snippets, or persist file paths/source text/hashes/images.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

# Allow `python scripts/seed_s08_uat_eval_db.py ...` from the repo root without
# requiring package installation or PYTHONPATH tweaks on Windows.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.schema import init_db
from src.eval.repository import create_eval_run, mark_eval_run_complete, upsert_eval_metric

MetricMap = dict[str, float]

EXPECTED_METRICS: Final[tuple[str, ...]] = (
    "retrieval.recall@5",
    "retrieval.recall@10",
    "retrieval.citation_accuracy@5",
    "retrieval.citation_accuracy@10",
    "rag.faithfulness.avg",
    "rag.answer_relevancy.avg",
    "rag.latency_ms.avg",
    "rag.latency_ms.p50",
    "rag.latency_ms.p95",
    "rag.cost_usd.total",
    "rag.cost_usd.avg",
    "rag.tokens.total",
)

SYNTHETIC_RUNS: Final[tuple[tuple[str, str, MetricMap], ...]] = (
    (
        "s08-uat-eval-run-a",
        "synthetic-uat-baseline",
        {
            "retrieval.recall@5": 0.72,
            "retrieval.recall@10": 0.84,
            "retrieval.citation_accuracy@5": 0.68,
            "retrieval.citation_accuracy@10": 0.78,
            "rag.faithfulness.avg": 0.81,
            "rag.answer_relevancy.avg": 0.79,
            "rag.latency_ms.avg": 1420.0,
            "rag.latency_ms.p50": 1180.0,
            "rag.latency_ms.p95": 2410.0,
            "rag.cost_usd.total": 0.0432,
            "rag.cost_usd.avg": 0.00432,
            "rag.tokens.total": 18400.0,
        },
    ),
    (
        "s08-uat-eval-run-b",
        "synthetic-uat-candidate",
        {
            "retrieval.recall@5": 0.80,
            "retrieval.recall@10": 0.90,
            "retrieval.citation_accuracy@5": 0.74,
            "retrieval.citation_accuracy@10": 0.86,
            "rag.faithfulness.avg": 0.88,
            "rag.answer_relevancy.avg": 0.85,
            "rag.latency_ms.avg": 1275.0,
            "rag.latency_ms.p50": 1015.0,
            "rag.latency_ms.p95": 2185.0,
            "rag.cost_usd.total": 0.0396,
            "rag.cost_usd.avg": 0.00396,
            "rag.tokens.total": 17650.0,
        },
    ),
)


def seed_database(db_path: str) -> None:
    """Initialize ``db_path`` and upsert the deterministic S08 synthetic runs."""

    target = Path(db_path)
    if target.exists() and target.is_dir():
        raise ValueError(f"Database path is a directory: {target}")

    init_db(str(target))

    for run_id, pipeline_label, metrics in SYNTHETIC_RUNS:
        create_eval_run(
            str(target),
            run_id=run_id,
            eval_type="rag_retrieval_uat",
            pipeline_label=pipeline_label,
            params={"dataset": "synthetic_s08_uat", "version": 1},
        )
        for metric_name in EXPECTED_METRICS:
            upsert_eval_metric(str(target), run_id, metric_name, metrics[metric_name])
        mark_eval_run_complete(str(target), run_id)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a SQLite database with synthetic S08 Eval-tab UAT metric history."
    )
    parser.add_argument("db_path", help="SQLite database path to create or update.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        seed_database(args.db_path)
    except Exception as exc:  # pragma: no cover - exercised by CLI behavior.
        print(f"Failed to seed S08 UAT eval database: {exc}", file=sys.stderr)
        return 1

    print(f"Seeded {len(SYNTHETIC_RUNS)} synthetic eval runs in {args.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
