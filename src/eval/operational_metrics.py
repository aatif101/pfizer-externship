"""Pure aggregation helpers for optional evaluation/operational metrics.

The functions in this module are intentionally provider-free and DB-free. They
accept bounded observation rows (for example ``RAGEvalObservationRow`` from
``src.eval.repository``) or simple mappings with the same numeric keys, then
return deterministic metric-name/value pairs suitable for ``eval_metrics``.

Null or missing source values are treated as absent. Malformed non-null numeric
values raise ``ValueError`` so upstream integrations fail visibly instead of
silently producing misleading aggregates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

LATENCY_AVG_MS = "retrieval.latency_ms.avg"
LATENCY_P50_MS = "retrieval.latency_ms.p50"
LATENCY_P95_MS = "retrieval.latency_ms.p95"
COST_TOTAL_USD = "retrieval.cost_usd.total"
COST_AVG_USD = "retrieval.cost_usd.avg"
INPUT_TOKENS_TOTAL = "retrieval.tokens.input.total"
OUTPUT_TOKENS_TOTAL = "retrieval.tokens.output.total"
TOTAL_TOKENS_TOTAL = "retrieval.tokens.total.total"
FAITHFULNESS_AVG = "ragas.faithfulness.avg"
ANSWER_RELEVANCY_AVG = "ragas.answer_relevancy.avg"

_NUMERIC_FIELDS = {
    "latency_ms",
    "cost_usd",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "faithfulness",
    "answer_relevancy",
}


def aggregate_observation_metrics(observations: Iterable[Any]) -> dict[str, float]:
    """Aggregate optional metric values from bounded observation rows.

    Returns an ordered ``dict`` of metric name to numeric value. Empty inputs, all
    null values, or missing fields emit no metric for that family rather than a
    misleading zero.
    """

    rows = list(observations)
    metrics: dict[str, float] = {}

    latency_values = _numeric_values(rows, "latency_ms")
    if latency_values:
        metrics[LATENCY_AVG_MS] = _average(latency_values)
        metrics[LATENCY_P50_MS] = _percentile(latency_values, 50)
        metrics[LATENCY_P95_MS] = _percentile(latency_values, 95)

    cost_values = _numeric_values(rows, "cost_usd")
    if cost_values:
        metrics[COST_TOTAL_USD] = float(sum(cost_values))
        metrics[COST_AVG_USD] = _average(cost_values)

    input_token_values = _numeric_values(rows, "input_tokens")
    if input_token_values:
        metrics[INPUT_TOKENS_TOTAL] = float(sum(input_token_values))

    output_token_values = _numeric_values(rows, "output_tokens")
    if output_token_values:
        metrics[OUTPUT_TOKENS_TOTAL] = float(sum(output_token_values))

    total_token_values = _numeric_values(rows, "total_tokens")
    if total_token_values:
        metrics[TOTAL_TOKENS_TOTAL] = float(sum(total_token_values))

    faithfulness_values = _numeric_values(rows, "faithfulness")
    if faithfulness_values:
        metrics[FAITHFULNESS_AVG] = _average(faithfulness_values)

    answer_relevancy_values = _numeric_values(rows, "answer_relevancy")
    if answer_relevancy_values:
        metrics[ANSWER_RELEVANCY_AVG] = _average(answer_relevancy_values)

    return metrics


def aggregate_latency_metrics(observations: Iterable[Any]) -> dict[str, float]:
    """Return latency average/p50/p95 metrics from observation-like rows."""

    rows = list(observations)
    values = _numeric_values(rows, "latency_ms")
    if not values:
        return {}
    return {
        LATENCY_AVG_MS: _average(values),
        LATENCY_P50_MS: _percentile(values, 50),
        LATENCY_P95_MS: _percentile(values, 95),
    }


def aggregate_cost_metrics(observations: Iterable[Any]) -> dict[str, float]:
    """Return cost total/average metrics when cost values are present."""

    values = _numeric_values(list(observations), "cost_usd")
    if not values:
        return {}
    return {COST_TOTAL_USD: float(sum(values)), COST_AVG_USD: _average(values)}


def aggregate_token_metrics(observations: Iterable[Any]) -> dict[str, float]:
    """Return token sum metrics for token fields that contain values."""

    rows = list(observations)
    metrics: dict[str, float] = {}
    field_to_metric = {
        "input_tokens": INPUT_TOKENS_TOTAL,
        "output_tokens": OUTPUT_TOKENS_TOTAL,
        "total_tokens": TOTAL_TOKENS_TOTAL,
    }
    for field_name, metric_name in field_to_metric.items():
        values = _numeric_values(rows, field_name)
        if values:
            metrics[metric_name] = float(sum(values))
    return metrics


def aggregate_quality_metrics(observations: Iterable[Any]) -> dict[str, float]:
    """Return faithfulness/relevancy averages when precomputed scores exist."""

    rows = list(observations)
    metrics: dict[str, float] = {}
    faithfulness_values = _numeric_values(rows, "faithfulness")
    if faithfulness_values:
        metrics[FAITHFULNESS_AVG] = _average(faithfulness_values)
    relevancy_values = _numeric_values(rows, "answer_relevancy")
    if relevancy_values:
        metrics[ANSWER_RELEVANCY_AVG] = _average(relevancy_values)
    return metrics


def _numeric_values(rows: list[Any], field_name: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value, present = _get_field(row, field_name)
        if not present or value is None:
            continue
        values.append(_coerce_number(value, field_name))
    return values


def _get_field(row: Any, field_name: str) -> tuple[Any, bool]:
    if isinstance(row, Mapping):
        if field_name not in row:
            return None, False
        return row[field_name], True
    if hasattr(row, field_name):
        return getattr(row, field_name), True
    return None, False


def _coerce_number(value: Any, field_name: str) -> float:
    if field_name not in _NUMERIC_FIELDS:
        raise ValueError(f"unsupported numeric field: {field_name}")
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric or None")
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
    else:
        raise ValueError(f"{field_name} must be numeric or None")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite")
    return number


def _average(values: list[float]) -> float:
    return float(sum(values) / len(values))


def _percentile(values: list[float], percentile: float) -> float:
    """Compute a deterministic linear-interpolated percentile."""

    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be between 0 and 100")

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    rank = (percentile / 100) * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return float(lower + (upper - lower) * fraction)
