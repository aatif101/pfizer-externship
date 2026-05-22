"""Evaluation dashboard adapter + Streamlit renderer.

This module is intentionally credential-free and read-only: it only queries the
SQLite evaluation tables (eval_runs + eval_metrics) to provide an evaluator-
facing UI for inspection.

Goals:
- Safe empty states (missing DB, missing tables).
- Avoid heavy recomputation: no evaluation runs are created here.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import asdict
from typing import Any

import streamlit as st

from src.dashboard.ui import (
    format_datetimeish,
    format_float,
    format_percent,
    render_empty_state,
    render_tab_header,
)
from src.eval.repository import EvalMetricRow, EvalRunRow, list_eval_metrics, list_eval_runs


_RUN_TABLE_COLUMNS: tuple[str, ...] = (
    "run_id",
    "eval_type",
    "status",
    "created_at",
    "completed_at",
    "pipeline_label",
    "error_reason",
)

_RATIO_METRIC_TOKENS: tuple[str, ...] = (
    "f1",
    "precision",
    "recall",
    "accuracy",
    "faithfulness",
    "answer_relevancy",
    "answer_relevance",
    "context_recall",
    "context_precision",
    "hit_rate",
    "recall_at",
    "precision_at",
)


def load_eval_runs(db_path: str, *, limit: int = 50) -> list[EvalRunRow]:
    """List eval runs, returning [] when the DB or tables are missing."""

    try:
        return list_eval_runs(db_path, limit=limit)
    except sqlite3.OperationalError as exc:
        if _is_missing_database_or_table(exc):
            return []
        raise


def load_eval_metrics(db_path: str, *, run_id: str) -> list[EvalMetricRow]:
    """List eval metrics for one run, returning [] when the tables are missing."""

    try:
        return list_eval_metrics(db_path, run_id)
    except sqlite3.OperationalError as exc:
        if _is_missing_database_or_table(exc):
            return []
        raise


def render_eval_tab(db_path: str | None = None) -> None:
    resolved_db_path = _resolve_db_path(db_path)

    render_tab_header(
        "Evaluation",
        "This tab is read-only: it surfaces persisted eval run history and metrics without triggering any evaluation computation.",
    )

    runs = load_eval_runs(resolved_db_path)
    if not runs:
        render_empty_state(
            "No evaluation runs yet. Run the evaluation CLI/tests to populate `eval_runs` and `eval_metrics` in the SQLite database.",
            caption=f"Looking for persisted runs in `{resolved_db_path}`.",
        )
        return

    st.subheader("Run history")
    st.dataframe(
        _run_table_rows(runs),
        hide_index=True,
        use_container_width=True,
    )

    run_by_id = {run.run_id: run for run in runs}
    run_id_options = [run.run_id for run in runs]

    primary_run_id = st.selectbox("Primary run", options=run_id_options)
    primary_run = run_by_id.get(primary_run_id)

    compare_same_type_only = st.checkbox("Only show compatible runs", value=True)
    include_any_types = st.checkbox("Allow comparing any eval_type", value=False)

    compatible_run_ids = [
        run_id
        for run_id, run in run_by_id.items()
        if run_id != primary_run_id
        and (
            (not compare_same_type_only)
            or (primary_run is None)
            or (run.eval_type == primary_run.eval_type)
        )
    ]

    compare_run_id = st.selectbox(
        "Compare to (optional)",
        options=["(none)", *sorted(compatible_run_ids)],
    )

    if compare_run_id != "(none)" and not include_any_types and primary_run is not None:
        compare_run = run_by_id.get(compare_run_id)
        if compare_run is not None and compare_run.eval_type != primary_run.eval_type:
            st.warning(
                "Selected runs have different eval_type values. Enable 'Allow comparing any eval_type' "
                "to compare across types."
            )
            compare_run_id = "(none)"

    primary_metrics = load_eval_metrics(resolved_db_path, run_id=primary_run_id)
    compare_metrics = (
        load_eval_metrics(resolved_db_path, run_id=compare_run_id)
        if compare_run_id != "(none)"
        else []
    )

    st.subheader("Metrics")
    _render_metrics_section(primary_metrics, compare_metrics)

    st.subheader("Compare runs")
    if compare_run_id == "(none)":
        st.info("Select a comparison run to see metric deltas.")
    else:
        show_only_changed = st.checkbox("Show only changed metrics", value=True)
        include_scoped = st.checkbox("Include per-scope metrics", value=False)
        st.dataframe(
            _build_comparison_rows(
                primary_metrics,
                compare_metrics,
                show_only_changed=show_only_changed,
                include_scoped=include_scoped,
            ),
            hide_index=True,
            use_container_width=True,
        )

    if primary_run and primary_run.error_reason:
        st.warning(f"Primary run error_reason: {primary_run.error_reason}")
    if compare_run_id != "(none)":
        compare_run = run_by_id.get(compare_run_id)
        if compare_run and compare_run.error_reason:
            st.warning(f"Comparison run error_reason: {compare_run.error_reason}")


def _resolve_db_path(db_path: str | None) -> str:
    if db_path:
        return db_path

    from src.config import get_settings

    return get_settings().db_path


def _run_table_rows(runs: list[EvalRunRow]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        row: dict[str, Any] = {}
        for column in _RUN_TABLE_COLUMNS:
            value = getattr(run, column)
            if column in {"created_at", "completed_at"}:
                row[column] = format_datetimeish(value)
            else:
                row[column] = value
        rows.append(row)
    return rows


def _render_metrics_section(primary: list[EvalMetricRow], compare: list[EvalMetricRow]) -> None:
    primary_global, primary_scoped = _split_metrics(primary)
    compare_global, compare_scoped = _split_metrics(compare)

    if not primary_global and not primary_scoped:
        st.info("No metrics are recorded for the selected run yet.")
        return

    st.markdown("**Global metrics**")
    st.dataframe(
        _format_global_metrics(primary_global, compare_global),
        hide_index=True,
        use_container_width=True,
    )

    if primary_scoped:
        with st.expander("Per-scope metrics", expanded=False):
            st.dataframe(
                _format_scoped_metrics(primary_scoped, compare_scoped),
                hide_index=True,
                use_container_width=True,
            )


def _split_metrics(metrics: list[EvalMetricRow]) -> tuple[list[EvalMetricRow], list[EvalMetricRow]]:
    global_metrics: list[EvalMetricRow] = []
    scoped_metrics: list[EvalMetricRow] = []
    for metric in metrics:
        if metric.scope_type is None and metric.scope_id is None:
            global_metrics.append(metric)
        else:
            scoped_metrics.append(metric)
    return global_metrics, scoped_metrics


def _format_global_metrics(primary: list[EvalMetricRow], compare: list[EvalMetricRow]) -> list[dict[str, Any]]:
    compare_lookup = {metric.metric_name: metric.metric_value for metric in compare}
    rows: list[dict[str, Any]] = []
    for metric in primary:
        metric_name = metric.metric_name
        a_value = metric.metric_value
        b_value = compare_lookup.get(metric_name)
        delta: float | None
        if a_value is None or b_value is None:
            delta = None
        else:
            delta = b_value - a_value

        rows.append(
            {
                "metric": metric_name,
                "value": _format_metric_value(metric_name, a_value),
                "compare_value": _format_metric_value(metric_name, b_value),
                "delta": _format_delta(metric_name, delta),
            }
        )
    return rows


def _format_scoped_metrics(primary: list[EvalMetricRow], compare: list[EvalMetricRow]) -> list[dict[str, Any]]:
    compare_lookup = {
        (metric.metric_name, metric.scope_type, metric.scope_id): metric.metric_value
        for metric in compare
    }

    rows: list[dict[str, Any]] = []
    for metric in primary:
        key = (metric.metric_name, metric.scope_type, metric.scope_id)
        metric_name = metric.metric_name
        a_value = metric.metric_value
        b_value = compare_lookup.get(key)
        delta: float | None
        if a_value is None or b_value is None:
            delta = None
        else:
            delta = b_value - a_value

        rows.append(
            {
                "scope_type": metric.scope_type,
                "scope_id": metric.scope_id,
                "metric": metric_name,
                "value": _format_metric_value(metric_name, a_value),
                "compare_value": _format_metric_value(metric_name, b_value),
                "delta": _format_delta(metric_name, delta),
            }
        )
    return rows


def _build_comparison_rows(
    primary: list[EvalMetricRow],
    compare: list[EvalMetricRow],
    *,
    show_only_changed: bool,
    include_scoped: bool,
) -> list[dict[str, Any]]:
    """Return comparison rows keyed by (metric_name, scope_type, scope_id).

    Includes blanks when one run lacks a metric; never raises on missing keys.
    """

    def metric_key(metric: EvalMetricRow) -> tuple[str, str | None, str | None]:
        return (metric.metric_name, metric.scope_type, metric.scope_id)

    primary_lookup = {metric_key(metric): metric.metric_value for metric in primary}
    compare_lookup = {metric_key(metric): metric.metric_value for metric in compare}

    all_keys = sorted(set(primary_lookup) | set(compare_lookup))

    rows: list[dict[str, Any]] = []
    for key in all_keys:
        metric_name, scope_type, scope_id = key
        if not include_scoped and (scope_type is not None or scope_id is not None):
            continue

        a_value = primary_lookup.get(key)
        b_value = compare_lookup.get(key)
        delta: float | None
        if a_value is None or b_value is None:
            delta = None
        else:
            delta = b_value - a_value

        changed = delta is not None and abs(delta) > 0
        if show_only_changed and not changed:
            continue

        rows.append(
            {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "metric": metric_name,
                "value_a": _format_metric_value(metric_name, a_value),
                "value_b": _format_metric_value(metric_name, b_value),
                "delta": _format_delta(metric_name, delta),
            }
        )

    return rows


def _format_metric_value(metric_name: str, value: float | None) -> str:
    if value is None:
        return ""

    if _is_ratio_metric(metric_name):
        return format_percent(value, digits=1, unknown="")

    return format_float(value, digits=3, unknown="")


def _format_delta(metric_name: str, delta: float | None) -> str:
    if delta is None:
        return ""

    if _is_ratio_metric(metric_name):
        return f"{delta:+.1%}"

    return f"{delta:+.3f}"


def _is_ratio_metric(metric_name: str) -> bool:
    lowered = metric_name.lower()
    return any(token in lowered for token in _RATIO_METRIC_TOKENS)


def _is_missing_database_or_table(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "no such table" in message or "unable to open database file" in message
