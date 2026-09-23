# Phase 6: Agentic RAG & Observability - Pattern Map

**Mapped:** 2026-09-23
**Files analyzed:** 33 (18 new source/test files + 15 modified)
**Analogs found:** 31 / 33 (2 have partial or no analog: `src/rag/agentic/graph.py` LangGraph wiring and `trace_session`/`mask` Langfuse propagation)

## Locked decisions for this run (from the orchestrator, treat as binding)

1. **Pin `langgraph==1.0.1`**, not `>=1.1`. Reason: langchain-core<1 / RAGAS 0.4.3. Raise langfuse to `>=3.9,<4.0` and add `anthropic>=1,<2`. Add a pin-guard test modelled on `tests/test_tracing.py::test_langfuse_v3_pinned` (lines 14-20).
2. **Critic fails closed.** With no Anthropic key the critic abstains (`CRITIC_ERROR`). The Gemini critic runs only when explicitly selected with `critic_provider="gemini"`. It is never an automatic fallback.
3. **Chat tab defaults to the agentic pipeline** (`rag_pipeline="agentic"`). The eval harness (`src/eval/ragas_quality.py`, `retrieval_eval_runner.py`) stays on linear `answer_question` unless told otherwise.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` (mod) | config | — | `pyproject.toml` lines 9-32 | exact |
| `src/config.py` (mod) | config | — | `src/config.py` lines 26-45 | exact |
| `src/rag/models.py` (mod) | model (DTO) | transform | self, lines 22-69 | exact |
| `src/rag/agentic/__init__.py` | package export | — | `src/rag/__init__.py` | exact |
| `src/rag/agentic/state.py` | model (state + limits) | transform | `src/rag/models.py` (frozen dataclass + constants) | partial |
| `src/rag/agentic/routing.py` | utility (pure routers) | transform | `src/rag/service.py` `_answer_reason_for_weak_evidence` / `_provider_exception_reason` lines 276-284 | partial |
| `src/rag/agentic/nodes.py` | service (node fns) | request-response | `src/rag/service.py` `answer_question` lines 68-202 | exact (logic source) |
| `src/rag/agentic/graph.py` | service (orchestrator) | request-response | `src/rag/service.py` lines 1-67, 294-331 (decorator, seams, trace) | role-match (no LangGraph analog) |
| `src/rag/agentic/decompose.py` | utility | transform | `src/retrieval/retriever.py` `_TOKEN_RE`/`_STOPWORDS` lines 47-64; `src/rag/gemini.py` prompt/fence helpers | partial |
| `src/rag/agentic/rewrite.py` | utility | transform | same as decompose | partial |
| `src/rag/critic.py` | provider adapter | request-response (external API) | `src/rag/gemini.py` + `src/rag/providers.py` | exact |
| `src/extraction/models.py` (mod) | model | — | self, lines 51-61 | exact |
| `src/extraction/review.py` | repository | CRUD (SQLite transaction) | `src/extraction/repository.py` lines 60-131, 313-341, 393-427, 504-520 | exact |
| `src/db/schema.py` (mod) | migration | — | self, `SCHEMA_SQL` + `init_db` lines 363-393 | exact |
| `src/dashboard/review.py` | component (Streamlit tab) | request-response (form submit) | `src/dashboard/compliance.py` (selectbox/detail/image) + `src/dashboard/chat.py` (injectable fn seams) | exact |
| `src/dashboard/chat.py` (mod) | component | request-response | self | exact |
| `src/dashboard/__init__.py` (mod) | package export | — | self | exact |
| `src/app.py` (mod) | entry point | — | self, line 44 | exact |
| `src/tracing.py` (mod) | utility (cross-cutting) | event-driven (spans) | self | exact |
| `src/rag/gemini.py` (mod, generation span) | provider | request-response | self lines 76-117 + `src/extraction/gemini.py::_extract_usage_metadata` lines 402-425 | exact |
| `src/retrieval/retriever.py`, `src/rag/service.py`, `src/extraction/pipeline.py` (mod, phase tag) | service | — | own `_safe_update_trace_metadata` helpers | exact |
| `src/pipeline/ingest.py` (mod) | CLI entry | batch | self lines 33-44 (hard-coded `"phase1"` tag, to be replaced) | exact |
| `src/extraction/cli.py`, `src/retrieval/cli.py`, `src/eval/cli.py` (mod, trace_session) | CLI entry | batch | `src/eval/cli.py` lines 49-58 | exact |
| `.env.example` (mod) | config | — | existing file | exact |
| `tests/rag/__init__.py`, `tests/rag/agentic/__init__.py` | test pkg | — | `tests/eval/__init__.py` (empty) | exact |
| `tests/rag/agentic/conftest.py` | test fixtures | — | `tests/retrieval/visual/conftest.py` + `FakeAnswerProvider` in `tests/test_answer_service.py` lines 27-46 | exact |
| `tests/rag/agentic/test_stack_pins.py` | test | — | `tests/test_tracing.py` lines 14-28 | exact |
| `tests/rag/agentic/test_routing.py` | test (pure unit) | — | `tests/test_extraction_risk.py` (pure fn tests) | role-match |
| `tests/rag/agentic/test_graph.py` | test (integration, fakes) | — | `tests/test_answer_service.py` | exact |
| `tests/rag/agentic/test_decompose_rewrite.py` | test | — | `tests/test_retriever.py` | role-match |
| `tests/rag/test_critic_provider.py` | test (fake SDK client) | — | `tests/test_answer_provider_gemini.py` lines 1-70 | exact |
| `tests/test_review_repository.py` | test (tmp sqlite) | — | `tests/test_extraction_persistence.py` lines 1-135 | exact |
| `tests/test_dashboard_review_tab.py` | test (FakeStreamlit) | — | `tests/test_compliance_dashboard.py` lines 579-641 + `tests/test_chat_dashboard.py` lines 24-100 | exact |
| `tests/test_tracing_phase.py` | test | — | `tests/test_tracing.py` lines 44-65, 288-351 | exact |
| `tests/test_db.py`, `tests/test_app.py`, `tests/test_chat_dashboard.py`, `tests/test_dashboard_chat_tab.py` (extend) | test | — | self | exact |

---

## Pattern Assignments

### `pyproject.toml` (config)

**Analog:** `pyproject.toml` lines 9-32. The dependency list already carries inline justification comments for the RAGAS/langchain pins (lines 24-31). Follow that style:

```toml
    "langfuse>=3.0,<4.0",            # line 12 -> change to ">=3.9,<4.0" (propagate_attributes)
    ...
    # ragas 0.4.3 requires the langchain 0.3.x stack (langchain 1.x removed the
    # ChatVertexAI / ContextOverflowError symbols ragas imports at load time).
    "ragas==0.4.3",
    "langchain>=0.3,<1",
    "langchain-core>=0.3,<1",
```
Add `"langgraph==1.0.1",` with a comment ("last release compatible with langchain-core<1; see 06-RESEARCH Pitfall 1") and `"anthropic>=1,<2",`. Pytest config at lines 44-49 (`addopts = "-x --tb=short"`, `gpu` marker) stays unchanged.

---

### `src/config.py` (config)

**Analog:** `src/config.py` lines 26-45. Use one `Field` per setting with a `description`, and a bounded float with `ge/le`:

```python
    gemini_api_key: str = Field(default="", description="Gemini API key for live extraction and answer providers")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Gemini model for live SDF extraction and answers")
    extraction_low_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence below which extracted fields require human review",
    )
    ...
    retrieval_mode: str = Field(
        default="text-only",
        description=(...multi-line rationale...),
    )
```
New fields: `anthropic_api_key: str = ""`, `critic_provider: str = "anthropic"` (description must say the `"gemini"` value is an explicit opt-in and there is no automatic fallback), `critic_model: str = "claude-sonnet-4-6"`, `critic_min_faithfulness: float = Field(0.8, ge=0, le=1)`, `rag_pipeline: str = "agentic"` (Chat default, per locked decision 3), `pipeline_phase: str = "phase2"`. HITL queue threshold reuses the existing `extraction_low_confidence_threshold`. Keep `get_settings()` with `lru_cache` (lines 48-51). Tests that change settings must call `get_settings.cache_clear()`.

---

### `src/rag/models.py` (modify: enum + diagnostics)

**Analog:** self. Enum at lines 22-36, diagnostics at lines 57-69:

```python
class AnswerReasonCode(StrEnum):
    ...
    PROVIDER_CONFIGURATION_ERROR = "provider_configuration_error"
    # add: RETRIEVAL_EXHAUSTED = "retrieval_exhausted", CRITIC_REJECTED = "critic_rejected", CRITIC_ERROR = "critic_error"

@dataclass(frozen=True)
class AnswerDiagnostics:
    ...
    evidence_reason: str
    error_class: str | None = None
    # append ONLY defaulted trailing fields:
    # pipeline: str = "linear"; retrieval_rounds: int = 0; regeneration_count: int = 0
    # sub_query_count: int = 0; critic_verdict: str | None = None; critic_score: float | None = None
```
Existing constructors pass keyword args (`service.py` lines 189-199, `chat.py` lines 157-167, `tests/test_chat_dashboard.py::_diagnostics` line 101), so defaulted trailing fields do not break them.

---

### `src/rag/agentic/__init__.py` (package export)

**Analog:** `src/rag/__init__.py`. It uses explicit imports plus an alphabetized `__all__`. Export `answer_question_agentic` and `build_agentic_graph` only. **Do not** import `src.rag.agentic` from `src/rag/__init__.py` at module level unless graph.py keeps `langgraph` lazy (see graph.py below). `src.rag` must stay import-safe offline (`tests/test_answer_provider_gemini.py` lines 10-17 prove this for Gemini).

---

### `src/rag/agentic/state.py` (state model + limits)

**Analog (constants + typed containers):** `src/rag/models.py` (frozen dataclasses, `StrEnum`) and `src/rag/service.py` lines 49-50 (`_DEFAULT_TOP_K = 5` module constants).

Use the RESEARCH Pattern 2 `AgenticState(TypedDict, total=False)` verbatim, with `steps: Annotated[list[str], operator.add]` and the module constants `MAX_RETRIEVAL_ROUNDS = 3`, `MAX_REGENERATIONS = 1`, `GRAPH_RECURSION_LIMIT = 30`. Put `AgenticDeps` here (or in graph.py) as a `@dataclass(frozen=True)`, mirroring `AnswerProviderRequest` (`src/rag/providers.py` lines 33-43). Fields: `db_path`, `retrieve_fn` (default `retrieve_evidence`), `answer_provider`, `critic`, `decomposer`, `rewriter`, `top_k`, `critic_min_faithfulness`. This module must not import langgraph.

---

### `src/rag/agentic/routing.py` (pure routers)

**Analog:** `src/rag/service.py` lines 276-284. These are small pure mapping functions with no I/O:

```python
def _answer_reason_for_weak_evidence(reason: RetrievalEvidenceReason) -> AnswerReasonCode:
    return _RETRIEVAL_TO_ANSWER_REASON.get(reason, AnswerReasonCode.RETRIEVAL_ERROR)

def _provider_exception_reason(exc: BaseException) -> AnswerReasonCode:
    for exc_type, reason_code in _PROVIDER_ERROR_REASON_BY_EXCEPTION:
        if isinstance(exc, exc_type):
            return reason_code
    return AnswerReasonCode.PROVIDER_EXCEPTION
```
Copy `route_after_evaluate` / `route_after_critique` from RESEARCH Pattern 2. Return string literals that match the `add_conditional_edges` path maps. `error_class` set means `"abstain"` (fail closed).

---

### `src/rag/agentic/nodes.py` (node functions, request-response)

**Analog:** `src/rag/service.py::answer_question` lines 68-202. Each linear step becomes a node, and each node keeps the same error handling.

**Imports pattern** (service.py lines 9-27):
```python
from uuid import uuid4
from typing import Any

from src.rag.models import (AnswerCitation, AnswerDiagnostics, AnswerReasonCode, AnswerResult, AnswerStatus)
from src.rag.providers import (AnswerConfigurationError, AnswerProvider, AnswerProviderRequest,
                               AnswerProviderResult, AnswerValidationError)
from src.retrieval import RetrievalEvidenceReason, RetrievalHit, retrieve_evidence
from src.tracing import observe, safe_update_current_trace
```

**retrieve node: wrap retrieval in try/except and map to a reason code** (lines 90-110):
```python
    try:
        evidence = retrieve_evidence(db_path, question, top_k=bounded_top_k, candidate_limit=candidate_limit,
                                     min_top_score=min_top_score, min_query_term_coverage=min_query_term_coverage,
                                     min_hit_count=min_hit_count)
    except Exception as exc:  # noqa: BLE001 - service boundary must not crash callers on retrieval failures.
        result = _abstained_result(reason_code=AnswerReasonCode.RETRIEVAL_ERROR, ..., error_class=exc.__class__.__name__)
```
In the node, call `deps.retrieve_fn(deps.db_path, subq, top_k=deps.top_k)` once per active sub-query. Store `is_strong`, `top_score`, `run_id`, `reason_code.value`, and hits merged/deduped by `(doc_id, page_num)`, keeping the max `score`. **Do not** pass relaxed thresholds on retry (the gate defaults are `DEFAULT_MIN_TOP_SCORE = 0.45`, `DEFAULT_MIN_QUERY_TERM_COVERAGE = 0.50` in `src/retrieval/retriever.py` lines 53-55). `retrieve_evidence` returns `EvidenceGateResult` (alias `RetrievalResult`, `src/retrieval/models.py` lines 154-188) with `is_strong`, `reason_code`, `hits`, `top_score`, `run_id`.

**draft node: provider call and result validation** (lines 137-182):
```python
    run_id = evidence.run_id or f"answer-{uuid4()}"
    request = AnswerProviderRequest(question=question, run_id=run_id, evidence=evidence.hits)
    try:
        provider_result = provider.answer(request)
    except Exception as exc:  # noqa: BLE001 - sanitize typed and arbitrary provider failures.
        result = _provider_error_result(reason_code=_provider_exception_reason(exc), ...,
                                        error_class=exc.__class__.__name__)
    if not isinstance(provider_result, AnswerProviderResult) or not isinstance(provider_result.answer_text, str):
        ... PROVIDER_MALFORMED_RESULT
    answer_text = provider_result.answer_text.strip()
    if not answer_text:
        ... PROVIDER_BLANK_ANSWER
```
Provider failures set `outcome="provider_error"` + `reason_code` + `error_class` in state and route to a terminal. They never raise out of the graph. For regeneration, the critic feedback goes only into the in-memory prompt. Because `AnswerProviderRequest` is frozen with 3 fields, pass the feedback either through an optional defaulted field `revision_hint: str | None = None` appended to `AnswerProviderRequest` (then extend `_build_contents` in `src/rag/gemini.py` lines 133-153) or by folding it into `question`. Prefer the defaulted field.

**finalize node: citations are service-owned** (lines 184-217). Reuse, do not duplicate:
```python
    citations = _citations_from_hits(evidence.hits[:bounded_top_k])
```
Import `_citations_from_hits`, `_abstained_result`, `_provider_error_result` from `src.rag.service`, or move them to a shared private module and re-import them in service.py. Abstention text must match service.py line 231 exactly so the dashboard/eval treat it uniformly.

**terminal builders** (lines 220-273): `_abstained_result(...)` / `_provider_error_result(...)` keyword-only constructors. Extend them with the new diagnostics fields as kwargs (defaulted).

---

### `src/rag/agentic/graph.py` (orchestrator)

**Analog:** `src/rag/service.py` for the decorator, seams, and trace update. RESEARCH "Graph builder" (lines 406-452) for the LangGraph wiring, which has no codebase analog.

**Module-level test seams** (service.py lines 29-47). Copy this block with a new allowlist:
```python
# Injectable test seams: tests monkeypatch both symbols. langfuse_context=None
# means "resolve the live v3 client lazily inside src.tracing".
_LANGFUSE_AVAILABLE: bool = True
langfuse_context: Any | None = None

_ANSWER_TRACE_ALLOWED_KEYS = frozenset({"boundary", "answer_status", "reason_code", "run_id", "provider_name",
                                        "trace_id", "top_score", "citation_count", "evidence_reason", "error_class"})
```
Agentic allowlist = the above + `pipeline`, `retrieval_round`/`retrieval_rounds`, `sub_query_count`, `regeneration_count`, `critic_verdict`, `critic_score`. **Never** question, draft, critic feedback, or unsupported_claims.

**Entry decorator + signature compat** (service.py lines 68-79):
```python
@observe(name="rag_answer_question")
def answer_question(db_path: str, question: str, *, provider: AnswerProvider | None, top_k: int = _DEFAULT_TOP_K, ...) -> AnswerResult:
```
New: `@observe(name="rag.agentic", capture_input=False, capture_output=False)` and `def answer_question_agentic(db_path, question, *, provider, critic=None, top_k=5, **kw) -> AnswerResult`. The positional `(db_path, question, provider=...)` call shape must match `src/eval/ragas_quality.py` line 204 (`answer_fn(db_path, query_text, provider=provider)`) and `src/dashboard/chat.py` line 132 (`answer_fn(db_path, prompt, provider=provider)`). When `critic` is None, resolve it with `build_critic_provider(settings)`. A configuration failure there leads to abstain with `CRITIC_ERROR` (locked decision 2), and must not raise.

**Trace-metadata tail** (service.py lines 294-328). Copy `_update_answer_trace_metadata` / `_safe_update_trace_metadata` with the agentic allowlist and `tags=["rag", "agentic"]`.

**Lazy langgraph import:** keep `from langgraph.graph import END, START, StateGraph` and `from langgraph.errors import GraphRecursionError` **inside functions**. This matches the lazy SDK import pattern in `src/rag/gemini.py` lines 125-129 and `src/rag/providers.py` lines 79-82.

---

### `src/rag/agentic/decompose.py` / `rewrite.py` (transform utilities)

**Analog:** tokenization in `src/retrieval/retriever.py` lines 47-64 (`_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")`, `_STOPWORDS` frozenset), plus `_strip_simple_fences` in `src/rag/gemini.py` lines 178-182:
```python
def _strip_simple_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    return re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*|\s*```$", "", stripped).strip()
```
Deterministic first: `is_compound()` heuristic and a domain-synonym table as a module-level `dict[str, tuple[str, ...]]` constant. The optional LLM decomposer/rewriter is an injected callable. Malformed output falls back to `[question]` and is never an abstain. Cap at 3 sub-queries. Use `SDFFieldName` values (`src/extraction/models.py` lines 11-19) for the "≥2 field names" compound signal.

---

### `src/rag/critic.py` (provider adapter, external API)

**Analogs:** `src/rag/providers.py` (protocol, typed errors, lazy builder) and `src/rag/gemini.py` (adapter with injectable client, retry, sanitized errors).

**Typed errors with reason_code** (providers.py lines 15-30):
```python
class AnswerConfigurationError(RuntimeError):
    """Raised when a live answer provider is not configured safely."""
    reason_code = "provider_configuration_error"
```
→ `CriticConfigurationError`, `CriticProviderError`, `CriticValidationError`, all with `reason_code = "critic_error"`.

**Request dataclass + Protocol** (providers.py lines 33-61): `CriticRequest(question, draft, evidence: tuple[RetrievalHit, ...], run_id)` frozen, plus `class CriticProvider(Protocol): provider_name: str; def critique(self, request) -> CriticVerdict`.

**Lazy builder** (providers.py lines 64-83):
```python
def build_answer_provider(provider: str | AnswerProvider | None = None, **kwargs: object) -> AnswerProvider | None:
    if provider is None:
        return None
    if not isinstance(provider, str):
        return provider
    provider_name = provider.strip().lower()
    if not provider_name:
        return None
    if provider_name == "gemini":
        from src.rag.gemini import GeminiAnswerProvider
        return GeminiAnswerProvider(**kwargs)
    raise AnswerConfigurationError(f"Unsupported answer provider: {provider_name}")
```
→ `build_critic_provider(name)` with `"anthropic"` (default) and `"gemini"` (explicit opt-in only). A missing Anthropic key raises `CriticConfigurationError`. **Do not** silently fall back to Gemini.

**Adapter constructor with injectable client + key check** (gemini.py lines 52-74):
```python
    def __init__(self, *, api_key: str | None = None, model: str | None = None, client: Any | None = None,
                 client_factory: Callable[[str], Any] | None = None, max_attempts: int = 2) -> None:
        settings = get_settings()
        self.model = (model or settings.gemini_model or DEFAULT_GEMINI_ANSWER_MODEL).strip()
        ...
        self._api_key = (api_key if api_key is not None else settings.gemini_api_key).strip()
        if self._client is None and self._client_factory is None and not self._api_key:
            raise AnswerConfigurationError("GEMINI_API_KEY is required to use the Gemini answer provider.")
```

**Sanitized call + bounded retry** (gemini.py lines 76-130, 185-193): copy `_generate_content_with_retry` (tenacity `Retrying(stop_after_attempt, wait_none, retry_if_exception(_is_retryable_provider_exception), reraise=True)`), the `except Exception as exc: raise ...ProviderError("... error_class={exc.__class__.__name__}") from exc` sanitization, and the lazy `_get_client()` SDK import. For Anthropic: `anthropic.Anthropic(api_key=...)`, `client.messages.create(model=, max_tokens=512, system=, messages=[...])`. **No `temperature` kwarg** (anthropic 1.x). Parse with `CriticVerdict.model_validate_json(_strip_simple_fences(text))`. A pydantic `ValidationError` becomes `CriticValidationError`.

**Evidence prompt** (gemini.py lines 133-160): reuse `_build_contents`'s `<evidence index= doc_id= filename= page= score=>` block style and `_bounded_evidence` (2000-char cap, `_MAX_EVIDENCE_ITEMS = 5`).

**Pydantic model style** (from `src/extraction/models.py` line 40 `model_config = ConfigDict(extra="forbid", frozen=True)`): the `CriticVerdict` in RESEARCH uses `extra="ignore"` because LLM output is untrusted. Keep that, with `Literal[...]` verdict and `Field(ge=0.0, le=1.0)`.

---

### `src/extraction/models.py` (modify `SourceEvidence.evidence_type`)

**Analog:** self lines 51-61:
```python
    evidence_type: str = Field(
        default="text",
        description="'text' = verbatim-grounded; 'visual' = image-grounded, page-cited, review-flagged.",
    )

    @field_validator("evidence_type")
    @classmethod
    def validate_evidence_type(cls, value: str) -> str:
        if value not in {"text", "visual"}:
            raise ValueError("evidence_type must be 'text' or 'visual'")
        return value
```
Add `"human"` to the set and to the description. Consumers to re-check (grep result): `src/extraction/pipeline.py` lines 583-614, `src/extraction/repository.py` lines 389, 500, 516, `src/db/schema.py` `evidence_type`/`source_evidence_type` columns (TEXT, no CHECK, so no migration is needed). The `ExtractedField` validator (lines 104-117) requires `verbatim_span` for non-abstained fields, so a CORRECT action must set a span.

---

### `src/extraction/review.py` (repository, CRUD transaction)

**Analog:** `src/extraction/repository.py`.

**Imports + module docstring convention** (lines 1-16):
```python
"""SQLite persistence helpers for validated SDF extraction records.

Repository boundary: callers pass already-validated Pydantic models. All SQL uses
parameterized placeholders; source evidence text is persisted only in explicit
evidence columns and is never logged here.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from datetime import datetime
from typing import Any

from src.db.schema import _connect
from src.extraction.models import ExtractedField, ReviewState, SDFExtractionRecord, SDFFieldName, SourceEvidence
```

**Frozen DTO for dashboard rows** (lines 45-57, `ExtractionRunSummary`) is the pattern for `ReviewQueueItem` / `ReviewOutcome`.

**Single-transaction write with rollback** (lines 78-102):
```python
    conn = _connect(db_path)
    try:
        ...writes...
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Row-factory read** (lines 105-131): `conn.row_factory = sqlite3.Row`, parameterized `WHERE doc_id = ?`. Use this shape for `list_review_queue` (join `documents` for `filename`).

**Latest-row field update, reuse the private helpers:** `_upsert_extraction_field(conn, doc_id, field, trace_id)` (lines 313-341) and `_upsert_compliance_record(conn, record)` (lines 393-427) write **only** the latest tables. `apply_field_review` calls those two private helpers directly inside its own transaction. It **must not** call `upsert_extraction_record` (lines 78-102), which also writes `extraction_history` / `compliance_record_history` when `run_id` is set (Pitfall 7).

**Load current record:** `get_extraction_record(db_path, doc_id)` (lines 105-131) opens its own connection. Either call it before opening the write transaction, or reuse `_get_extraction_record_with_queries(conn, ...)` (line 207) inside the same connection.

**Row → model** (lines 504-520): `_field_from_row` shows the `SourceEvidence(page_num=..., evidence_type=row["evidence_type"] or "text")` reconstruction. `ExtractedField` has `validate_assignment=True`, so build the corrected field with `field.model_copy(update=...)` then re-validate via `ExtractedField.model_validate(...)`.

**Risk recompute** (`src/extraction/risk.py` lines 23-49):
```python
def compute_record_risk(record: SDFExtractionRecord, *, today: date) -> RiskMetadata:
    return compute_fields_risk(record.fields, today=today)
```
Then `record.model_copy(update={"risk_level": m.risk_level, "risk_reason": m.risk_reason, "compliance_status": m.compliance_status, "age_days": m.age_days, "fields": new_fields})` → `_upsert_compliance_record(conn, record)`.

**Date parsing for reviewer input:** `src/extraction/pipeline.py::_parse_iso_date` lines 693-701 for ISO. Use the `dateutil` fallback from `src/eval/extraction_metrics.py` lines 86-97 (lazy `from dateutil import parser as date_parser`, preserving explicit ISO/`YYYY-MM` precision). Reject unparseable dates with a typed error **before** any write.

**Trace:** decorate `apply_field_review` with `@observe(name="hitl.review", capture_input=False, capture_output=False)`. Copy the extraction trace helper shape (`src/extraction/pipeline.py` lines 415-427) with an allowlist of `boundary, doc_id, field_name, action, previous_review_state, review_id, error_class`. Values and notes must not be added.

---

### `src/db/schema.py` (migration)

**Analog:** self.
- Add the `extraction_reviews` `CREATE TABLE IF NOT EXISTS` (RESEARCH Pattern 5 SQL) to `SCHEMA_SQL`, after `compliance_record_history` (around line 155). Use the table style of `extractions` (lines 46-64): `REFERENCES documents(doc_id) ON DELETE CASCADE`, timestamps default `strftime('%Y-%m-%dT%H:%M:%SZ', 'now')`.
- Add `CREATE INDEX IF NOT EXISTS idx_extraction_reviews_doc_field ...` to `POST_MIGRATION_INDEX_SQL` (lines 363-367).
- Because the table is brand-new, `CREATE TABLE IF NOT EXISTS` is already idempotent, so no `_migrate_*` helper is needed. If columns are later added, follow `_migrate_visual_index_runs_table` (lines 470-486) + `_table_columns` (lines 489-492).
- `init_db` (lines 377-393) already wraps everything in commit/rollback. Test idempotency by calling `init_db` twice (extend `tests/test_db.py`).

---

### `src/dashboard/review.py` (Streamlit component, form submit)

**Analogs:** `src/dashboard/compliance.py` (layout, selectbox detail, page image, safe text) and `src/dashboard/chat.py` (injectable function seams, session-state keys, bounded text, safe error UI).

**Imports** (compliance.py lines 7-22 + chat.py lines 9-15):
```python
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

import streamlit as st

from src.dashboard.ui import render_empty_state, render_section_divider, render_tab_header
from src.db.queries import get_page_image
from src.extraction.review import (...)   # list_review_queue, apply_field_review, ReviewAction
```

**Injectable seams + session keys** (chat.py lines 28-36, 54-68):
```python
_CHAT_MESSAGES_KEY = "pfizer_chat_messages"
AnswerFn = Callable[..., AnswerResult]

def render_chat_tab(db_path: str | None = None, provider_factory: ProviderFactory | None = None,
                    answer_fn: AnswerFn | None = None) -> None:
    _initialize_chat_state()
    resolved_db_path = _resolve_db_path(db_path)
    active_answer_fn = answer_fn or default_answer_question
```
→ `render_review_tab(db_path=None, *, queue_fn=None, apply_fn=None)`, `_REVIEW_SELECTED_KEY = "pfizer_review_selected"`.

**Tab body flow** (compliance.py lines 160-205): `render_tab_header(...)` → load → `render_empty_state(...)` when empty and return → metrics via `st.columns(n)` + `.metric` (lines 360-370) → `st.dataframe(rows, hide_index=True, width="stretch")` (lines 198-202). Note that the FakeStreamlit asserts these exact kwargs (test lines 621-624).

**Selected-item detail + page image** (compliance.py lines 421-448):
```python
    options = [str(row.get("doc_id") or f"row-{index + 1}") for index, row in enumerate(rows)]
    selected_doc_id = st.selectbox("Select a document", options=options)
    ...
    st.markdown(f"**Source verbatim span:** {_safe_detail_text(selected_row.get('source_verbatim_span'))}")
    image = _load_selected_source_image(db_path, selected_row)
    if image is None:
        st.caption("No source preview available for the selected document/page.")
    else:
        st.image(image, caption=selected_row.get("source_page_label") or "Source page")

def _load_selected_source_image(db_path, row):
    ...
    try:
        return get_page_image(db_path, str(doc_id), int(source_page))
    except (OSError, TypeError, ValueError, sqlite3.Error):
        return None
```
Queue options must be `f"{doc_id}::{field_name}"` so keys are unique (Pitfall 9).

**Bounded text** (compliance.py lines 451-459 `_safe_detail_text`, 1000-char cap. chat.py lines 280-288 `_bounded_text`). **Page display is 1-based**. See `_source_page_display` (compliance.py line 487). Stored pages are 0-indexed (`SourceEvidence.page_num` "0-indexed"), so `number_input` shows +1 and subtracts 1 on submit.

**Safe error UI** (chat.py lines 124-139): wrap `apply_fn(...)` in `try/except` for typed errors and `Exception`, and render only `exc.__class__.__name__`/reason code via `st.error`, never `str(exc)`. On success: `st.success(...)`, flush Langfuse (Pitfall 11), then `st.rerun()`. Wrap the submit in `trace_session(phase=settings.pipeline_phase, ...)`.

**Form widgets:** there is no existing `st.form` usage. Use RESEARCH Pattern 6 (`st.form(key=f"review_{doc_id}_{field}")`, `st.radio`, `st.text_input`, `st.number_input`, `st.text_area`, `st.form_submit_button`).

---

### `src/dashboard/chat.py` (modify)

**Analog:** self.
- `_REASON_HINTS` (lines 39-51): add entries for `RETRIEVAL_EXHAUSTED`, `CRITIC_REJECTED`, `CRITIC_ERROR`. The `CRITIC_ERROR` hint must mention configuring `ANTHROPIC_API_KEY` (or opting into `CRITIC_PROVIDER=gemini`). The fallback in `_hint_for_reason` (lines 259-264) otherwise renders a generic message.
- Pipeline selection: `active_answer_fn = answer_fn or default_answer_question` (line 68) becomes `answer_fn or _default_answer_fn()`. `_default_answer_fn()` reads `get_settings().rag_pipeline` and returns `answer_question_agentic` when `"agentic"` (the default, locked decision 3), otherwise `answer_question`. Lazy-import the agentic module there, the same way `_resolve_db_path` lazy-imports `get_settings` (lines 108-114). Existing tests inject `answer_fn`, so they are unaffected.
- `_diagnostics_payload` (lines 191-202) and `_render_diagnostics` label tuple (lines 245-256): append `pipeline`, `retrieval_rounds`, `regeneration_count`, `sub_query_count`, `critic_verdict`, `critic_score`. Pass them through `_safe_optional_text` / `round(float(...), 3)`, handling `None`.
- `_answer_prompt` (lines 117-139): wrap the `answer_fn(...)` call in `trace_session(phase=PHASE_TAGS[pipeline], session_id=<st.session_state uuid>)` and flush afterwards.

---

### `src/app.py` / `src/dashboard/__init__.py` (modify)

**Analog:** `src/app.py` lines 18, 44-56:
```python
from src.dashboard import render_chat_tab, render_compliance_tab, render_eval_tab
...
tab_compliance, tab_chat, tab_eval = st.tabs(["Compliance", "Chat", "Eval"])
with tab_eval:
    st.header("Evaluation")
    render_eval_tab(get_settings().db_path)
```
Add `tab_review` → `st.header("Human Review")` + `render_review_tab(get_settings().db_path)`. Update the module docstring tab list (lines 3-7) and `src/dashboard/__init__.py` `__all__`.

---

### `src/tracing.py` (modify: cross-cutting)

**Analog:** self.

**Optional-SDK guarded import** (lines 59-76): new Langfuse symbols (`propagate_attributes`, `langfuse.langchain.CallbackHandler`) must be imported **inside** functions under `try/except Exception`, the same way `_LANGFUSE_AVAILABLE` handling works. Never at module top level. `langfuse.langchain` pulls langchain-core.

**Client init to extend with `mask=`** (lines 149-172):
```python
    try:
        _Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return True
    except Exception:
        return False
```
Add `mask=mask_trace_payload`.

**Value sanitization to reuse in `mask_trace_payload`** (lines 82-146): `_TRACE_VALUE_MAX_CHARS`, `_SECRET_VALUE_RE`, `_bounded_string`, `_safe_trace_value`, `filter_trace_metadata`. The mask should walk Mappings and keep only a global safe-key set. Long strings become `"[redacted:len=N]"`, and objects/dataclasses/bytes are dropped.

**No-raise update helper to mirror for `safe_update_current_span`, and to extend with the phase tag** (lines 185-224):
```python
    trace_context = context if context is not None else _get_langfuse_context()
    if trace_context is None or not hasattr(trace_context, "update_current_trace"):
        return False
    safe_metadata = filter_trace_metadata(metadata, allowed_metadata_keys or frozenset())
    safe_tags: list[str] = []
    ...
    try:
        trace_context.update_current_trace(**update_kwargs)
    except Exception:
        return False
    return True
```
Pitfall 10: append the current `_CURRENT_PHASE` ContextVar value to `safe_tags` (if set) before the `if not safe_metadata and not safe_tags` check. `trace_session`, `build_callback_handler`, `flush_traces` follow RESEARCH "Langfuse v3 session + tags" and must never raise. Use `nullcontext()` fallback.

---

### `src/rag/gemini.py` (modify: generation span)

**Analog:** self lines 103-117 + `src/extraction/gemini.py::_extract_usage_metadata` lines 402-425 (reads `usage_metadata.prompt_token_count` / `candidates_token_count` / `total_token_count`). Wrap `answer` (or `_generate_content`) with `observe(name="generation.draft", as_type="generation", capture_input=False, capture_output=False)`. Report `update_current_generation(model=self.model, usage_details={"input": n, "output": m})` through a no-raise tracing helper. Keep the existing `config={"temperature": 0}` for Gemini (line 117). The no-temperature rule is Anthropic-only.

---

### Phase-tag retrofit: `src/retrieval/retriever.py`, `src/rag/service.py`, `src/extraction/pipeline.py`, `src/pipeline/ingest.py`

**Analog:** each file's existing `_safe_update_trace_metadata` helper, e.g. `src/retrieval/retriever.py` lines 633-643:
```python
def _safe_update_trace_metadata(metadata: dict[str, Any]) -> None:
    if not _LANGFUSE_AVAILABLE:
        return
    safe_update_current_trace(
        tags=["retrieval", "evidence"],
        metadata=metadata,
        allowed_metadata_keys=_RETRIEVAL_TRACE_ALLOWED_KEYS,
        context=langfuse_context,
    )
```
No per-module change is needed if `safe_update_current_trace` auto-appends the phase tag. **Exception:** `src/pipeline/ingest.py` lines 38-44 hard-codes `tags=["phase1", "ingestion"]`. Replace it with `["ingestion"]` and let `trace_session` / the ContextVar supply the phase. The existing `@observe(name=...)` decorators (`retrieval_evidence_gate` line 440, `rag_answer_question` line 68, `sdf_extract_document` pipeline line 312, `ingest_document` line 76) keep their names. The global mask handles their default `capture_input=True` leak.

---

### CLI entry points: `src/extraction/cli.py`, `src/retrieval/cli.py`, `src/eval/cli.py`, `src/pipeline/ingest.py`

**Analog:** `src/eval/cli.py` lines 49-58, which initializes tracing best-effort before the observed call:
```python
    try:
        from src.tracing import _ensure_langfuse_initialized

        _ensure_langfuse_initialized()
    except Exception:  # noqa: BLE001 - tracing is best-effort; never block the eval.
        pass
```
Replace or augment with `with trace_session(phase=get_settings().pipeline_phase, tags=["cli", "<command>"]):` around the command body (e.g., `extract_command` body lines 135-150 in `src/extraction/cli.py`; `build_command` lines 130-142 in `src/retrieval/cli.py`). The eval CLI stays on the linear pipeline, so tag it `phase1` unless an explicit pipeline flag is added.

---

### Tests

**`tests/rag/agentic/conftest.py`.** Fixture style comes from `tests/retrieval/visual/conftest.py` lines 1-20 (module docstring stating "offline", `tmp_db_path` fixture). Fakes:
- `FakeAnswerProvider` copied from `tests/test_answer_service.py` lines 27-46 (dataclass with `calls` list, optional `exception`, `malformed_result`). Add a scripted `answers: list[str]`.
- `FakeRetrieve`: callable returning scripted `EvidenceGateResult(is_strong=..., reason_code=RetrievalEvidenceReason..., hits=(...), top_score=..., query_terms=(...), run_id=...)` (fields per `src/retrieval/models.py` lines 154-170). Build `RetrievalHit` using `RetrievalScoreComponents()` as in `tests/test_answer_provider_gemini.py` lines 62-70 `_request(...)`.
- `FakeCritic`: scripted `CriticVerdict`s or exceptions, `calls` list.

**`tests/rag/test_critic_provider.py`.** Copy `tests/test_answer_provider_gemini.py` lines 1-60: offline-import test with `monkeypatch.delenv(...)`, missing-key `pytest.raises(...ConfigurationError)` asserting `reason_code`, and `FakeClient` → `FakeMessages.create(**kwargs)` recording `calls` and popping scripted responses or exceptions. Assert `"temperature" not in calls[0]`. `RetryableProviderError(status_code=503)` / `NonRetryableProviderError(status_code=400)` classes at lines 54-59.

**`tests/test_review_repository.py`.** Copy `make_field` / `make_record` / `prepare_db` / `table_count` from `tests/test_extraction_persistence.py` lines 23-132 (use `run_id="run-001"` so history rows exist, then assert they are byte-identical after review). Use the `tmp_db_path` fixture from `tests/conftest.py`.

**`tests/test_dashboard_review_tab.py`.** Base on `tests/test_compliance_dashboard.py` `FakeStreamlit` (lines 579-641: `columns`→`FakeMetricColumn.metric`, `dataframe(rows, *, hide_index, width)`, `selectbox(label, *, options, format_func=None)`, `image(image, *, caption)`). Add the `FakeContext` context-manager class from `tests/test_chat_dashboard.py` lines 28-45 for `st.form`. Add `radio`, `text_input`, `number_input`, `text_area`, `form_submit_button` (scripted return), `success`, `error`, `rerun`. Monkeypatch both `src.dashboard.review.st` and `src.dashboard.ui.st` (pattern: `tests/test_dashboard_chat_tab.py` lines 51-53).

**`tests/test_tracing_phase.py`.** Reuse `_FORBIDDEN_TRACE_KEYS` and `_FakeLangfuseContext` from `tests/test_tracing.py` lines 44-64 (import them or copy them). Module seam monkeypatching follows lines 288-296:
```python
        monkeypatch.setattr(module, "_LANGFUSE_AVAILABLE", True)
        monkeypatch.setattr(module, "langfuse_context", fake_context)
```
Add `src.rag.agentic.graph` and `src.extraction.review` to the module list.

**`tests/rag/agentic/test_stack_pins.py`.** Copy `tests/test_tracing.py::test_langfuse_v3_pinned` (lines 14-20) using `importlib.metadata.version`: assert `version("langgraph") == "1.0.1"`, `version("langchain-core").startswith("0.3.")`, and that `from langgraph.graph import StateGraph` compiles a trivial graph.

**Extend:** `tests/test_app.py` (headless start still passes with 4 tabs), `tests/test_db.py` (init_db twice, `extraction_reviews` exists), `tests/test_chat_dashboard.py` (new reason hints and agentic diagnostics fields rendered bounded; `_diagnostics(...)` helper line 101 gets the new kwargs).

---

## Shared Patterns

### Offline-safe lazy imports of heavy/optional SDKs
**Source:** `src/rag/gemini.py` lines 119-130, `src/rag/providers.py` lines 79-82, `src/tracing.py` lines 59-76
**Apply to:** `graph.py` (langgraph), `critic.py` (anthropic, google-genai), `tracing.py` (`propagate_attributes`, `langfuse.langchain`), `chat.py` (agentic module)
```python
        try:
            from google import genai  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001 - optional dependency boundary.
            raise AnswerConfigurationError("google-genai is installed/configured incorrectly for Gemini answers.") from exc
```

### Fail-safe boundaries: sanitize to reason codes and error class names
**Source:** `src/rag/service.py` lines 100-110, 141-153. `src/rag/gemini.py` lines 83-88. `src/extraction/cli.py` lines 81-90.
**Apply to:** every node, the critic adapter, review repository errors, the Review tab, and CLIs. Only `exc.__class__.__name__` and a `reason_code` cross boundaries, never `str(exc)`, prompts, evidence, or API payloads.

### Trace allowlists + injectable context seam
**Source:** `src/rag/service.py` lines 29-47 and 314-328. `src/tracing.py` lines 185-224.
**Apply to:** `graph.py`, `nodes.py` (span metadata), `review.py`. Every module has its own `_*_TRACE_ALLOWED_KEYS` frozenset and the `_LANGFUSE_AVAILABLE` / `langfuse_context` monkeypatch seams. Forbidden everywhere: `question`, `snippet`, `evidence_text`, `page_text`, draft text, critic feedback/unsupported_claims, field values, notes, secrets, image bytes (`tests/test_tracing.py` lines 44-53).

### Service-owned citations (D016)
**Source:** `src/rag/service.py::_citations_from_hits` lines 205-217
**Apply to:** agentic `finalize` node. Citations come only from merged retrieval hits. Critic and provider text never add citations.

### Bounded display text
**Source:** `src/dashboard/chat.py` lines 267-288 (`_safe_optional_text`, `_diagnostic_display`, `_bounded_text`). `src/dashboard/compliance.py` lines 451-459 (`_safe_detail_text`).
**Apply to:** Review tab and new Chat diagnostics.

### SQLite transaction discipline
**Source:** `src/extraction/repository.py` lines 81-102. `src/db/schema.py::_connect` lines 370-374 (FK pragma).
**Apply to:** `apply_field_review`. There is one connection and one commit, rollback on any exception, and parameterized SQL only. Validate `field_name` via `SDFFieldName(...)` and `action` via the `ReviewAction` enum before SQL.

### Frozen DTOs with defaulted trailing fields for contract extension
**Source:** `src/rag/models.py` lines 39-85, `src/retrieval/models.py` lines 132-151 (`evidence_text: str = ""` added later as a defaulted field)
**Apply to:** `AnswerDiagnostics` extension, optional `AnswerProviderRequest.revision_hint`, `ReviewQueueItem`, `ReviewOutcome`, `AgenticDeps`.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/rag/agentic/graph.py` (StateGraph wiring, `recursion_limit`, `GraphRecursionError`) | orchestrator | request-response | No LangGraph code exists in the repo yet. Use the RESEARCH "Graph builder" example (verified on langgraph 1.0.1). The surrounding decorator, seams, and trace code come from `src/rag/service.py` |
| `src/tracing.py::trace_session` / `mask_trace_payload` / `build_callback_handler` | cross-cutting | event-driven | No `propagate_attributes`, `mask=`, or `CallbackHandler` usage exists yet. Use RESEARCH "Langfuse v3 session + tags" and "Global mask wiring". Reuse the existing `_safe_trace_value` / `filter_trace_metadata` helpers for sanitization |
| `st.form` usage in `src/dashboard/review.py` | component | form submit | No existing Streamlit forms. Use RESEARCH Pattern 6. The rest of the tab has strong analogs |

## Metadata

**Analog search scope:** `src/rag/`, `src/retrieval/`, `src/extraction/`, `src/db/`, `src/dashboard/`, `src/eval/`, `src/pipeline/`, `src/tracing.py`, `src/config.py`, `src/app.py`, `tests/` (incl. `tests/retrieval/visual/`, `tests/eval/`), `pyproject.toml`
**Files scanned:** ~40 (18 read in depth)
**Pattern extraction date:** 2026-09-23
