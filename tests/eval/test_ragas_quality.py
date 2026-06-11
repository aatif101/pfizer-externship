"""Offline tests for the lazy-import RAGAS quality producer.

These tests NEVER import ragas or langchain_google_genai. They inject a fake
``scorer`` and a fake ``answer_fn`` so no network call and no optional SDK import
happens. The module under test must keep all ragas/langchain imports inside
function bodies so importing it is credential-free and SDK-free.
"""
from __future__ import annotations

import importlib
import math
import sqlite3
import sys

import pytest

from src.db.schema import init_db
from src.eval import ragas_quality
from src.eval.operational_metrics import (
    ANSWER_RELEVANCY_AVG,
    FAITHFULNESS_AVG,
    aggregate_quality_metrics,
)
from src.eval.ragas_quality import RagasSample, compute_ragas_quality
from src.eval.repository import list_rag_eval_observations
from src.rag.models import (
    AnswerCitation,
    AnswerDiagnostics,
    AnswerReasonCode,
    AnswerResult,
    AnswerStatus,
)


def _seed_gold_queries(db_path: str, queries: list[tuple[str, str]]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for query_id, query_text in queries:
            conn.execute(
                "INSERT INTO gold_retrieval_queries (query_id, query_text) VALUES (?, ?)",
                (query_id, query_text),
            )
        conn.commit()
    finally:
        conn.close()


def _answered_result(
    answer_text: str,
    snippets: list[str],
    evidence_texts: list[str] | None = None,
) -> AnswerResult:
    bodies = evidence_texts if evidence_texts is not None else snippets
    citations = tuple(
        AnswerCitation(
            doc_id="d1",
            filename="d1.pdf",
            page_num=idx,
            display_page_num=idx + 1,
            snippet=snippet,
            score=0.9,
            evidence_text=bodies[idx],
        )
        for idx, snippet in enumerate(snippets)
    )
    return AnswerResult(
        status=AnswerStatus.ANSWERED,
        answer_text=answer_text,
        citations=citations,
        diagnostics=AnswerDiagnostics(
            status=AnswerStatus.ANSWERED,
            reason_code=AnswerReasonCode.ANSWERED,
            run_id="run-1",
            provider_name="fake",
            trace_id=None,
            top_score=0.9,
            citation_count=len(citations),
            evidence_reason="ok",
        ),
    )


def _abstained_result() -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus.ABSTAINED,
        answer_text="not enough evidence",
        citations=(),
        diagnostics=AnswerDiagnostics(
            status=AnswerStatus.ABSTAINED,
            reason_code=AnswerReasonCode.BELOW_THRESHOLD,
            run_id="run-1",
            provider_name="fake",
            trace_id=None,
            top_score=0.1,
            citation_count=0,
            evidence_reason="below_threshold",
        ),
    )


def _make_answer_fn(answers: dict[str, AnswerResult]):
    def _answer_fn(db_path, question, *, provider=None, **kwargs):  # noqa: ANN001, ANN002
        return answers[question]

    return _answer_fn


def test_module_import_is_offline() -> None:
    """Importing ragas_quality must not import ragas or langchain_google_genai."""

    for mod in list(sys.modules):
        if mod == "ragas" or mod.startswith("ragas.") or mod.startswith("langchain_google_genai"):
            del sys.modules[mod]

    importlib.reload(ragas_quality)

    assert "ragas" not in sys.modules
    assert not any(name.startswith("langchain_google_genai") for name in sys.modules)


def test_scores_persist_keyed_by_query_id(tmp_path) -> None:
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_gold_queries(db_path, [("q1", "what is the assay result?")])

    answers = {"what is the assay result?": _answered_result("Assay is 99.2%", ["assay 99.2%"])}

    def fake_scorer(sample: RagasSample):
        return (0.9, 0.8)

    count = compute_ragas_quality(
        db_path,
        source_run_id="src-run",
        scorer=fake_scorer,
        answer_fn=_make_answer_fn(answers),
        provider=object(),
    )

    assert count == 1
    rows = list_rag_eval_observations(db_path, query_id="q1")
    assert len(rows) == 1
    assert rows[0].faithfulness == pytest.approx(0.9)
    assert rows[0].answer_relevancy == pytest.approx(0.8)
    assert rows[0].source_run_id == "src-run"
    assert rows[0].status == "observed"


def test_judge_contexts_equal_citation_evidence_text(tmp_path) -> None:
    """The faithfulness contract: RagasSample.contexts == the answered citations'
    evidence_text strings, in order — the exact contexts the generator saw."""

    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_gold_queries(db_path, [("q1", "what is the assay result?")])

    evidence_texts = [
        "WIDE_EVIDENCE_A: full grounding sentence the judge must score against.",
        "WIDE_EVIDENCE_B: a second wider grounding context distinct from the teaser.",
    ]
    answers = {
        "what is the assay result?": _answered_result(
            "Assay is 99.2%",
            snippets=["short teaser a", "short teaser b"],
            evidence_texts=evidence_texts,
        )
    }

    captured: dict[str, tuple[str, ...]] = {}

    def capturing_scorer(sample: RagasSample):
        captured["contexts"] = sample.contexts
        return (0.5, 0.5)

    compute_ragas_quality(
        db_path,
        source_run_id="src-run",
        scorer=capturing_scorer,
        answer_fn=_make_answer_fn(answers),
        provider=object(),
    )

    # The judge's contexts are exactly the evidence_text strings, not the teasers.
    assert captured["contexts"] == tuple(evidence_texts)
    assert "short teaser a" not in captured["contexts"]

    # Privacy: no evidence_text string is persisted to rag_eval_observations.
    rows = list_rag_eval_observations(db_path, source_run_id="src-run")
    assert len(rows) == 1
    persisted_repr = repr(rows[0])
    for body in evidence_texts:
        assert body not in persisted_repr


def test_null_preserved_for_unanswered(tmp_path) -> None:
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_gold_queries(
        db_path,
        [("rq_ex3_a", "below threshold query"), ("q_ok", "answerable query")],
    )

    answers = {
        "below threshold query": _abstained_result(),
        "answerable query": _answered_result("real answer", ["ctx"]),
    }

    def fake_scorer(sample: RagasSample):
        return (0.7, 0.6)

    compute_ragas_quality(
        db_path,
        source_run_id="src-run",
        scorer=fake_scorer,
        answer_fn=_make_answer_fn(answers),
        provider=object(),
    )

    skipped = list_rag_eval_observations(db_path, query_id="rq_ex3_a")
    assert len(skipped) == 1
    assert skipped[0].faithfulness is None
    assert skipped[0].answer_relevancy is None
    assert skipped[0].status != "observed"

    answered = list_rag_eval_observations(db_path, query_id="q_ok")
    assert len(answered) == 1
    assert answered[0].faithfulness == pytest.approx(0.7)

    # The unanswered query contributes nothing to the aggregate.
    rows = list_rag_eval_observations(db_path, source_run_id="src-run")
    metrics = aggregate_quality_metrics(rows)
    assert metrics[FAITHFULNESS_AVG] == pytest.approx(0.7)


def test_nan_coerced_to_none(tmp_path) -> None:
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_gold_queries(db_path, [("q1", "nan query")])

    answers = {"nan query": _answered_result("answer", ["ctx"])}

    def nan_scorer(sample: RagasSample):
        return (float("nan"), 0.5)

    # Must not raise (repository._coerce_nullable_float rejects NaN).
    compute_ragas_quality(
        db_path,
        source_run_id="src-run",
        scorer=nan_scorer,
        answer_fn=_make_answer_fn(answers),
        provider=object(),
    )

    rows = list_rag_eval_observations(db_path, query_id="q1")
    assert len(rows) == 1
    assert rows[0].faithfulness is None
    assert rows[0].answer_relevancy == pytest.approx(0.5)


def test_exception_isolated(tmp_path) -> None:
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_gold_queries(db_path, [("q_bad", "bad query"), ("q_good", "good query")])

    answers = {
        "bad query": _answered_result("answer bad", ["ctx"]),
        "good query": _answered_result("answer good", ["ctx"]),
    }

    def flaky_scorer(sample: RagasSample):
        if sample.query_id == "q_bad":
            raise RuntimeError("judge exploded")
        return (0.95, 0.85)

    count = compute_ragas_quality(
        db_path,
        source_run_id="src-run",
        scorer=flaky_scorer,
        answer_fn=_make_answer_fn(answers),
        provider=object(),
    )

    assert count == 2
    bad = list_rag_eval_observations(db_path, query_id="q_bad")
    assert bad[0].faithfulness is None
    assert bad[0].answer_relevancy is None

    good = list_rag_eval_observations(db_path, query_id="q_good")
    assert good[0].faithfulness == pytest.approx(0.95)


def test_aggregates_from_real_scores(tmp_path) -> None:
    db_path = str(tmp_path / "eval.sqlite")
    init_db(db_path)
    _seed_gold_queries(db_path, [("q1", "query one"), ("q2", "query two")])

    answers = {
        "query one": _answered_result("ans1", ["ctx1"]),
        "query two": _answered_result("ans2", ["ctx2"]),
    }
    scores = {"q1": (0.8, 0.6), "q2": (0.6, 0.4)}

    def fake_scorer(sample: RagasSample):
        return scores[sample.query_id]

    compute_ragas_quality(
        db_path,
        source_run_id="src-run",
        scorer=fake_scorer,
        answer_fn=_make_answer_fn(answers),
        provider=object(),
    )

    rows = list_rag_eval_observations(db_path, source_run_id="src-run")
    metrics = aggregate_quality_metrics(rows)
    assert metrics[FAITHFULNESS_AVG] == pytest.approx((0.8 + 0.6) / 2)
    assert metrics[ANSWER_RELEVANCY_AVG] == pytest.approx((0.6 + 0.4) / 2)


def test_score_one_coerces_nan_and_exception() -> None:
    """The async-driving helper coerces NaN/None/exception to None."""

    class _GoodMetric:
        async def single_turn_ascore(self, sample):  # noqa: ANN001
            return 0.5

    class _NanMetric:
        async def single_turn_ascore(self, sample):  # noqa: ANN001
            return float("nan")

    class _BoomMetric:
        async def single_turn_ascore(self, sample):  # noqa: ANN001
            raise RuntimeError("boom")

    assert ragas_quality._score_one(_GoodMetric(), object()) == pytest.approx(0.5)
    assert ragas_quality._score_one(_NanMetric(), object()) is None
    assert ragas_quality._score_one(_BoomMetric(), object()) is None
