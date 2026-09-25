"""Node functions for the agentic RAG graph.

Every node is a plain function ``node(state, deps) -> partial state dict`` with
no langgraph import, so nodes are unit-testable without compiling a graph.
Each node appends its own name to ``steps``.

Safety invariants owned here:
- ``retrieve`` passes ONLY ``top_k`` to the retrieval gate, so the default
  evidence thresholds apply unchanged on every round (never relaxed on retry).
- ``draft`` refuses to call the answer provider when no critic is configured
  (D-02 fail closed; also saves provider quota).
- ``critique`` maps every critic failure to ``critic_error``; only an accepted
  verdict can lead to ``finalize``.
- Citations are never built here from provider or critic text; the graph
  result builder derives them from merged retrieval hits only.

Observability (OBS-01): each node runs in its own Langfuse span named
``agent.<node>`` with input/output capture disabled, and attaches only the
allowlisted numeric/id metadata in ``_NODE_SPAN_ALLOWED_KEYS``. Question text,
query text, snippets, evidence text, drafts, and critic feedback never reach a
span.
"""
from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from src.rag.agentic.decompose import decompose_question
from src.rag.agentic.rewrite import rewrite_query
from src.rag.agentic.state import AgenticDeps
from src.rag.critic import CriticRequest, CriticVerdict
from src.rag.models import AnswerReasonCode
from src.rag.providers import AnswerProviderRequest, AnswerProviderResult, AnswerValidationError
from src.rag.service import _citations_from_hits, _provider_exception_reason
from src.retrieval.models import RetrievalHit
from src.tracing import observe, safe_update_current_span

_CRITIC_FEEDBACK_MAX_CHARS = 1000
_DEFAULT_CRITIC_FEEDBACK = "Remove any claim not directly supported by the evidence."

State = Mapping[str, Any]

# Injectable test seams (mirrors src.rag.agentic.graph). langfuse_context=None
# means "resolve the live v3 client lazily inside src.tracing".
_LANGFUSE_AVAILABLE: bool = True
langfuse_context: Any | None = None

# Non-content, numeric/id-only span metadata. Content keys (question, query text,
# snippet, evidence_text, draft, critic_feedback, unsupported claims) are absent.
_NODE_SPAN_ALLOWED_KEYS = frozenset(
    {
        "retrieval_round",
        "sub_query_count",
        "regeneration_count",
        "critic_verdict",
        "critic_score",
        "critic_accepted",
        "citation_count",
        "doc_id",
        "page_number",
        "outcome",
        "reason_code",
        "error_class",
    }
)


def _span_meta(metadata: dict[str, Any]) -> None:
    """Attach allowlisted metadata to the current node span. Never raises."""

    if not _LANGFUSE_AVAILABLE:
        return
    try:
        safe_update_current_span(
            metadata=metadata,
            allowed_metadata_keys=_NODE_SPAN_ALLOWED_KEYS,
            context=langfuse_context,
        )
    except Exception:  # noqa: BLE001 - tracing must never break answering.
        return


def _outcome_meta(update: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "outcome": update.get("outcome"),
        "reason_code": update.get("reason_code"),
        "error_class": update.get("error_class"),
    }


def _resolve_retrieve_fn(deps: AgenticDeps) -> Any:
    if deps.retrieve_fn is not None:
        return deps.retrieve_fn
    from src.retrieval.retriever import retrieve_evidence  # noqa: PLC0415 - keep node import light

    return retrieve_evidence


@observe(name="agent.decompose", capture_input=False, capture_output=False)
def decompose(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Split the question into bounded sub-queries (deterministic-first)."""

    update = _decompose(state, deps)
    _span_meta({"sub_query_count": len(update.get("sub_queries") or ()), **_outcome_meta(update)})
    return update


def _decompose(state: State, deps: AgenticDeps) -> dict[str, Any]:
    question = (state.get("question") or "").strip()
    if not question:
        return {
            "sub_queries": [],
            "active_queries": {},
            "outcome": "abstained",
            "reason_code": AnswerReasonCode.EMPTY_QUESTION.value,
            "evidence_reason": "empty_question",
            "steps": ["decompose"],
        }
    sub_queries, method = decompose_question(question, llm=deps.decomposer)
    # Sub-queries are dict keys below; decompose_question already dedupes and caps.
    sub_queries = [text for text in sub_queries if text] or [question]
    return {
        "sub_queries": list(sub_queries),
        "active_queries": {text: text for text in sub_queries},
        "tried_queries": list(sub_queries),
        "per_query_strong": {text: False for text in sub_queries},
        "strong_hits": {},
        "retrieval_round": 0,
        "regeneration_count": 0,
        "steps": ["decompose", f"decompose:{method}"],
    }


@observe(name="agent.retrieve", capture_input=False, capture_output=False)
def retrieve(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Run the evidence gate once per still-active sub-query."""

    retrieve_fn = _resolve_retrieve_fn(deps)
    round_number = int(state.get("retrieval_round", 0)) + 1
    per_query_strong = dict(state.get("per_query_strong") or {})
    strong_hits = dict(state.get("strong_hits") or {})
    run_id = state.get("run_id")
    top_score = float(state.get("top_score", 0.0) or 0.0)
    evidence_reason = state.get("evidence_reason") or ""
    update: dict[str, Any] = {"retrieval_round": round_number, "steps": ["retrieve"]}
    top_hit: RetrievalHit | None = None

    for original, query_text in dict(state.get("active_queries") or {}).items():
        try:
            # Only top_k: the gate defaults (min_top_score, min_query_term_coverage,
            # min_hit_count) must apply unchanged on every round.
            result = retrieve_fn(deps.db_path, query_text, top_k=deps.top_k)
        except Exception as exc:  # noqa: BLE001 - graph boundary must fail closed, not crash.
            update.update(
                {
                    "error_class": exc.__class__.__name__,
                    "reason_code": AnswerReasonCode.RETRIEVAL_ERROR.value,
                    "outcome": "abstained",
                    "evidence_reason": "retrieval_error",
                }
            )
            break
        per_query_strong[original] = bool(result.is_strong)
        for hit in result.hits:
            if top_hit is None or hit.score > top_hit.score:
                top_hit = hit
        if result.is_strong:
            strong_hits[original] = tuple(result.hits)
        if run_id is None and result.run_id is not None:
            run_id = result.run_id
        top_score = max(top_score, float(result.top_score))
        evidence_reason = result.reason_code.value

    update.setdefault("evidence_reason", evidence_reason)
    update.update(
        {
            "per_query_strong": per_query_strong,
            "strong_hits": strong_hits,
            "run_id": run_id,
            "top_score": top_score,
        }
    )
    _span_meta(
        {
            "retrieval_round": round_number,
            "doc_id": top_hit.doc_id if top_hit is not None else None,
            "page_number": top_hit.page_num if top_hit is not None else None,
            **_outcome_meta(update),
        }
    )
    return update


@observe(name="agent.evaluate", capture_input=False, capture_output=False)
def evaluate(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Merge strong hits (dedupe by doc/page, max score) and retire strong sub-queries.

    ``per_query_strong`` is keyed by ORIGINAL sub-query, and routing drafts only
    when every original is strong: a compound question with any uncovered
    sub-query is never answered from the covered half (research A6).
    """

    merged: dict[tuple[str, int], RetrievalHit] = {}
    for hits in (state.get("strong_hits") or {}).values():
        for hit in hits:
            key = (hit.doc_id, hit.page_num)
            current = merged.get(key)
            if current is None or hit.score > current.score:
                merged[key] = hit
    evidence = tuple(sorted(merged.values(), key=lambda hit: hit.score, reverse=True)[: max(1, deps.top_k)])

    per_query_strong = state.get("per_query_strong") or {}
    active = {
        original: text
        for original, text in (state.get("active_queries") or {}).items()
        if not per_query_strong.get(original, False)
    }
    _span_meta(
        {
            "sub_query_count": len(state.get("sub_queries") or ()),
            "retrieval_round": int(state.get("retrieval_round", 0) or 0),
        }
    )
    return {"evidence": evidence, "active_queries": active, "steps": ["evaluate"]}


@observe(name="agent.rewrite", capture_input=False, capture_output=False)
def rewrite(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Rewrite only the still-weak sub-queries, with a monotonic-progress guard.

    Each active sub-query tries deterministic domain-synonym expansion first,
    then (only when configured) an LLM keyword rewrite. A candidate equal to an
    already-tried query is no progress; when no active sub-query gets a new
    query the loop is exhausted and routing abstains.
    """

    steps = ["rewrite"]
    tried = list(state.get("tried_queries") or [])
    active = dict(state.get("active_queries") or {})
    changed = False
    for original, query_text in list(active.items()):
        new_text, method = rewrite_query(query_text, tried=tried, llm=deps.rewriter)
        steps.append(f"rewrite:{method}")
        if new_text is not None:
            active[original] = new_text
            tried.append(new_text)
            changed = True
    _span_meta(
        {
            "retrieval_round": int(state.get("retrieval_round", 0) or 0),
            "sub_query_count": len(state.get("sub_queries") or ()),
        }
    )
    return {
        "active_queries": active,
        "tried_queries": tried,
        "rewrite_exhausted": not changed,
        "steps": steps,
    }


@observe(name="agent.draft", capture_input=False, capture_output=False)
def draft(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Generate (or regenerate once) a draft answer from merged evidence."""

    update = _draft(state, deps)
    regenerations = update.get("regeneration_count", state.get("regeneration_count", 0))
    _span_meta({"regeneration_count": int(regenerations or 0), **_outcome_meta(update)})
    return update


def _draft(state: State, deps: AgenticDeps) -> dict[str, Any]:

    if deps.critic is None:
        # D-02 fail closed: an unverifiable draft is never produced.
        return {
            "error_class": deps.critic_error_class or "CriticNotConfigured",
            "reason_code": AnswerReasonCode.CRITIC_ERROR.value,
            "outcome": "abstained",
            "steps": ["draft"],
        }
    provider = deps.answer_provider
    if provider is None:
        return {
            "outcome": "provider_error",
            "reason_code": AnswerReasonCode.PROVIDER_CONFIGURATION_ERROR.value,
            "error_class": "AnswerConfigurationError",
            "steps": ["draft"],
        }

    feedback = state.get("critic_feedback")
    update: dict[str, Any] = {"steps": ["draft"]}
    if feedback:
        update["regeneration_count"] = int(state.get("regeneration_count", 0)) + 1
    request = AnswerProviderRequest(
        question=state.get("question") or "",
        run_id=state.get("run_id") or f"answer-{uuid4()}",
        evidence=tuple(state.get("evidence") or ()),
        revision_hint=feedback or None,
    )
    provider_name = getattr(provider, "provider_name", None) or None
    try:
        result = provider.answer(request)
    except Exception as exc:  # noqa: BLE001 - sanitize typed and arbitrary provider failures.
        update.update(
            {
                "outcome": "provider_error",
                "reason_code": _provider_exception_reason(exc).value,
                "error_class": exc.__class__.__name__,
                "provider_name": provider_name,
                "draft": None,
            }
        )
        return update
    if not isinstance(result, AnswerProviderResult) or not isinstance(result.answer_text, str):
        update.update(
            {
                "outcome": "provider_error",
                "reason_code": AnswerReasonCode.PROVIDER_MALFORMED_RESULT.value,
                "error_class": AnswerValidationError.__name__,
                "provider_name": provider_name,
                "draft": None,
            }
        )
        return update
    resolved_name = result.provider_name or provider_name
    if not result.answer_text.strip():
        update.update(
            {
                "outcome": "provider_error",
                "reason_code": AnswerReasonCode.PROVIDER_BLANK_ANSWER.value,
                "error_class": AnswerValidationError.__name__,
                "provider_name": resolved_name,
                "trace_id": result.trace_id,
                "draft": None,
            }
        )
        return update
    update.update({"draft": result.answer_text, "provider_name": resolved_name, "trace_id": result.trace_id})
    return update


@observe(name="agent.critique", capture_input=False, capture_output=False)
def critique(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Ask the critic whether the draft is supported; any failure fails closed."""

    update = _critique(state, deps)
    _span_meta(
        {
            "critic_verdict": update.get("critic_verdict"),
            "critic_score": update.get("critic_score"),
            "critic_accepted": update.get("critic_accepted"),
            **_outcome_meta(update),
        }
    )
    return update


def _critique(state: State, deps: AgenticDeps) -> dict[str, Any]:

    if state.get("error_class") or state.get("outcome") == "provider_error":
        return {"steps": ["critique"]}
    critic = deps.critic
    if critic is None:
        return {
            "error_class": deps.critic_error_class or "CriticNotConfigured",
            "reason_code": AnswerReasonCode.CRITIC_ERROR.value,
            "outcome": "abstained",
            "critic_accepted": False,
            "steps": ["critique"],
        }
    request = CriticRequest(
        question=state.get("question") or "",
        draft=state.get("draft") or "",
        evidence=tuple(state.get("evidence") or ()),
        run_id=state.get("run_id") or f"critic-{uuid4()}",
    )
    try:
        verdict = critic.critique(request)
        if not isinstance(verdict, CriticVerdict):
            raise TypeError("critic returned a non-CriticVerdict result")
    except Exception as exc:  # noqa: BLE001 - any critic failure fails closed (D-02).
        error_class = "CriticValidationError" if isinstance(exc, TypeError) else exc.__class__.__name__
        return {
            "error_class": error_class,
            "reason_code": AnswerReasonCode.CRITIC_ERROR.value,
            "outcome": "abstained",
            "critic_accepted": False,
            "steps": ["critique"],
        }

    accepted = verdict.verdict == "supported" and verdict.faithfulness >= deps.critic_min_faithfulness
    update: dict[str, Any] = {
        "critic_verdict": verdict.verdict,
        "critic_score": float(verdict.faithfulness),
        "critic_accepted": accepted,
        "steps": ["critique"],
    }
    if not accepted:
        claims = [claim.strip() for claim in verdict.unsupported_claims if claim and claim.strip()]
        feedback = "\n".join(claims) if claims else _DEFAULT_CRITIC_FEEDBACK
        update["critic_feedback"] = feedback[:_CRITIC_FEEDBACK_MAX_CHARS]
    return update


@observe(name="agent.finalize", capture_input=False, capture_output=False)
def finalize(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Mark the critic-accepted draft as the answer (see ``_finalize``)."""

    update = _finalize(state, deps)
    _span_meta({"citation_count": len(update.get("citations") or ()), **_outcome_meta(update)})
    return update


def _finalize(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Mark the critic-accepted draft as the answer with service-owned citations.

    Citations come only from merged retrieval hits; provider or critic text can
    never add one. An answer with no citable evidence fails closed.
    """

    citations = _citations_from_hits(tuple(state.get("evidence") or ()))
    if not citations:
        return {
            "outcome": "abstained",
            "reason_code": AnswerReasonCode.RETRIEVAL_EXHAUSTED.value,
            "citations": (),
            "steps": ["finalize"],
        }
    return {
        "outcome": "answered",
        "reason_code": AnswerReasonCode.ANSWERED.value,
        "citations": citations,
        "steps": ["finalize"],
    }


@observe(name="agent.abstain", capture_input=False, capture_output=False)
def abstain(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Terminal abstention (see ``_abstain``)."""

    update = _abstain(state, deps)
    merged = {**dict(state), **update}
    _span_meta(
        {
            "reason_code": merged.get("reason_code"),
            "error_class": merged.get("error_class"),
            "outcome": merged.get("outcome"),
        }
    )
    return update


def _abstain(state: State, deps: AgenticDeps) -> dict[str, Any]:
    """Terminal abstention; picks a reason code when no node set one.

    A provider_error outcome is preserved so the result builder reports it as
    PROVIDER_ERROR rather than a silent abstention.
    """

    update: dict[str, Any] = {"steps": ["abstain"]}
    if state.get("outcome") != "provider_error":
        update["outcome"] = "abstained"
    if not state.get("reason_code"):
        # Critic rejection is checked first: evidence can turn strong on the
        # last retrieval round and the draft still be rejected afterwards.
        if state.get("critic_verdict") is not None and not state.get("critic_accepted"):
            reason = AnswerReasonCode.CRITIC_REJECTED
        else:
            # rewrite_exhausted or retrieval_round >= MAX_RETRIEVAL_ROUNDS; also the
            # conservative fallback for any other unlabelled abstention.
            reason = AnswerReasonCode.RETRIEVAL_EXHAUSTED
        update["reason_code"] = reason.value
    return update


__all__ = ["abstain", "critique", "decompose", "draft", "evaluate", "finalize", "retrieve", "rewrite"]
