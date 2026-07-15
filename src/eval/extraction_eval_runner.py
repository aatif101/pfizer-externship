"""Provider-free extraction eval runner.

Turns ``extraction_history`` rows plus ``gold_extraction_labels`` into
per-field and macro precision/recall/F1 ``eval_metrics`` for a given
extraction run. Intentionally imports no provider SDKs, RAGAS, or Streamlit.
"""

from __future__ import annotations

from datetime import datetime
import math
import re
import sqlite3
import uuid

from src.extraction.models import ExtractionRunSummary
from src.extraction.repository import ExtractionRunError, get_complete_extraction_run
from src.eval.extraction_metrics import (
    compute_extraction_field_scores,
    compute_macro_averages,
)
from src.eval.repository import (
    ExtractionUsageObservationRow,
    begin_eval_run,
    list_extraction_usage_observations,
    list_gold_extraction_labels,
    list_predicted_extractions_for_run,
    mark_eval_run_complete,
    mark_eval_run_error,
    set_eval_run_params,
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
        "reason_code",
        "pipeline_label",
        "source_run_status",
        "extraction_started_at",
        "extraction_completed_at",
        "extraction_run_date",
        "provider",
        "requested_model",
        "resolved_model",
        "pricing_model",
        "corpus_version",
        "manifest_hash",
        "expected_document_count",
        "succeeded_document_count",
        "failed_document_count",
        "usage_observation_count",
        "input_tokens",
        "candidate_tokens",
        "thought_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "cost_coverage",
    }
)
_SOURCE_INCOMPLETE_REASON = "source_extraction_run_incomplete"
_EVAL_ERROR_REASON = "extraction_eval_error"


class SourceExtractionRunIncompleteError(RuntimeError):
    """Raised when evaluation is requested for a non-reproducible source run."""

    reason_code = _SOURCE_INCOMPLETE_REASON

    def __init__(self) -> None:
        super().__init__(self.reason_code)


class ExtractionEvalError(RuntimeError):
    """Raised for a non-source lifecycle failure without exposing raw details."""

    reason_code = _EVAL_ERROR_REASON

    def __init__(self) -> None:
        super().__init__(self.reason_code)


@observe(name="extraction_eval_run")
def run_extraction_eval(
    db_path: str,
    *,
    source_run_id: str,
    eval_run_id: str | None = None,
    pipeline_label: str = "extraction_eval",
) -> str:
    """Compute extraction field metrics for one extraction run.

    Returns the eval run id. The source extraction run must first satisfy the
    strict manifest-bound all-success invariant. Once accepted, missing gold or
    prediction rows complete with no metrics. Other failures mark the eval run
    ``error`` with a stable reason code and never persist raw exception text.
    """

    safe_source_run_id = _bounded_identity(source_run_id, "source_run_id")
    safe_pipeline_label = _bounded_identity(pipeline_label, "pipeline_label")
    if safe_source_run_id is None or safe_pipeline_label is None:
        raise ValueError("extraction_eval_identity_invalid")
    source_run_id = safe_source_run_id
    pipeline_label = safe_pipeline_label
    run_id = (
        _bounded_identity(eval_run_id, "eval_run_id")
        if eval_run_id is not None
        else uuid.uuid4().hex
    )
    if run_id is None:
        raise ValueError("extraction_eval_identity_invalid")
    gold_count = 0
    pred_count = 0
    metric_count = 0
    source_provenance: dict[str, object] | None = None
    _update_trace_metadata(
        status="started",
        run_id=run_id,
        source_run_id=source_run_id,
        gold_count=gold_count,
        pred_count=pred_count,
        metric_count=metric_count,
    )

    base_params = {
        "pipeline_label": pipeline_label,
        "source_run_id": source_run_id,
    }
    begin_eval_run(
        db_path,
        run_id=run_id,
        eval_type="extraction_eval",
        pipeline_label=pipeline_label,
        params=base_params,
    )

    try:
        source_run = load_complete_extraction_source_run(db_path, source_run_id)
        if source_run is None:
            raise SourceExtractionRunIncompleteError()

        usage_rows = _load_optional_extraction_usage_observations(db_path, source_run_id)
        source_provenance = _build_source_provenance(
            source_run,
            usage_rows,
            pipeline_label=pipeline_label,
        )
        set_eval_run_params(
            db_path,
            run_id,
            source_provenance,
            pipeline_label=pipeline_label,
        )
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
                provenance=source_provenance,
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
            provenance=source_provenance,
        )
        return run_id

    except Exception as exc:
        reason_code = _eval_error_reason(exc)
        error_params = source_provenance or base_params
        set_eval_run_params(
            db_path,
            run_id,
            error_params,
            pipeline_label=pipeline_label,
        )
        mark_eval_run_error(db_path, run_id, reason_code)
        _update_trace_metadata(
            status="error",
            run_id=run_id,
            source_run_id=source_run_id,
            gold_count=gold_count,
            pred_count=pred_count,
            metric_count=metric_count,
            error_class=exc.__class__.__name__,
            reason_code=reason_code,
            provenance=source_provenance,
        )
        if isinstance(exc, SourceExtractionRunIncompleteError):
            raise
        raise ExtractionEvalError() from None


def load_complete_extraction_source_run(db_path: str, source_run_id: str) -> ExtractionRunSummary | None:
    """Return only a strict, manifest-bound, reproducible source run."""

    try:
        source_run = get_complete_extraction_run(db_path, source_run_id)
        if source_run is None or not _has_reproducibility_provenance(source_run):
            return None
        return source_run
    except ExtractionRunError:
        return None
    except sqlite3.OperationalError as exc:
        if "extraction_runs" in str(exc) and "no such table" in str(exc).lower():
            return None
        raise


def _has_reproducibility_provenance(source_run: ExtractionRunSummary) -> bool:
    """Require the manifest-bound identities/timestamps promised by current runs."""

    try:
        required_values = (
            _bounded_identity(source_run.provider, "provider"),
            _bounded_identity(source_run.requested_model, "requested_model"),
            _bounded_identity(source_run.resolved_model, "resolved_model"),
            _bounded_identity(source_run.corpus_version, "corpus_version"),
            _bounded_manifest_hash(source_run.manifest_hash),
            _bounded_timestamp(source_run.started_at, "extraction_started_at"),
            _bounded_timestamp(source_run.completed_at, "extraction_completed_at"),
        )
    except ValueError:
        return False
    return all(value is not None for value in required_values)


def _load_optional_extraction_usage_observations(
    db_path: str,
    source_run_id: str,
) -> list[ExtractionUsageObservationRow]:
    try:
        rows = list_extraction_usage_observations(
            db_path,
            run_id=source_run_id,
            limit=1_000_001,
        )
        if len(rows) > 1_000_000:
            raise ValueError("extraction_usage_observations_truncated")
        return rows
    except sqlite3.OperationalError as exc:
        if "extraction_usage_observations" in str(exc) and "no such table" in str(exc).lower():
            return []
        raise


def _build_source_provenance(
    source_run: ExtractionRunSummary,
    usage_rows: list[ExtractionUsageObservationRow],
    *,
    pipeline_label: str,
) -> dict[str, object]:
    started_at = _bounded_timestamp(source_run.started_at, "extraction_started_at")
    completed_at = _bounded_timestamp(source_run.completed_at, "extraction_completed_at")
    _validate_usage_model_consistency(source_run, usage_rows)
    pricing_models = sorted(
        {
            model
            for row in usage_rows
            if (model := _bounded_identity(row.pricing_model, "pricing_model")) is not None
        }
    )
    if len(pricing_models) > 8:
        raise ValueError("pricing_model_count_invalid")
    token_totals = {
        "input_tokens": _sum_optional_nonnegative_int(usage_rows, "input_tokens"),
        "candidate_tokens": _sum_optional_nonnegative_int(usage_rows, "output_tokens"),
        "thought_tokens": _sum_optional_nonnegative_int(usage_rows, "thought_tokens"),
        "total_tokens": _sum_optional_nonnegative_int(usage_rows, "total_tokens"),
    }
    return {
        "source_run_id": source_run.run_id,
        "source_run_status": source_run.status.value,
        "extraction_started_at": started_at,
        "extraction_completed_at": completed_at,
        "extraction_run_date": _timestamp_date(started_at),
        "provider": _bounded_identity(source_run.provider, "provider"),
        "requested_model": _bounded_identity(source_run.requested_model, "requested_model"),
        "resolved_model": _bounded_identity(source_run.resolved_model, "resolved_model"),
        "pricing_model": pricing_models[0] if len(pricing_models) == 1 else None,
        "pricing_models": pricing_models,
        "corpus_version": _bounded_identity(source_run.corpus_version, "corpus_version"),
        "manifest_hash": _bounded_manifest_hash(source_run.manifest_hash),
        "expected_document_count": source_run.expected_document_count,
        "succeeded_document_count": source_run.succeeded_document_count,
        "failed_document_count": source_run.failed_document_count,
        "usage_observation_count": len(usage_rows),
        **token_totals,
        "estimated_cost_usd": _aggregate_estimated_cost(usage_rows),
        "cost_coverage": _cost_coverage(usage_rows),
        "pipeline_label": _bounded_identity(pipeline_label, "pipeline_label"),
    }


def _sum_optional_nonnegative_int(
    rows: list[ExtractionUsageObservationRow],
    field_name: str,
) -> int | None:
    values: list[int] = []
    for row in rows:
        value = getattr(row, field_name)
        if value is None:
            continue
        if isinstance(value, bool):
            raise ValueError(f"{field_name}_invalid")
        try:
            numeric_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}_invalid") from exc
        if numeric_value < 0 or isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{field_name}_invalid")
        values.append(numeric_value)
    return sum(values) if values else None


def _aggregate_estimated_cost(rows: list[ExtractionUsageObservationRow]) -> float | None:
    costs: list[float] = []
    has_unpriced_billable_usage = False
    for row in rows:
        attempted = _usage_row_represents_provider_attempt(row)
        if row.estimated_cost_usd is None:
            has_unpriced_billable_usage = has_unpriced_billable_usage or attempted
            continue
        if isinstance(row.estimated_cost_usd, bool):
            raise ValueError("estimated_cost_usd_invalid")
        cost = float(row.estimated_cost_usd)
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("estimated_cost_usd_invalid")
        costs.append(cost)
    if has_unpriced_billable_usage:
        return None
    return float(sum(costs)) if costs else None


def _cost_coverage(rows: list[ExtractionUsageObservationRow]) -> float | None:
    attempted_rows = [row for row in rows if _usage_row_represents_provider_attempt(row)]
    if not attempted_rows:
        return None
    known = sum(row.estimated_cost_usd is not None for row in attempted_rows)
    return known / len(attempted_rows)


def _usage_row_represents_provider_attempt(row: ExtractionUsageObservationRow) -> bool:
    if row.status == "skipped":
        return False
    return any(
        value is not None
        for value in (
            row.provider,
            row.model,
            row.requested_model,
            row.resolved_model,
            row.latency_ms,
            row.input_tokens,
            row.output_tokens,
            row.thought_tokens,
            row.total_tokens,
            row.estimated_cost_usd,
        )
    ) or row.status in {"observed", "complete", "needs_review", "abstained", "error"}


def _validate_usage_model_consistency(
    source_run: ExtractionRunSummary,
    rows: list[ExtractionUsageObservationRow],
) -> None:
    primary_rows = [row for row in rows if row.stage == "text_extraction" and row.status != "skipped"]
    if not primary_rows:
        primary_rows = [row for row in rows if row.stage == "visual_fallback" and row.status != "skipped"]

    expected = {
        "provider": _bounded_identity(source_run.provider, "provider"),
        "requested_model": _bounded_identity(source_run.requested_model, "requested_model"),
        "resolved_model": _bounded_identity(source_run.resolved_model, "resolved_model"),
    }
    for field_name, expected_value in expected.items():
        observed = {
            value
            for row in primary_rows
            if (value := _bounded_identity(getattr(row, field_name), field_name)) is not None
        }
        if any(value != expected_value for value in observed):
            raise ValueError("extraction_usage_model_mismatch")


def _bounded_identity(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name}_invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > 255:
        raise ValueError(f"{field_name}_invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"{field_name}_invalid")
    return normalized


def _bounded_manifest_hash(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise ValueError("manifest_hash_invalid")
    return value.lower()


def _bounded_timestamp(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError(f"{field_name}_invalid")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name}_invalid") from exc
    return value


def _timestamp_date(value: str | None) -> str | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()


def _eval_error_reason(exc: Exception) -> str:
    reason_code = getattr(exc, "reason_code", None)
    if isinstance(reason_code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,95}", reason_code):
        return reason_code
    return _EVAL_ERROR_REASON


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
    reason_code: str | None = None,
    provenance: dict[str, object] | None = None,
) -> None:
    """Attach bounded extraction eval metadata to the current trace.

    Metadata is limited to identifiers, lifecycle status/counts, bounded model
    and corpus provenance, and numeric usage/cost totals. It never includes raw
    prompts, page text, provider payloads, document paths, images, PDFs, secrets,
    or raw exception strings.
    """

    metadata: dict[str, object | None] = {
        "boundary": "evaluation",
        "status": status,
        "eval_type": "extraction_eval",
        "run_id": run_id,
        "source_run_id": source_run_id,
        "gold_count": gold_count,
        "pred_count": pred_count,
        "metric_count": metric_count,
        "error_class": error_class,
        "reason_code": reason_code,
    }
    if provenance is not None:
        metadata.update(
            {
                key: value
                for key, value in provenance.items()
                if key in _EXTRACTION_EVAL_TRACE_ALLOWED_KEYS and key != "pricing_models"
            }
        )

    safe_update_current_trace(
        tags=["evaluation", "extraction_eval"],
        metadata=metadata,
        allowed_metadata_keys=_EXTRACTION_EVAL_TRACE_ALLOWED_KEYS,
    )
