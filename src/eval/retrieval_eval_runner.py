"""Runner that computes retrieval eval metrics and persists them to SQLite.

This module is provider-free (no LLM / external APIs). It evaluates the current
retrieval index against the gold query set in `gold_retrieval_*` tables.

Persisted output:
- One row in `eval_runs` (eval_type = "retrieval_eval")
- Rows in `eval_metrics` for:
  - global summary metrics: retrieval.recall@K, retrieval.citation_accuracy@K
  - per-query metrics: retrieval.recall@K, retrieval.citation_accuracy@K

Citation accuracy uses the top-k retrieved hits as "citations" for now.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass

from src.eval.operational_metrics import (
    aggregate_cost_metrics,
    aggregate_latency_metrics,
    aggregate_quality_metrics,
    aggregate_token_metrics,
)
from src.eval.repository import (
    create_eval_run,
    get_latest_retrieval_index_run_id,
    list_gold_retrieval_queries,
    list_gold_retrieval_targets,
    list_rag_eval_observations,
    mark_eval_run_complete,
    mark_eval_run_error,
    upsert_eval_metric,
)
from src.eval.retrieval_metrics import compute_page_level_citation_accuracy, compute_retrieval_recall_at_k
from src.retrieval.retriever import retrieve_evidence


@dataclass(frozen=True)
class RetrievalEvalConfig:
    k_values: tuple[int, ...] = (5, 10)
    pipeline_label: str | None = "retrieval_eval"


_ERROR_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 _.:\-/#]+")


def run_retrieval_eval(
    db_path: str,
    *,
    k_values: list[int] | tuple[int, ...] = (5, 10),
    include_latency_cost: bool = False,
    include_ragas: bool = False,
) -> str:
    """Run retrieval evaluation and persist an eval_run + metrics.

    Returns the created run_id.

    Empty-state behavior:
    - If there is no retrieval index run or no gold queries, the run is marked
      complete but metrics are not written.
    """

    run_id = uuid.uuid4().hex
    k_tuple = tuple(int(k) for k in k_values)
    retrieval_run_id = get_latest_retrieval_index_run_id(db_path)

    create_eval_run(
        db_path,
        run_id=run_id,
        eval_type="retrieval_eval",
        pipeline_label="retrieval_eval",
        params={"k_values": list(k_tuple), "retrieval_run_id": retrieval_run_id},
    )

    try:
        if retrieval_run_id is None:
            mark_eval_run_complete(db_path, run_id)
            return run_id

        gold_queries = list_gold_retrieval_queries(db_path)
        if not gold_queries:
            mark_eval_run_complete(db_path, run_id)
            return run_id

        per_query: list[tuple[str, list[tuple[str, int]], list[tuple[str, int]]]] = []
        for query in gold_queries:
            query_id = str(query["query_id"])
            query_text = str(query["query_text"])
            targets = list_gold_retrieval_targets(db_path, query_id)
            target_pairs = [(str(row["doc_id"]), int(row["page_num"])) for row in targets]

            max_k = max(k_tuple) if k_tuple else 10
            retrieval_result = retrieve_evidence(db_path, query_text, top_k=max_k)
            retrieved_pairs = [(hit.doc_id, int(hit.page_num)) for hit in retrieval_result.hits]
            per_query.append((query_id, target_pairs, retrieved_pairs))

        gold_by_query = {qid: targets for qid, targets, _retrieved in per_query}

        for k in k_tuple:
            retrieved_by_query = {
                qid: [(doc_id, page_num, 1.0) for doc_id, page_num in retrieved[:k]]
                for qid, _targets, retrieved in per_query
            }
            recall_result = compute_retrieval_recall_at_k(gold_by_query, retrieved_by_query, k=k)

            cited_by_query = {qid: retrieved[:k] for qid, _targets, retrieved in per_query}
            citation_result = compute_page_level_citation_accuracy(gold_by_query, cited_by_query)

            upsert_eval_metric(db_path, run_id, f"retrieval.recall@{k}", recall_result.macro_recall)
            upsert_eval_metric(
                db_path,
                run_id,
                f"retrieval.citation_accuracy@{k}",
                float(citation_result["macro_accuracy"]),
            )

            for query_id in gold_by_query.keys():
                upsert_eval_metric(
                    db_path,
                    run_id,
                    f"retrieval.recall@{k}",
                    float(recall_result.per_query_recall.get(query_id, 0.0)),
                    scope_type="query",
                    scope_id=query_id,
                )
                upsert_eval_metric(
                    db_path,
                    run_id,
                    f"retrieval.citation_accuracy@{k}",
                    float(citation_result["per_query_accuracy"].get(query_id, 0.0)),
                    scope_type="query",
                    scope_id=query_id,
                )

        if include_latency_cost or include_ragas:
            _maybe_persist_optional_rag_metrics(
                db_path,
                run_id,
                source_run_id=retrieval_run_id,
                include_latency_cost=include_latency_cost,
                include_ragas=include_ragas,
            )

        mark_eval_run_complete(db_path, run_id)
        return run_id
    except Exception as exc:
        mark_eval_run_error(db_path, run_id, _sanitize_error(exc))
        raise


def _maybe_persist_optional_rag_metrics(
    db_path: str,
    run_id: str,
    *,
    source_run_id: str,
    include_latency_cost: bool,
    include_ragas: bool,
) -> None:
    """Persist optional RAG aggregates from bounded observations when present.

    Observation rows are keyed to the retrieval/index or RAG source run that
    produced them, not to this newly-created eval run. Missing observation
    storage is optional and skipped; malformed numeric data remains a real
    runner error so eval_runs records a sanitized failure reason.
    """

    observations = _load_optional_rag_eval_observations(db_path, source_run_id=source_run_id)
    metrics: dict[str, float] = {}
    if include_latency_cost:
        metrics.update(aggregate_latency_metrics(observations))
        metrics.update(aggregate_cost_metrics(observations))
        metrics.update(aggregate_token_metrics(observations))
    if include_ragas:
        metrics.update(aggregate_quality_metrics(observations))

    for metric_name, metric_value in metrics.items():
        upsert_eval_metric(db_path, run_id, metric_name, metric_value)


def _load_optional_rag_eval_observations(db_path: str, *, source_run_id: str):
    try:
        return list_rag_eval_observations(db_path, source_run_id=source_run_id)
    except sqlite3.OperationalError as exc:
        if "rag_eval_observations" in str(exc) and "no such table" in str(exc).lower():
            return []
        raise


def _maybe_persist_latency_cost_metrics(db_path: str, run_id: str, *, source_run_id: str | None = None) -> None:
    """Persist optional latency/cost/token aggregates from bounded observations.

    This compatibility wrapper degrades gracefully when no observations exist.
    Aggregation is pure Python and avoids optional SQLite percentile functions.
    Only numeric aggregates are written to ``eval_metrics``; observation rows
    never contain raw prompts, answers, snippets, provider payloads, images, or
    document JSON.
    """

    observations = _load_optional_rag_eval_observations(db_path, source_run_id=source_run_id or run_id)
    metrics = {
        **aggregate_latency_metrics(observations),
        **aggregate_cost_metrics(observations),
        **aggregate_token_metrics(observations),
    }
    for metric_name, metric_value in metrics.items():
        upsert_eval_metric(db_path, run_id, metric_name, metric_value)


def _maybe_persist_ragas_placeholder_metrics(db_path: str, run_id: str, *, source_run_id: str | None = None) -> None:
    """Persist precomputed RAG quality aggregates from bounded observations.

    Despite the historical function name, this does not import RAGAS or call any
    provider. It only averages already-computed numeric faithfulness and answer
    relevancy values when they are present in ``rag_eval_observations``.
    """

    observations = _load_optional_rag_eval_observations(db_path, source_run_id=source_run_id or run_id)
    for metric_name, metric_value in aggregate_quality_metrics(observations).items():
        upsert_eval_metric(db_path, run_id, metric_name, metric_value)


def _sanitize_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    message = _ERROR_SANITIZE_RE.sub("", message)
    return message[:500]
