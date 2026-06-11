"""Lazy-import RAGAS quality producer (faithfulness + answer relevancy).

Importing this module is offline-safe: it imports neither ``ragas`` nor
``langchain_google_genai`` at module load. All optional SDK imports live inside
function bodies, mirroring ``src.rag.providers.build_answer_provider`` and
``src.rag.gemini.GeminiAnswerProvider``.

The producer re-runs the live RAG answer per gold query, scores the answer with
an injectable ``RagasScorer`` (the live one wraps a Gemini judge + embeddings),
and persists bounded numeric scores into ``rag_eval_observations`` keyed by
``query_id``. The existing ``aggregate_quality_metrics`` aggregation then lights
up ``rag.faithfulness.avg`` / ``rag.answer_relevancy.avg`` with no change.

Privacy boundary: only numeric scores + ids + status are persisted; never the
question, answer, contexts, snippets, or raw judge output (T-mw5-01).
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.eval.repository import (
    RAGEvalObservationRow,
    insert_rag_eval_observation,
    list_gold_retrieval_queries,
)

# Default Gemini model strings (GA, verified). text-embedding-004 is deprecated
# (Jan 14 2026) and must not be used.
_DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"
_DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"


def _finite_or_none(value: float | None) -> float | None:
    """Coerce None / NaN / inf to None so the repository's finite guard never trips.

    The live scorer already coerces NaN in ``_score_one``, but a fake/injected
    scorer (tests) or a future scorer may return a non-finite value directly;
    this is the defense-in-depth before persistence (T-mw5-03).
    """

    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


@dataclass(frozen=True)
class RagasSample:
    """Bounded scoring input for one gold query.

    Carries only the strings the judge needs. It is never persisted; only the
    numeric scores derived from it are written to ``rag_eval_observations``.
    """

    query_id: str
    question: str
    contexts: tuple[str, ...]
    answer: str


# Injectable seam: returns (faithfulness, answer_relevancy), each ``float | None``.
RagasScorer = Callable[[RagasSample], "tuple[float | None, float | None]"]


def _score_one(metric: Any, sample: Any) -> float | None:
    """Drive an async ragas metric from sync code, coercing failures to None.

    NaN / None / any exception (judge timeout, 429, parse failure) all coerce to
    ``None`` so one bad sample cannot sink the batch and a NaN cannot trip the
    repository's finite-float guard.
    """

    import asyncio
    import math

    try:
        import nest_asyncio

        nest_asyncio.apply()  # safe no-op outside a running loop; required under Streamlit
    except Exception:  # noqa: BLE001 - nest_asyncio is optional at import time
        pass

    try:
        value = asyncio.run(metric.single_turn_ascore(sample))
    except Exception:  # noqa: BLE001 - one bad sample must not sink the batch
        return None
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:  # NaN guard for non-float numerics
        return None
    return numeric


def build_ragas_scorer(
    *,
    api_key: str | None = None,
    judge_model: str = _DEFAULT_JUDGE_MODEL,
    embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
) -> RagasScorer:
    """Build the LIVE Gemini-judged RAGAS scorer.

    All ragas / langchain_google_genai imports are lazy (inside this function),
    so importing this module stays offline-safe. Raises
    ``AnswerConfigurationError`` when no API key is available, mirroring
    ``GeminiAnswerProvider``.
    """

    from src.config import get_settings
    from src.rag.providers import AnswerConfigurationError

    resolved_key = (api_key if api_key is not None else get_settings().gemini_api_key).strip()
    if not resolved_key:
        raise AnswerConfigurationError("Gemini API key is required for RAGAS scoring")

    # IMPORTANT: import ragas BEFORE langchain_google_genai. On Windows the grpc
    # native libs pulled by langchain_google_genai conflict with the grpc loaded
    # via ragas.llms' langchain_community.chat_models.vertexai import path, and the
    # reverse order segfaults the interpreter at import time (native access
    # violation). Importing ragas first loads its grpc symbols cleanly.
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, ResponseRelevancy

    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

    judge = ChatGoogleGenerativeAI(model=judge_model, temperature=0.0, api_key=resolved_key)
    evaluator_llm = LangchainLLMWrapper(judge)

    try:
        embeddings_model = GoogleGenerativeAIEmbeddings(model=embedding_model, google_api_key=resolved_key)
    except TypeError:
        # A1 fallback: if google_api_key kwarg is rejected, use GOOGLE_API_KEY env.
        import os

        os.environ.setdefault("GOOGLE_API_KEY", resolved_key)
        embeddings_model = GoogleGenerativeAIEmbeddings(model=embedding_model)
    evaluator_embeddings = LangchainEmbeddingsWrapper(embeddings_model)

    faithfulness_metric = Faithfulness(llm=evaluator_llm)
    relevancy_metric = ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings)

    def _scorer(sample: RagasSample) -> tuple[float | None, float | None]:
        single = SingleTurnSample(
            user_input=sample.question,
            response=sample.answer,
            retrieved_contexts=list(sample.contexts),
        )
        faith = _score_one(faithfulness_metric, single)
        relev = _score_one(relevancy_metric, single)
        return faith, relev

    return _scorer


def compute_ragas_quality(
    db_path: str,
    *,
    source_run_id: str,
    scorer: RagasScorer,
    answer_fn: Callable[..., Any] | None = None,
    provider: Any | None = None,
) -> int:
    """Produce real per-query faithfulness/answer_relevancy observation rows.

    For each gold query:
    - Re-run the live RAG answer (``answer_fn``, defaults to
      ``src.rag.service.answer_question``).
    - Unanswered (ABSTAINED / PROVIDER_ERROR, e.g. below_threshold ``rq_ex3_*``):
      persist a ``status="skipped"`` row with NULL scores; the judge is never
      sent abstention boilerplate.
    - Answered: build a ``RagasSample`` from the answer + citation snippets, score
      it, coerce NaN/exception to None, and persist a ``status="observed"`` row.

    Returns the count of observation rows persisted.
    """

    if answer_fn is None:
        from src.rag.service import answer_question

        answer_fn = answer_question
    if provider is None:
        from src.rag.providers import build_answer_provider

        provider = build_answer_provider("gemini")

    persisted = 0
    for query in list_gold_retrieval_queries(db_path):
        query_id = str(query["query_id"])
        query_text = str(query["query_text"])

        result = answer_fn(db_path, query_text, provider=provider)

        if not getattr(result, "is_answered", False):
            insert_rag_eval_observation(
                db_path,
                RAGEvalObservationRow(
                    source_run_id=source_run_id,
                    query_id=query_id,
                    status="skipped",
                    faithfulness=None,
                    answer_relevancy=None,
                ),
            )
            persisted += 1
            continue

        sample = RagasSample(
            query_id=query_id,
            question=query_text,
            contexts=tuple(citation.snippet for citation in result.citations),
            answer=result.answer_text,
        )
        try:
            faith, relev = scorer(sample)
        except Exception:  # noqa: BLE001 - one bad sample must not sink the batch
            faith, relev = None, None

        faith = _finite_or_none(faith)
        relev = _finite_or_none(relev)

        insert_rag_eval_observation(
            db_path,
            RAGEvalObservationRow(
                source_run_id=source_run_id,
                query_id=query_id,
                status="observed",
                faithfulness=faith,
                answer_relevancy=relev,
            ),
        )
        persisted += 1

    return persisted


__all__ = [
    "RagasSample",
    "RagasScorer",
    "build_ragas_scorer",
    "compute_ragas_quality",
]
