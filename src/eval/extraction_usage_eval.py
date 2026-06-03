"""Provider-free aggregation runner for extraction usage observations.

This helper turns bounded ``extraction_usage_observations`` rows into dashboard-
readable ``eval_metrics``. It intentionally imports no provider SDKs, RAGAS, or
Streamlit; the source rows already contain the only allowed usage telemetry.
"""

from __future__ import annotations

import re
import sqlite3
import uuid

from src.eval.operational_metrics import aggregate_extraction_usage_metrics
from src.eval.repository import (
    create_eval_run,
    list_extraction_usage_observations,
    mark_eval_run_complete,
    mark_eval_run_error,
    upsert_eval_metric,
)
from src.tracing import observe, safe_update_current_trace

_EXTRACTION_USAGE_TRACE_ALLOWED_KEYS = frozenset(
    {
        "boundary",
        "status",
        "eval_type",
        "run_id",
        "source_run_id",
        "observation_count",
        "metric_count",
        "error_class",
    }
)
_ERROR_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 _.:\-/#]+")


@observe(name="extraction_usage_eval_run")
def run_extraction_usage_eval(
    db_path: str,
    *,
    source_run_id: str,
    eval_run_id: str | None = None,
    pipeline_label: str | None = "extraction_usage_eval",
    max_observations: int = 10_000,
) -> str:
    """Aggregate usage observations for one extraction run into eval metrics.

    Returns the eval run id. Empty or older DBs with no observation table complete
    successfully with no metrics. Malformed persisted numeric values fail visibly,
    mark the eval run ``error``, and store only a sanitized error class/message.
    """

    run_id = eval_run_id or uuid.uuid4().hex
    observation_count = 0
    metric_count = 0
    _update_extraction_usage_trace_metadata(
        status="started",
        run_id=run_id,
        source_run_id=source_run_id,
        observation_count=observation_count,
        metric_count=metric_count,
    )

    create_eval_run(
        db_path,
        run_id=run_id,
        eval_type="extraction_usage_eval",
        pipeline_label=pipeline_label,
        params={"source_run_id": source_run_id, "max_observations": max_observations},
    )

    try:
        observations = _load_optional_extraction_usage_observations(
            db_path,
            source_run_id=source_run_id,
            limit=max_observations,
        )
        observation_count = len(observations)
        metrics = aggregate_extraction_usage_metrics(observations)
        for metric_name, metric_value in metrics.items():
            upsert_eval_metric(db_path, run_id, metric_name, metric_value)
            metric_count += 1

        mark_eval_run_complete(db_path, run_id)
        _update_extraction_usage_trace_metadata(
            status="complete",
            run_id=run_id,
            source_run_id=source_run_id,
            observation_count=observation_count,
            metric_count=metric_count,
        )
        return run_id
    except Exception as exc:
        mark_eval_run_error(db_path, run_id, _sanitize_error(exc))
        _update_extraction_usage_trace_metadata(
            status="error",
            run_id=run_id,
            source_run_id=source_run_id,
            observation_count=observation_count,
            metric_count=metric_count,
            error_class=exc.__class__.__name__,
        )
        raise


def _load_optional_extraction_usage_observations(db_path: str, *, source_run_id: str, limit: int):
    try:
        return list_extraction_usage_observations(db_path, run_id=source_run_id, limit=limit)
    except sqlite3.OperationalError as exc:
        if "extraction_usage_observations" in str(exc) and "no such table" in str(exc).lower():
            return []
        raise


def _update_extraction_usage_trace_metadata(
    *,
    status: str,
    run_id: str,
    source_run_id: str,
    observation_count: int,
    metric_count: int,
    error_class: str | None = None,
) -> None:
    """Attach bounded extraction-usage eval metadata to the current trace.

    Metadata is limited to identifiers, status, and counts. It never includes raw
    prompts, page text, provider payloads, document paths, images, PDFs, secrets,
    or raw exception strings.
    """

    safe_update_current_trace(
        tags=["evaluation", "extraction_usage_eval"],
        metadata={
            "boundary": "evaluation",
            "status": status,
            "eval_type": "extraction_usage_eval",
            "run_id": run_id,
            "source_run_id": source_run_id,
            "observation_count": observation_count,
            "metric_count": metric_count,
            "error_class": error_class,
        },
        allowed_metadata_keys=_EXTRACTION_USAGE_TRACE_ALLOWED_KEYS,
    )


def _sanitize_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    message = _ERROR_SANITIZE_RE.sub("", message)
    return message[:500]
