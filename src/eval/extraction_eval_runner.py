"""Provider-free extraction eval runner.

Turns ``extraction_history`` rows plus ``gold_extraction_labels`` into
per-field and macro precision/recall/F1 ``eval_metrics`` for a given
extraction run. Intentionally imports no provider SDKs, RAGAS, or Streamlit.
"""

from __future__ import annotations

import re
import sqlite3
import uuid

from src.eval.extraction_metrics import (
    compute_extraction_field_scores,
    compute_macro_averages,
)
from src.eval.repository import (
    create_eval_run,
    list_gold_extraction_labels,
    list_predicted_extractions_for_run,
    mark_eval_run_complete,
    mark_eval_run_error,
    upsert_eval_metric,
)
from src.tracing import observe, safe_update_current_trace

_EXTRACTION_EVAL_TRACE_ALLOWED_KEYS = frozenset(
    {
        "boundary",
        "status",
        "eval_type",
        "run_id",
        "source_run_id",
        "gold_count",
        "pred_count",
        "metric_count",
        "error_class",
    }
)
_ERROR_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 _.:\-/#]+")


@observe(name="extraction_eval_run")
def run_extraction_eval(
    db_path: str,
    *,
    source_run_id: str,
    eval_run_id: str | None = None,
    pipeline_label: str = "extraction_eval",
) -> str:
    """Compute extraction field metrics for one extraction run.

    Returns the eval run id. Empty or older DBs with no gold or history tables
    complete successfully with no metrics. Malformed persisted values fail
    visibly, mark the eval run ``error``, and store only a sanitized error
    class/message.
    """

    run_id = eval_run_id or uuid.uuid4().hex
    gold_count = 0
    pred_count = 0
    metric_count = 0
    _update_trace_metadata(
        status="started",
        run_id=run_id,
        source_run_id=source_run_id,
        gold_count=gold_count,
        pred_count=pred_count,
        metric_count=metric_count,
    )

    create_eval_run(
        db_path,
        run_id=run_id,
        eval_type="extraction_eval",
        pipeline_label=pipeline_label,
        params={"source_run_id": source_run_id},
    )

    try:
        gold_rows = _load_optional_gold_labels(db_path)
        pred_rows = _load_optional_predicted_extractions(db_path, source_run_id)
        gold_count = len(gold_rows)
        pred_count = len(pred_rows)

        if gold_count == 0 or pred_count == 0:
            mark_eval_run_complete(db_path, run_id)
            _update_trace_metadata(
                status="complete",
                run_id=run_id,
                source_run_id=source_run_id,
                gold_count=gold_count,
                pred_count=pred_count,
                metric_count=metric_count,
            )
            return run_id

        per_field = compute_extraction_field_scores(gold_rows, pred_rows)
        macro = compute_macro_averages(per_field)

        # Global macro metrics (no scope)
        for suffix, value in macro.items():
            upsert_eval_metric(db_path, run_id, f"extraction.macro.{suffix}", value)
            metric_count += 1

        # Per-field scoped metrics
        for field_name, score in per_field.items():
            for suffix, value in (
                ("f1", score.f1),
                ("precision", score.precision),
                ("recall", score.recall),
            ):
                upsert_eval_metric(
                    db_path,
                    run_id,
                    f"extraction.{suffix}",
                    value,
                    scope_type="field",
                    scope_id=field_name,
                )
                metric_count += 1

        mark_eval_run_complete(db_path, run_id)
        _update_trace_metadata(
            status="complete",
            run_id=run_id,
            source_run_id=source_run_id,
            gold_count=gold_count,
            pred_count=pred_count,
            metric_count=metric_count,
        )
        return run_id

    except Exception as exc:
        mark_eval_run_error(db_path, run_id, _sanitize_error(exc))
        _update_trace_metadata(
            status="error",
            run_id=run_id,
            source_run_id=source_run_id,
            gold_count=gold_count,
            pred_count=pred_count,
            metric_count=metric_count,
            error_class=exc.__class__.__name__,
        )
        raise


def _load_optional_gold_labels(db_path: str) -> list[dict]:
    try:
        return list_gold_extraction_labels(db_path)
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _load_optional_predicted_extractions(db_path: str, source_run_id: str) -> list[dict]:
    try:
        return list_predicted_extractions_for_run(db_path, source_run_id)
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _update_trace_metadata(
    *,
    status: str,
    run_id: str,
    source_run_id: str,
    gold_count: int,
    pred_count: int,
    metric_count: int,
    error_class: str | None = None,
) -> None:
    """Attach bounded extraction eval metadata to the current trace.

    Metadata is limited to identifiers, status, and counts. It never includes
    raw prompts, page text, provider payloads, document paths, images, PDFs,
    secrets, or raw exception strings.
    """

    safe_update_current_trace(
        tags=["evaluation", "extraction_eval"],
        metadata={
            "boundary": "evaluation",
            "status": status,
            "eval_type": "extraction_eval",
            "run_id": run_id,
            "source_run_id": source_run_id,
            "gold_count": gold_count,
            "pred_count": pred_count,
            "metric_count": metric_count,
            "error_class": error_class,
        },
        allowed_metadata_keys=_EXTRACTION_EVAL_TRACE_ALLOWED_KEYS,
    )


def _sanitize_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    message = _ERROR_SANITIZE_RE.sub("", message)
    return message[:500]
