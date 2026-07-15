"""Provider-free aggregation runner for extraction usage observations.

This helper turns bounded ``extraction_usage_observations`` rows into dashboard-
readable ``eval_metrics``. It intentionally imports no provider SDKs, RAGAS, or
Streamlit; the source rows already contain the only allowed usage telemetry.
"""

from __future__ import annotations

import sqlite3
import uuid

from src.eval.extraction_eval_runner import (
    SourceExtractionRunIncompleteError,
    load_complete_extraction_source_run,
)
from src.eval.operational_metrics import aggregate_extraction_usage_metrics
from src.eval.repository import (
    begin_eval_run,
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
        "reason_code",
    }
)
_EXTRACTION_USAGE_EVAL_ERROR_REASON = "extraction_usage_eval_error"


class ExtractionUsageEvalError(RuntimeError):
    """Raised when usage aggregation fails without exposing persisted values."""

    reason_code = _EXTRACTION_USAGE_EVAL_ERROR_REASON

    def __init__(self) -> None:
        super().__init__(self.reason_code)


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
    mark the eval run ``error``, and store only a stable bounded reason code.
    """

    run_id = eval_run_id or uuid.uuid4().hex
    if isinstance(max_observations, bool) or not isinstance(max_observations, int) or not 1 <= max_observations <= 1_000_000:
        raise ValueError("max_observations_invalid")
    observation_count = 0
    metric_count = 0
    _update_extraction_usage_trace_metadata(
        status="started",
        run_id=run_id,
        source_run_id=source_run_id,
        observation_count=observation_count,
        metric_count=metric_count,
    )

    begin_eval_run(
        db_path,
        run_id=run_id,
        eval_type="extraction_usage_eval",
        pipeline_label=pipeline_label,
        params={"source_run_id": source_run_id, "max_observations": max_observations},
    )

    try:
        if load_complete_extraction_source_run(db_path, source_run_id) is None:
            raise SourceExtractionRunIncompleteError()
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
        reason_code = (
            exc.reason_code
            if isinstance(exc, SourceExtractionRunIncompleteError)
            else _EXTRACTION_USAGE_EVAL_ERROR_REASON
        )
        mark_eval_run_error(db_path, run_id, reason_code)
        _update_extraction_usage_trace_metadata(
            status="error",
            run_id=run_id,
            source_run_id=source_run_id,
            observation_count=observation_count,
            metric_count=metric_count,
            error_class=exc.__class__.__name__,
            reason_code=reason_code,
        )
        if isinstance(exc, SourceExtractionRunIncompleteError):
            raise
        raise ExtractionUsageEvalError() from None


def _load_optional_extraction_usage_observations(db_path: str, *, source_run_id: str, limit: int):
    try:
        rows = list_extraction_usage_observations(db_path, run_id=source_run_id, limit=limit + 1)
        if len(rows) > limit:
            raise ValueError("extraction_usage_observations_truncated")
        return rows
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
    reason_code: str | None = None,
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
            "reason_code": reason_code,
        },
        allowed_metadata_keys=_EXTRACTION_USAGE_TRACE_ALLOWED_KEYS,
    )
