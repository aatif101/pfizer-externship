"""LangGraph wiring for the agentic RAG pipeline (RAG-03).

Flow: decompose -> retrieve -> evaluate -> [rewrite -> retrieve]* -> draft ->
critique -> [draft]? -> finalize | abstain.

``langgraph`` is imported lazily inside functions so importing this module
stays cheap and the linear path never pays for it. ``answer_question_agentic``
returns the same ``AnswerResult`` DTO as ``src.rag.service.answer_question`` and
is call-compatible with the eval harness seam
``answer_fn(db_path, query_text, provider=provider)``.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable

from src.rag.agentic import nodes
from src.rag.agentic.routing import route_after_critique, route_after_evaluate, route_after_rewrite
from src.rag.agentic.state import (
    DEFAULT_CRITIC_MIN_FAITHFULNESS,
    GRAPH_RECURSION_LIMIT,
    AgenticDeps,
)
from src.config import get_settings
from src.rag.critic import CriticProvider, build_critic_provider
from src.rag.models import AnswerDiagnostics, AnswerReasonCode, AnswerResult, AnswerStatus
from src.rag.providers import AnswerProvider
from src.rag.service import (
    _DEFAULT_TOP_K,
    _abstained_result,
    _citations_from_hits,
    _provider_error_result,
    _provider_name,
)
from src.retrieval.models import EvidenceGateResult
from src.tracing import build_callback_handler, observe, safe_update_current_trace

__all__ = ["GRAPH_RECURSION_LIMIT", "answer_question_agentic", "build_agentic_graph"]

# Injectable test seams (mirrors src.rag.service). langfuse_context=None means
# "resolve the live v3 client lazily inside src.tracing".
_LANGFUSE_AVAILABLE: bool = True
langfuse_context: Any | None = None

# Non-content diagnostics only. Question, draft, evidence text, snippets, critic
# feedback, and unsupported claims are intentionally absent.
_AGENTIC_TRACE_ALLOWED_KEYS = frozenset(
    {
        "boundary",
        "answer_status",
        "reason_code",
        "run_id",
        "provider_name",
        "trace_id",
        "top_score",
        "citation_count",
        "evidence_reason",
        "error_class",
        "pipeline",
        "retrieval_rounds",
        "sub_query_count",
        "regeneration_count",
        "critic_verdict",
        "critic_score",
    }
)


def _route_after_decompose(state: dict[str, Any]) -> str:
    return "abstain" if state.get("outcome") == "abstained" else "retrieve"


def build_agentic_graph(deps: AgenticDeps) -> Any:
    """Compile the agentic StateGraph with nodes bound to ``deps``."""

    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415 - lazy by design

    from src.rag.agentic.state import AgenticState  # noqa: PLC0415

    builder = StateGraph(AgenticState)
    builder.add_node("decompose", lambda state: nodes.decompose(state, deps))
    builder.add_node("retrieve", lambda state: nodes.retrieve(state, deps))
    builder.add_node("evaluate", lambda state: nodes.evaluate(state, deps))
    builder.add_node("rewrite", lambda state: nodes.rewrite(state, deps))
    builder.add_node("draft", lambda state: nodes.draft(state, deps))
    builder.add_node("critique", lambda state: nodes.critique(state, deps))
    builder.add_node("finalize", lambda state: nodes.finalize(state, deps))
    builder.add_node("abstain", lambda state: nodes.abstain(state, deps))

    builder.add_edge(START, "decompose")
    builder.add_conditional_edges(
        "decompose", _route_after_decompose, {"retrieve": "retrieve", "abstain": "abstain"}
    )
    builder.add_edge("retrieve", "evaluate")
    builder.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {"draft": "draft", "rewrite": "rewrite", "abstain": "abstain"},
    )
    builder.add_conditional_edges(
        "rewrite", route_after_rewrite, {"retrieve": "retrieve", "abstain": "abstain"}
    )
    builder.add_edge("draft", "critique")
    builder.add_conditional_edges(
        "critique",
        route_after_critique,
        {"finalize": "finalize", "draft": "draft", "abstain": "abstain"},
    )
    builder.add_edge("finalize", END)
    builder.add_edge("abstain", END)
    return builder.compile()


@observe(name="rag.agentic", capture_input=False, capture_output=False)
def answer_question_agentic(
    db_path: str,
    question: str,
    *,
    provider: AnswerProvider | None,
    critic: CriticProvider | None = None,
    top_k: int = _DEFAULT_TOP_K,
    retrieve_fn: Callable[..., EvidenceGateResult] | None = None,
    decomposer: Callable[[str], str] | None = None,
    rewriter: Callable[[str], str] | None = None,
    critic_min_faithfulness: float | None = None,
) -> AnswerResult:
    """Answer via the bounded agentic graph, or abstain safely.

    Never raises for graph failures: a ``GraphRecursionError`` becomes an
    ABSTAINED ``retrieval_exhausted`` result and any other exception becomes an
    ABSTAINED ``retrieval_error`` result.

    When ``critic`` is None it is resolved from settings via
    ``build_critic_provider``; a resolution failure leaves the critic unset so
    the draft node abstains with ``critic_error`` before any provider call (D-02).
    """

    result = _run_agentic(
        db_path,
        question,
        provider=provider,
        critic=critic,
        top_k=top_k,
        retrieve_fn=retrieve_fn,
        decomposer=decomposer,
        rewriter=rewriter,
        critic_min_faithfulness=critic_min_faithfulness,
    )
    _update_agentic_trace_metadata(result)
    return result


def _run_agentic(
    db_path: str,
    question: str,
    *,
    provider: AnswerProvider | None,
    critic: CriticProvider | None,
    top_k: int,
    retrieve_fn: Callable[..., EvidenceGateResult] | None,
    decomposer: Callable[[str], str] | None,
    rewriter: Callable[[str], str] | None,
    critic_min_faithfulness: float | None,
) -> AnswerResult:
    critic_error_class: str | None = None
    if critic is None:
        try:
            critic = build_critic_provider()
        except Exception as exc:  # noqa: BLE001 - fail closed: no critic means abstain (D-02).
            critic = None
            critic_error_class = exc.__class__.__name__
    if critic_min_faithfulness is None:
        try:
            critic_min_faithfulness = float(get_settings().critic_min_faithfulness)
        except Exception:  # noqa: BLE001 - settings failure keeps the conservative default.
            critic_min_faithfulness = DEFAULT_CRITIC_MIN_FAITHFULNESS

    complete_text = getattr(provider, "complete_text", None) if provider is not None else None
    if callable(complete_text):
        if decomposer is None:
            decomposer = lambda prompt: complete_text(prompt, role="decompose")  # noqa: E731
        if rewriter is None:
            rewriter = lambda prompt: complete_text(prompt, role="rewrite")  # noqa: E731

    deps = AgenticDeps(
        db_path=db_path,
        answer_provider=provider,
        critic=critic,
        retrieve_fn=retrieve_fn,
        decomposer=decomposer,
        rewriter=rewriter,
        top_k=max(1, int(top_k)),
        critic_min_faithfulness=float(critic_min_faithfulness),
        critic_error_class=critic_error_class,
    )
    initial: dict[str, Any] = {"question": question or "", "steps": []}
    try:
        from langgraph.errors import GraphRecursionError  # noqa: PLC0415 - lazy by design
    except Exception:  # pragma: no cover - langgraph is a pinned dependency
        GraphRecursionError = RecursionError  # type: ignore[assignment,misc]  # noqa: N806

    try:
        graph = build_agentic_graph(deps)
        # Module global read at call time so tests can monkeypatch the backstop.
        config: dict[str, Any] = {"recursion_limit": GRAPH_RECURSION_LIMIT}
        handler = build_callback_handler()
        if handler is not None:
            config["callbacks"] = [handler]
        final = graph.invoke(initial, config)
    except GraphRecursionError as exc:
        return _mark_agentic(
            _abstained_result(
                reason_code=AnswerReasonCode.RETRIEVAL_EXHAUSTED,
                run_id=None,
                provider_name=_provider_name(provider),
                top_score=0.0,
                evidence_reason="retrieval_exhausted",
                error_class=exc.__class__.__name__,
            ),
            {},
        )
    except Exception as exc:  # noqa: BLE001 - graph boundary must not crash callers.
        return _mark_agentic(
            _abstained_result(
                reason_code=AnswerReasonCode.RETRIEVAL_ERROR,
                run_id=None,
                provider_name=_provider_name(provider),
                top_score=0.0,
                evidence_reason="retrieval_error",
                error_class=exc.__class__.__name__,
            ),
            {},
        )
    return _result_from_state(final, deps)


def _result_from_state(final: dict[str, Any], deps: AgenticDeps) -> AnswerResult:
    """Map terminal graph state onto the shared ``AnswerResult`` contract."""

    outcome = final.get("outcome")
    run_id = final.get("run_id")
    provider_name = final.get("provider_name") or _provider_name(deps.answer_provider)
    top_score = float(final.get("top_score", 0.0) or 0.0)
    evidence_reason = final.get("evidence_reason") or ""
    draft_text = (final.get("draft") or "").strip()

    if outcome == "answered" and draft_text:
        citations = tuple(final.get("citations") or ()) or _citations_from_hits(tuple(final.get("evidence") or ()))
        result = AnswerResult(
            status=AnswerStatus.ANSWERED,
            answer_text=draft_text,
            citations=citations,
            diagnostics=AnswerDiagnostics(
                status=AnswerStatus.ANSWERED,
                reason_code=AnswerReasonCode.ANSWERED,
                run_id=run_id,
                provider_name=provider_name,
                trace_id=final.get("trace_id"),
                top_score=top_score,
                citation_count=len(citations),
                evidence_reason=evidence_reason,
                error_class=None,
            ),
        )
    elif outcome == "provider_error":
        result = _provider_error_result(
            reason_code=_reason(final, AnswerReasonCode.PROVIDER_EXCEPTION),
            run_id=run_id,
            provider_name=provider_name,
            trace_id=final.get("trace_id"),
            top_score=top_score,
            citation_count=0,
            evidence_reason=evidence_reason,
            error_class=final.get("error_class") or "AnswerProviderError",
        )
    else:
        result = _abstained_result(
            reason_code=_reason(final, AnswerReasonCode.RETRIEVAL_EXHAUSTED),
            run_id=run_id,
            provider_name=provider_name,
            top_score=top_score,
            evidence_reason=evidence_reason,
            error_class=final.get("error_class"),
        )
    return _mark_agentic(result, final)


def _update_agentic_trace_metadata(result: AnswerResult) -> None:
    """Attach allowlisted agentic diagnostics to the current trace, if available."""

    diagnostics = result.diagnostics
    _safe_update_trace_metadata(
        {
            "boundary": "rag.agentic",
            "answer_status": diagnostics.status.value,
            "reason_code": diagnostics.reason_code.value,
            "run_id": diagnostics.run_id,
            "provider_name": diagnostics.provider_name,
            "trace_id": diagnostics.trace_id,
            "top_score": diagnostics.top_score,
            "citation_count": diagnostics.citation_count,
            "evidence_reason": diagnostics.evidence_reason,
            "error_class": diagnostics.error_class,
            "pipeline": getattr(diagnostics, "pipeline", None),
            "retrieval_rounds": getattr(diagnostics, "retrieval_rounds", None),
            "sub_query_count": getattr(diagnostics, "sub_query_count", None),
            "regeneration_count": getattr(diagnostics, "regeneration_count", None),
            "critic_verdict": getattr(diagnostics, "critic_verdict", None),
            "critic_score": getattr(diagnostics, "critic_score", None),
        }
    )


def _safe_update_trace_metadata(metadata: dict[str, Any]) -> None:
    """Update Langfuse trace metadata defensively with the agentic allowlist. Never raises."""

    if not _LANGFUSE_AVAILABLE:
        return
    try:
        safe_update_current_trace(
            tags=["rag", "agentic"],
            metadata=metadata,
            allowed_metadata_keys=_AGENTIC_TRACE_ALLOWED_KEYS,
            context=langfuse_context,
        )
    except Exception:  # noqa: BLE001 - tracing must never break answering.
        return


def _reason(final: dict[str, Any], default: AnswerReasonCode) -> AnswerReasonCode:
    raw = final.get("reason_code")
    if not raw or raw == AnswerReasonCode.ANSWERED.value:
        return default
    try:
        return AnswerReasonCode(raw)
    except ValueError:
        return default


def _mark_agentic(result: AnswerResult, final: dict[str, Any]) -> AnswerResult:
    diagnostics = dataclasses.replace(
        result.diagnostics,
        pipeline="agentic",
        retrieval_rounds=int(final.get("retrieval_round", 0) or 0),
        regeneration_count=int(final.get("regeneration_count", 0) or 0),
        sub_query_count=len(final.get("sub_queries") or ()),
        critic_verdict=final.get("critic_verdict"),
        critic_score=final.get("critic_score"),
    )
    return dataclasses.replace(result, diagnostics=diagnostics)
