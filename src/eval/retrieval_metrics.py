"""Provider-free retrieval and citation evaluation metrics.

This module provides deterministic helpers for evaluating retrieval runs against
an offline gold set. It is intentionally *provider/LLM-free*.

Metric definitions
------------------
Recall@k
  For each query, recall@k is defined as:

    (# unique gold targets retrieved in the top-k hits) / (# unique gold targets)

  where a "target" is identified at *page-level* by the tuple
  ``(doc_id, page_num)``.

  The module also computes a macro-average across queries (simple mean of
  per-query recalls).

Page-level citation accuracy
  For each query, citation accuracy is 1.0 if **any** cited page
  ``(doc_id, page_num)`` matches **any** gold target for that query, else 0.0.

Limitations
-----------
- Page-level matching does not guarantee the cited page contains the exact span
  supporting the answer. Span-level grounding validation is out-of-scope here.
- Scores ignore raw text and operate only on identifiers: ``(doc_id, page_num)``.

Empty-state behavior
--------------------
- Empty gold sets, missing queries, missing retrieved hits, and missing citations
  are all handled gracefully (metrics return 0.0 and per-query breakdowns are
  still returned).

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


PageId = tuple[str, int]


@dataclass(frozen=True)
class RecallAtKResult:
    """Result for recall@k computation."""

    k: int
    macro_recall: float
    per_query_recall: dict[str, float]


def _normalize_page_id(doc_id: object, page_num: object) -> PageId:
    return (str(doc_id), int(page_num))


def _unique_pages(items: Iterable[tuple[object, object]]) -> set[PageId]:
    return {_normalize_page_id(doc_id, page_num) for doc_id, page_num in items}


def compute_retrieval_recall_at_k(
    gold_targets_by_query: Mapping[str, Iterable[tuple[object, object]]],
    retrieved_hits_by_query: Mapping[str, Sequence[tuple[object, object, object]]],
    k: int,
) -> RecallAtKResult:
    """Compute recall@k per query + macro average.

    Parameters
    ----------
    gold_targets_by_query:
        Mapping query_id -> iterable of gold target page identifiers
        ``(doc_id, page_num)``.
    retrieved_hits_by_query:
        Mapping query_id -> sequence of retrieved hits for that query.
        Each hit is ``(doc_id, page_num, score)``. Only the first ``k`` hits are
        considered; score is ignored for recall.
    k:
        Cutoff for top-k.

    Returns
    -------
    RecallAtKResult
        Contains per-query recalls (including queries with empty/missing gold)
        and the macro-average across all query_ids present in
        ``gold_targets_by_query``.

    Notes
    -----
    - Duplicates in either gold or retrieved hits are de-duplicated by page id.
    - If a query has zero gold targets, its recall is defined as 0.0.
    """

    if k <= 0:
        raise ValueError("k must be >= 1")

    per_query: dict[str, float] = {}

    for query_id, gold_targets in gold_targets_by_query.items():
        gold_pages = _unique_pages(gold_targets)
        if not gold_pages:
            per_query[str(query_id)] = 0.0
            continue

        hits = retrieved_hits_by_query.get(query_id) or []
        topk = hits[:k]
        retrieved_pages = _unique_pages((doc_id, page_num) for doc_id, page_num, _score in topk)

        overlap = gold_pages.intersection(retrieved_pages)
        per_query[str(query_id)] = float(len(overlap)) / float(len(gold_pages))

    macro = sum(per_query.values()) / len(per_query) if per_query else 0.0
    return RecallAtKResult(k=k, macro_recall=macro, per_query_recall=per_query)


def compute_page_level_citation_accuracy(
    gold_targets_by_query: Mapping[str, Iterable[tuple[object, object]]],
    cited_pages_by_query: Mapping[str, Iterable[tuple[object, object]]],
) -> dict[str, float]:
    """Compute page-level citation accuracy per query + macro average.

    A query is counted as correct (1.0) if any cited page matches any gold page
    for that query. Otherwise it is incorrect (0.0).

    Behavior for empty-state:
    - If a query has no gold targets, accuracy is 0.0.
    - If a query has gold targets but no cited pages, accuracy is 0.0.

    Returns
    -------
    dict
        {"macro_accuracy": float, "per_query_accuracy": {query_id: 0.0|1.0}}
    """

    per_query: dict[str, float] = {}

    for query_id, gold_targets in gold_targets_by_query.items():
        gold_pages = _unique_pages(gold_targets)
        if not gold_pages:
            per_query[str(query_id)] = 0.0
            continue

        cited_pages = _unique_pages(cited_pages_by_query.get(query_id) or [])
        per_query[str(query_id)] = 1.0 if gold_pages.intersection(cited_pages) else 0.0

    macro = sum(per_query.values()) / len(per_query) if per_query else 0.0
    return {"macro_accuracy": macro, "per_query_accuracy": per_query}
