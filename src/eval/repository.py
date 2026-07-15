"""Evaluation repository helpers.

Goals:
- Streamlit rerun-safe (INSERT OR IGNORE / upsert semantics)
- Offline-safe: no provider/LLM imports
- Only parameterized SQL

This module builds on the canonical evaluation schema introduced in
`src/db/schema.py` (eval_runs + eval_metrics + gold_* tables).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from src.db.schema import _connect


_EXTRACTION_USAGE_STAGES = frozenset(
    {"extraction", "field_extraction", "text_extraction", "visual_fallback", "compliance_scoring"}
)
_EXTRACTION_USAGE_STATUSES = frozenset(
    {"observed", "complete", "needs_review", "abstained", "skipped", "error"}
)
_SAFE_REASON_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_MAX_USAGE_LIST_LIMIT = 1_000_001


@dataclass(frozen=True)
class EvalRunRow:
    run_id: str
    eval_type: str
    status: str
    created_at: str | None
    completed_at: str | None
    pipeline_label: str | None
    params_json: str | None
    error_reason: str | None


@dataclass(frozen=True)
class EvalMetricRow:
    run_id: str
    metric_name: str
    metric_value: float | None
    scope_type: str | None
    scope_id: str | None
    created_at: str | None


@dataclass(frozen=True)
class RAGEvalObservationRow:
    """Bounded RAG/eval observation metadata persisted without raw text.

    This row intentionally carries only identifiers, status, numeric operational
    metrics, numeric quality scores, and citation coordinates. It must not grow
    prompt, answer, context, snippet, page text, provider payload, image, or blob
    fields; schema tests enforce that no raw-text columns are present.
    """

    observation_id: int | None = None
    source_run_id: str | None = None
    query_id: str | None = None
    status: str = "observed"
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    cited_doc_id: str | None = None
    cited_page_num: int | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class ExtractionUsageObservationRow:
    """Bounded extraction usage telemetry persisted without raw document data.

    This row intentionally carries only run/document identifiers, extraction
    stage/model metadata, status, sanitized error reason, trace id, and numeric
    token/latency/cost fields. It must not store prompts, page text, provider
    payloads, images, PDFs, secrets, or local confidential paths.
    """

    observation_id: int | None = None
    run_id: str = ""
    doc_id: str = ""
    stage: str = "extraction"
    provider: str | None = None
    model: str | None = None
    requested_model: str | None = None
    resolved_model: str | None = None
    pricing_model: str | None = None
    status: str = "observed"
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    thought_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    trace_id: str | None = None
    error_reason: str | None = None
    created_at: str | None = None


def create_eval_run(
    db_path: str,
    run_id: str,
    eval_type: str,
    pipeline_label: str | None,
    params: dict[str, Any] | None,
) -> None:
    """Create an eval run row if it doesn't exist.

    Uses INSERT OR IGNORE to avoid Streamlit rerun duplication.
    """

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO eval_runs (
                run_id, eval_type, status, pipeline_label, params_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, eval_type, "running", pipeline_label, json.dumps(params or {}, sort_keys=True)),
        )
        conn.commit()
    finally:
        conn.close()


def begin_eval_run(
    db_path: str,
    *,
    run_id: str,
    eval_type: str,
    pipeline_label: str | None,
    params: dict[str, Any] | None,
) -> None:
    """Atomically begin or restart an eval run and clear all prior metrics.

    Reuse is allowed only for the same eval type. Parameters are replaced so a
    rerun can never publish metrics from one source under another source's stale
    provenance. Existing terminal state is reset to ``running`` before metrics
    are removed in the same transaction.
    """

    params_json = json.dumps(params or {}, sort_keys=True)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT eval_type FROM eval_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if existing is not None and existing[0] != eval_type:
            raise ValueError("eval_run_type_mismatch")
        if existing is None:
            conn.execute(
                """
                INSERT INTO eval_runs (run_id, eval_type, status, pipeline_label, params_json)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (run_id, eval_type, pipeline_label, params_json),
            )
        else:
            conn.execute(
                """
                UPDATE eval_runs
                SET status = 'running', completed_at = NULL, error_reason = NULL,
                    pipeline_label = ?, params_json = ?
                WHERE run_id = ?
                """,
                (pipeline_label, params_json, run_id),
            )
        conn.execute("DELETE FROM eval_metrics WHERE run_id = ?", (run_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_eval_run_params(
    db_path: str,
    run_id: str,
    params: dict[str, Any],
    *,
    pipeline_label: str | None = None,
) -> None:
    """Replace one eval run's bounded JSON parameters and current pipeline label."""

    params_json = json.dumps(params, sort_keys=True)
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            UPDATE eval_runs
            SET params_json = ?, pipeline_label = COALESCE(?, pipeline_label)
            WHERE run_id = ?
            """,
            (params_json, pipeline_label, run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("eval_run_not_found")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_eval_metrics(db_path: str, run_id: str) -> None:
    """Delete metrics for one eval run before recompute or terminal refusal."""

    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM eval_metrics WHERE run_id = ?", (run_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_eval_run_complete(db_path: str, run_id: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE eval_runs
            SET status = ?, completed_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                error_reason = NULL
            WHERE run_id = ?
            """,
            ("complete", run_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_eval_run_error(db_path: str, run_id: str, error_reason: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE eval_runs
            SET status = ?, completed_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                error_reason = ?
            WHERE run_id = ?
            """,
            ("error", error_reason, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_eval_metric_uniqueness(conn: sqlite3.Connection) -> None:
    """Ensure a unique index exists for metric upserts.

    The base schema shipped in T01 does not include a UNIQUE constraint on
    (run_id, metric_name, scope_type, scope_id). To keep migrations simple and
    allow deterministic upserts, we create a unique index if missing.

    This is idempotent and safe to call on every upsert.
    """

    # SQLite UNIQUE indexes treat NULL values as distinct, so two rows with
    # scope_type/scope_id NULL would still duplicate. Use COALESCE() to map
    # NULL -> '' so the uniqueness key behaves as expected for "global" metrics.
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_metrics_dedupe
        ON eval_metrics(run_id, metric_name, COALESCE(scope_type, ''), COALESCE(scope_id, ''))
        """
    )


def upsert_eval_metric(
    db_path: str,
    run_id: str,
    metric_name: str,
    metric_value: float | None,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> None:
    """Insert or update a metric row keyed by (run_id, metric_name, scope_*).

    Designed to be safe under Streamlit reruns: repeated calls with the same
    key overwrite metric_value rather than duplicating rows.
    """

    conn = _connect(db_path)
    try:
        _ensure_eval_metric_uniqueness(conn)
        conn.execute(
            """
            INSERT INTO eval_metrics (run_id, metric_name, metric_value, scope_type, scope_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id, metric_name, COALESCE(scope_type, ''), COALESCE(scope_id, ''))
            DO UPDATE SET metric_value = excluded.metric_value
            """,
            (run_id, metric_name, metric_value, scope_type, scope_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_eval_runs(db_path: str, limit: int = 50) -> list[EvalRunRow]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT run_id, eval_type, status, created_at, completed_at, pipeline_label, params_json, error_reason
            FROM eval_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return [
        EvalRunRow(
            run_id=row[0],
            eval_type=row[1],
            status=row[2],
            created_at=row[3],
            completed_at=row[4],
            pipeline_label=row[5],
            params_json=row[6],
            error_reason=row[7],
        )
        for row in rows
    ]


def list_eval_metrics(db_path: str, run_id: str) -> list[EvalMetricRow]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT run_id, metric_name, metric_value, scope_type, scope_id, created_at
            FROM eval_metrics
            WHERE run_id = ?
            ORDER BY metric_name ASC, scope_type ASC, scope_id ASC
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    return [
        EvalMetricRow(
            run_id=row[0],
            metric_name=row[1],
            metric_value=row[2],
            scope_type=row[3],
            scope_id=row[4],
            created_at=row[5],
        )
        for row in rows
    ]


def _coerce_nullable_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric or None")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric or None") from exc
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite or None")
    return numeric_value


def _coerce_nullable_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer or None")
    try:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized or not normalized.lstrip("+-").isdigit():
                raise ValueError
            return int(normalized)
        numeric_value = int(value)
        if value != numeric_value:
            raise ValueError
        return numeric_value
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be an integer or None") from exc


def _coerce_nullable_nonnegative_float(value: Any, field_name: str) -> float | None:
    numeric_value = _coerce_nullable_float(value, field_name)
    if numeric_value is not None and numeric_value < 0:
        raise ValueError(f"{field_name} must be nonnegative or None")
    return numeric_value


def _coerce_nullable_nonnegative_int(value: Any, field_name: str) -> int | None:
    numeric_value = _coerce_nullable_int(value, field_name)
    if numeric_value is not None and numeric_value < 0:
        raise ValueError(f"{field_name} must be nonnegative or None")
    return numeric_value


def _coerce_optional_model_identity(value: Any, field_name: str) -> str | None:
    """Return one bounded content-free model identity or reject it safely."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a bounded string or None")
    normalized = value.strip()
    if not normalized or len(normalized) > 255:
        raise ValueError(f"{field_name} must be a bounded string or None")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"{field_name} must be a bounded string or None")
    return normalized


def _coerce_required_identity(value: Any, field_name: str) -> str:
    normalized = _coerce_optional_model_identity(value, field_name)
    if normalized is None:
        raise ValueError(f"{field_name} must be a bounded string")
    return normalized


def _coerce_usage_enum(value: Any, field_name: str, allowed: frozenset[str]) -> str:
    normalized = _coerce_required_identity(value, field_name)
    if normalized not in allowed:
        raise ValueError(f"{field_name} is not an allowed value")
    return normalized


def _coerce_optional_reason_code(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _SAFE_REASON_CODE_RE.fullmatch(value) is None:
        raise ValueError("error_reason must be a stable reason code or None")
    return value


def _coerce_positive_usage_limit(value: Any) -> int:
    normalized = _coerce_nullable_int(value, "limit")
    if normalized is None or normalized <= 0 or normalized > _MAX_USAGE_LIST_LIMIT:
        raise ValueError(f"limit must be between 1 and {_MAX_USAGE_LIST_LIMIT}")
    return normalized


def insert_rag_eval_observation(db_path: str, observation: RAGEvalObservationRow) -> int:
    """Persist one bounded RAG/eval observation and return its row id.

    Numeric-like values are normalized before binding. Invalid numeric inputs
    raise ``ValueError`` before any row is written, preserving a predictable
    contract for future provider/trace integrations.
    """

    latency_ms = _coerce_nullable_float(observation.latency_ms, "latency_ms")
    input_tokens = _coerce_nullable_int(observation.input_tokens, "input_tokens")
    output_tokens = _coerce_nullable_int(observation.output_tokens, "output_tokens")
    total_tokens = _coerce_nullable_int(observation.total_tokens, "total_tokens")
    cost_usd = _coerce_nullable_float(observation.cost_usd, "cost_usd")
    faithfulness = _coerce_nullable_float(observation.faithfulness, "faithfulness")
    answer_relevancy = _coerce_nullable_float(observation.answer_relevancy, "answer_relevancy")
    cited_page_num = _coerce_nullable_int(observation.cited_page_num, "cited_page_num")

    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO rag_eval_observations (
                source_run_id, query_id, status, latency_ms, input_tokens,
                output_tokens, total_tokens, cost_usd, faithfulness,
                answer_relevancy, cited_doc_id, cited_page_num
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.source_run_id,
                observation.query_id,
                observation.status,
                latency_ms,
                input_tokens,
                output_tokens,
                total_tokens,
                cost_usd,
                faithfulness,
                answer_relevancy,
                observation.cited_doc_id,
                cited_page_num,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_rag_eval_observations(
    db_path: str,
    *,
    source_run_id: str | None = None,
    query_id: str | None = None,
    limit: int = 100,
) -> list[RAGEvalObservationRow]:
    """List bounded RAG/eval observations in deterministic insertion order."""

    clauses: list[str] = []
    params: list[Any] = []
    if source_run_id is not None:
        clauses.append("source_run_id = ?")
        params.append(source_run_id)
    if query_id is not None:
        clauses.append("query_id = ?")
        params.append(query_id)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(_coerce_nullable_int(limit, "limit") or 100)

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT observation_id, source_run_id, query_id, status, latency_ms,
                   input_tokens, output_tokens, total_tokens, cost_usd,
                   faithfulness, answer_relevancy, cited_doc_id, cited_page_num,
                   created_at
            FROM rag_eval_observations
            {where_sql}
            ORDER BY observation_id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    return [
        RAGEvalObservationRow(
            observation_id=row[0],
            source_run_id=row[1],
            query_id=row[2],
            status=row[3],
            latency_ms=row[4],
            input_tokens=row[5],
            output_tokens=row[6],
            total_tokens=row[7],
            cost_usd=row[8],
            faithfulness=row[9],
            answer_relevancy=row[10],
            cited_doc_id=row[11],
            cited_page_num=row[12],
            created_at=row[13],
        )
        for row in rows
    ]


def insert_extraction_usage_observation(db_path: str, observation: ExtractionUsageObservationRow) -> int:
    """Persist one bounded extraction usage observation and return its row id.

    Numeric-like values are normalized before binding. Invalid numeric inputs
    raise ``ValueError`` before opening a write transaction, so malformed
    telemetry cannot create partial rows. SQLite integrity/schema errors are
    rolled back and surfaced to callers as normal repository exceptions.
    """

    run_id = _coerce_required_identity(observation.run_id, "run_id")
    doc_id = _coerce_required_identity(observation.doc_id, "doc_id")
    stage = _coerce_usage_enum(observation.stage, "stage", _EXTRACTION_USAGE_STAGES)
    provider = _coerce_optional_model_identity(observation.provider, "provider")
    model = _coerce_optional_model_identity(observation.model, "model")
    requested_model = _coerce_optional_model_identity(observation.requested_model, "requested_model")
    resolved_model = _coerce_optional_model_identity(observation.resolved_model, "resolved_model")
    pricing_model = _coerce_optional_model_identity(observation.pricing_model, "pricing_model")
    status = _coerce_usage_enum(observation.status, "status", _EXTRACTION_USAGE_STATUSES)
    trace_id = _coerce_optional_model_identity(observation.trace_id, "trace_id")
    error_reason = _coerce_optional_reason_code(observation.error_reason)
    latency_ms = _coerce_nullable_nonnegative_float(observation.latency_ms, "latency_ms")
    input_tokens = _coerce_nullable_nonnegative_int(observation.input_tokens, "input_tokens")
    output_tokens = _coerce_nullable_nonnegative_int(observation.output_tokens, "output_tokens")
    thought_tokens = _coerce_nullable_nonnegative_int(observation.thought_tokens, "thought_tokens")
    total_tokens = _coerce_nullable_nonnegative_int(observation.total_tokens, "total_tokens")
    estimated_cost_usd = _coerce_nullable_nonnegative_float(
        observation.estimated_cost_usd,
        "estimated_cost_usd",
    )

    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO extraction_usage_observations (
                run_id, doc_id, stage, provider, model, requested_model,
                resolved_model, pricing_model, status, latency_ms, input_tokens,
                output_tokens, thought_tokens, total_tokens, estimated_cost_usd,
                trace_id, error_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                doc_id,
                stage,
                provider,
                model,
                requested_model,
                resolved_model,
                pricing_model,
                status,
                latency_ms,
                input_tokens,
                output_tokens,
                thought_tokens,
                total_tokens,
                estimated_cost_usd,
                trace_id,
                error_reason,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_extraction_usage_observations(
    db_path: str,
    *,
    run_id: str | None = None,
    doc_id: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[ExtractionUsageObservationRow]:
    """List bounded extraction usage observations by indexed filters."""

    clauses: list[str] = []
    params: list[Any] = []
    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)
    if doc_id is not None:
        clauses.append("doc_id = ?")
        params.append(doc_id)
    if stage is not None:
        clauses.append("stage = ?")
        params.append(stage)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(_coerce_positive_usage_limit(limit))

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT observation_id, run_id, doc_id, stage, provider, model,
                   requested_model, resolved_model, pricing_model, status,
                   latency_ms, input_tokens, output_tokens, thought_tokens,
                   total_tokens, estimated_cost_usd, trace_id, error_reason,
                   created_at
            FROM extraction_usage_observations
            {where_sql}
            ORDER BY observation_id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    return [
        ExtractionUsageObservationRow(
            observation_id=row[0],
            run_id=row[1],
            doc_id=row[2],
            stage=row[3],
            provider=row[4],
            model=row[5],
            requested_model=row[6],
            resolved_model=row[7],
            pricing_model=row[8],
            status=row[9],
            latency_ms=row[10],
            input_tokens=row[11],
            output_tokens=row[12],
            thought_tokens=row[13],
            total_tokens=row[14],
            estimated_cost_usd=row[15],
            trace_id=row[16],
            error_reason=row[17],
            created_at=row[18],
        )
        for row in rows
    ]


def list_gold_extraction_labels(db_path: str) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT doc_id, field_name, expected_value, normalized_value, source_page, created_at
            FROM gold_extraction_labels
            ORDER BY doc_id ASC, field_name ASC
            """
        ).fetchall()
    finally:
        conn.close()

    columns = ["doc_id", "field_name", "expected_value", "normalized_value", "source_page", "created_at"]
    return [dict(zip(columns, row)) for row in rows]


def list_predicted_extractions(db_path: str) -> list[dict[str, Any]]:
    """List predicted extraction rows for offline evaluation.

    Returns dict rows with: doc_id, field_name, normalized_value, review_state.

    Notes:
    - This intentionally reads from the canonical `extractions` table.
    - `normalized_value` is expected to already be persisted by the extraction
      pipeline; metric code may re-normalize as a safety belt.
    """

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT doc_id, field_name, normalized_value, review_state
            FROM extractions
            ORDER BY doc_id ASC, field_name ASC
            """
        ).fetchall()
    finally:
        conn.close()

    columns = ["doc_id", "field_name", "normalized_value", "review_state"]
    return [dict(zip(columns, row)) for row in rows]


def list_predicted_extractions_for_run(db_path: str, run_id: str) -> list[dict[str, Any]]:
    """List predicted extraction rows for a specific extraction run.

    Returns dict rows with: doc_id, field_name, normalized_value, review_state.
    This intentionally reads only from additive `extraction_history` rows and
    does not fall back to latest-write `extractions` rows when a run is missing.
    """

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT doc_id, field_name, normalized_value, review_state
            FROM extraction_history
            WHERE run_id = ?
            ORDER BY doc_id ASC, field_name ASC
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    columns = ["doc_id", "field_name", "normalized_value", "review_state"]
    return [dict(zip(columns, row)) for row in rows]


def list_gold_retrieval_queries(db_path: str) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT query_id, query_text, notes, created_at
            FROM gold_retrieval_queries
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    columns = ["query_id", "query_text", "notes", "created_at"]
    return [dict(zip(columns, row)) for row in rows]


def list_gold_retrieval_targets(db_path: str, query_id: str) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT query_id, doc_id, page_num, created_at
            FROM gold_retrieval_targets
            WHERE query_id = ?
            ORDER BY doc_id ASC, page_num ASC
            """,
            (query_id,),
        ).fetchall()
    finally:
        conn.close()

    columns = ["query_id", "doc_id", "page_num", "created_at"]
    return [dict(zip(columns, row)) for row in rows]


def get_latest_retrieval_index_run_id(db_path: str) -> str | None:
    """Return the latest retrieval_index_runs.run_id, if any.

    The retrieval subsystem provides richer DTOs, but evaluation needs a tiny,
    provider-free helper to locate the currently active index run.
    """

    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT run_id
            FROM retrieval_index_runs
            ORDER BY built_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()

    return str(row[0]) if row is not None else None


def list_retrieval_index_pages(db_path: str, run_id: str) -> list[dict[str, Any]]:
    """List retrieval_index_pages rows for one run in deterministic order."""

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT doc_id, page_num, display_page_num, filename, run_id
            FROM retrieval_index_pages
            WHERE run_id = ?
            ORDER BY doc_id ASC, page_num ASC
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    columns = ["doc_id", "page_num", "display_page_num", "filename", "run_id"]
    return [dict(zip(columns, row)) for row in rows]
