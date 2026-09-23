# Phase 6: Agentic RAG & Observability - Research

**Researched:** 2026-09-23
**Domain:** LangGraph agentic RAG (self-critique loop), HITL review of low-confidence extractions (Streamlit + SQLite), Langfuse v3 tracing with phase tags
**Confidence:** HIGH for stack and codebase integration (checked against PyPI metadata, the installed Windows venv, a local smoke run, and the code). MEDIUM for graph policy choices (these are design decisions, flagged below).

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. The user skipped discuss-phase ("continue without discuss-phase; plan from research + requirements"). No AI-SPEC.md either.

### Locked Decisions (from the orchestrator prompt + CLAUDE.md, same authority)
- Stack is fixed by CLAUDE.md: LangGraph `>=1.1,<2` (**see Pitfall 1: this pin cannot be installed alongside the existing RAGAS stack. Recommended pin is `langgraph==1.0.1`, which needs user confirmation**), Langfuse `>=3,<4` (v4 has breaking changes), RAGAS `==0.4.3`, Gemini 2.5 Flash as the primary model, Claude Sonnet as the critic.
- Windows verification rule: run tests with `venv\Scripts\python.exe -m pytest ...` only. Never use `/bin/bash`.
- Follow the prior-phase pattern: offline-testable pure modules with lazy imports for heavy deps.
- Tests must run offline without live API keys. Mock the LLM and Langfuse.
- Langfuse must fall back to a no-op when keys are missing.

### Claude's Discretion
Everything not listed above: graph topology details, retry/regen policy thresholds, HITL data model, tag taxonomy, and module layout. Recommendations are below.

### Deferred Ideas (OUT OF SCOPE)
- `EXTRACT-03` (critic/reflection extraction loop) and `EXTRACT-04` (confidence ensemble `0.4 logprob + 0.4 self-consistency + 0.2 critic`). Phase 5 CONTEXT deferred both explicitly. They are **not** Phase 6 requirements. HITL-01 must work with the confidence and `review_state` signals the extraction pipeline **already produces** (`confidence < 0.75` → `needs_review`, abstained fields, visual-tier fields forced to `needs_review`).
- Langfuse v4 migration (REQUIREMENTS Out of Scope).
- Streaming chat responses (REQUIREMENTS Out of Scope).
- Authentication/RBAC (single-user demo).
- Phase 7 side-by-side benchmark UI. Phase 6 only has to leave the `linear | agentic` switch and phase tags in place so Phase 7 can use them.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RAG-03 | LangGraph agentic pipeline: decompose → retrieve → evaluate retrieval quality → re-retrieve if insufficient (≤2 retries) → draft → self-critique for faithfulness → regenerate or abstain (≤1 regen) | §Architecture Patterns 1–4, §Code Examples (graph builder, router functions, critic adapter), Pitfalls 1, 3, 4, 5, 6 |
| HITL-01 | Dashboard HITL tab surfaces low-confidence extractions for human review and correction; corrections update the Compliance DB | §Pattern 5 (review repository), §Pattern 6 (Review tab), Pitfalls 7, 8, 9 |
| OBS-01 | All agent steps, LLM calls, retrievals, and extractions traced in Langfuse (v3, pinned <4.0) with `phase` tag on every trace session | §Pattern 7 (trace_session + mask + CallbackHandler), §Code Examples (tracing helpers), Pitfalls 2, 10, 11 |
| SC-4 | "System abstains rather than hallucinating when confidence is insufficient across both extraction and RAG pathways" | Existing extraction abstention (`ReviewState.ABSTAINED`) + new RAG abstain terminals (retrieval exhausted, critic rejected, critic error). Cross-path test in Validation Architecture |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.11 (the Windows venv runs **3.11.9**, verified from `venv/pyvenv.cfg`).
- Locked stack: LangGraph, Langfuse **v3 (hard `<4.0`)**, Streamlit `>=1.56`, Pydantic v2, RAGAS `==0.4.3`, google-genai, anthropic.
- Gemini 2.5 Flash is the primary model for extraction and generation. Claude Sonnet (`claude-sonnet-4-6`) is for the critic and is used sparingly.
- Prefer wrapping SDK calls in plain nodes over LangChain model bindings ("simpler and avoids LangChain's churn").
- Langfuse guidance: `@observe()` on the top-level graph invocation, plus `CallbackHandler()` in `RunnableConfig.callbacks`. Attach `critic_score`, `retrieval_round`, `doc_id`, `page_number` metadata.
- Windows hard rule: verify with `venv\Scripts\python.exe -m pytest ...` (or `venv/Scripts/python.exe -m pytest ...`). Never `/bin/bash`.
- GSD workflow enforcement: edits go through GSD commands.
- `compliance.db` and `.env` are never staged (carried over from Phase 5).
- Privacy contract (quick-260611-ou3, Phase 5 T-05-11): page text, `evidence_text`, snippets, question text, image bytes, and secrets never enter Langfuse allowlists or persisted eval rows.

## Summary

The codebase is ready for this phase. `src/rag/service.py::answer_question` is a linear, gate-first RAG service returning a stable `AnswerResult` DTO. `src/retrieval/retriever.py::retrieve_evidence` returns reason-coded `EvidenceGateResult`s with `is_strong`, `top_score`, and bounded hits. The Chat tab calls the service through an injectable `answer_fn`. On the extraction side, `extractions` rows already carry `confidence`, `needs_review`, `review_state` (`pending|needs_review|reviewed|abstained`), and `abstention_reason`. `src/extraction/risk.py::compute_record_risk` is a pure function that can recompute risk after a correction. Tracing goes through `src/tracing.py` (`observe`, `safe_update_current_trace` with per-module allowlists and the injectable `langfuse_context` test seam).

Phase 6 adds three things. (1) A LangGraph `StateGraph` (`src/rag/agentic/`) that returns the **same `AnswerResult` contract** and reuses `retrieve_evidence` plus the Gemini `AnswerProvider` as plain-function nodes. The critic is a new `CriticProvider` protocol (Claude Sonnet primary). Loop bounds are enforced by counters in state plus an explicit `recursion_limit`. (2) A review repository (`list_review_queue`, `apply_field_review`) with an append-only `extraction_reviews` audit table, and a fourth Streamlit "Review" tab. (3) Tracing upgrades in `src/tracing.py`: a `trace_session()` context manager that applies the `phase` tag/metadata and `session_id` through Langfuse v3's `propagate_attributes`, a global `mask` function so auto-captured `@observe` and `CallbackHandler` I/O cannot leak page text, a factory that returns a LangChain `CallbackHandler` or `None`, and `@observe(as_type="generation")` wrappers around the raw-SDK Gemini and Claude calls.

**The biggest finding is a dependency conflict.** Every `langgraph>=1.1.0` requires `langchain-core>=1.0` (via `langgraph-prebuilt>=1.0.8` or directly). The project pins `langchain-core<1` because RAGAS 0.4.3 breaks on langchain 1.x. `uv pip compile` confirms `langgraph>=1.1` + `langchain-core<1` is **unsatisfiable**. The newest compatible release is **`langgraph==1.0.1`** (with `langgraph-prebuilt==1.0.1`, `langgraph-checkpoint==3.0.1`). I smoke-tested it on Python 3.11 with `langchain-core==0.3.86` and `langfuse==3.14.6` (the exact installed versions): StateGraph, conditional edges, `recursion_limit`/`GraphRecursionError`, and `CallbackHandler` all work.

**Primary recommendation:** Pin `langgraph==1.0.1` (documented deviation from CLAUDE.md's `>=1.1` floor, user to confirm). Build the agentic graph as plain-function nodes over the existing retrieval and provider seams, returning `AnswerResult`. Make retrieval-quality evaluation deterministic (reuse the evidence gate, no LLM). Fail closed (abstain) on any critic failure. Route HITL corrections through a new repository function that updates only the "latest" tables (`extractions`, `compliance_records`) plus an audit table, never the run-history tables.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Agentic RAG orchestration (decompose/retrieve/evaluate/draft/critique) | API / Backend (`src/rag/agentic/`) | — | Business logic. The UI only calls `answer_fn`. Must be headless-testable and reusable by the Phase 7 eval harness |
| Retrieval-quality evaluation | API / Backend (deterministic over `EvidenceGateResult`) | — | Reuses gate signals and needs no LLM, so it is testable and cheap |
| Faithfulness critique | API / Backend (`CriticProvider` adapters) | External LLM API (Claude / Gemini) | Provider boundary sanitizes errors. Citations stay service-owned |
| Review queue query and correction writes | Database / Storage (`src/extraction/review.py` repository over SQLite) | API / Backend (date normalization, risk recompute) | ARCHITECTURE.md: "Extractor/Critic are the only writers to the Compliance DB". Keep writes in the extraction package's repository, not in the dashboard |
| Review tab rendering | Browser / Client (Streamlit `src/dashboard/review.py`) | — | Thin presentation layer. Calls repository functions only |
| Trace session / phase tagging / masking | Cross-cutting (`src/tracing.py`) | Langfuse SaaS | One module owns all Langfuse calls. Entry points (Streamlit handlers, CLIs) open the session |
| Pipeline selection (`linear` vs `agentic`) | Config (`src/config.py` Settings) | Dashboard | Needed by Phase 7 BENCH-01 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | **==1.0.1** (released 2025-10-20) | StateGraph agentic loop | Locked framework. 1.0.1 is the **last** release compatible with `langchain-core<1` [VERIFIED: PyPI metadata + `uv pip compile`] |
| langgraph-prebuilt | ==1.0.1 (transitive) | Required by langgraph 1.0.1 | 1.0.2+ requires `langchain-core>=1.0` [VERIFIED: PyPI] |
| langgraph-checkpoint | 3.0.1 (transitive, `<4`) | Required by langgraph | No checkpointer is used. The graph runs stateless per question [VERIFIED: uv resolution] |
| langfuse | >=3.9,<4 (installed **3.14.6**, latest v3 **3.15.0**) | Tracing | `propagate_attributes` was added in **3.9.0** [VERIFIED: inspected wheels 3.8.0 (absent) / 3.9.0 (present)]. Raise the floor from `>=3.0` to `>=3.9` |
| langchain-core | 0.3.86 (installed, `<1` pinned) | Runnable config / callbacks used by langgraph and `langfuse.langchain.CallbackHandler` | Pinned by the RAGAS 0.4.3 constraint in pyproject [VERIFIED: venv dist-info] |
| anthropic | >=1,<2 (latest **1.8.0**, 2026-09-22) | Claude Sonnet critic | Messages API. v1.0 (Aug 2026) removed the `temperature/top_p/top_k` kwargs and moved schema dicts to `output_config` [CITED: github.com/anthropics/anthropic-sdk-python/blob/v1.0.0/MIGRATION.md]. Not currently installed |
| google-genai | installed 2.7.0 | Gemini draft/decompose/rewrite (existing `GeminiAnswerProvider`) | Already in use [VERIFIED: venv] |
| streamlit | installed 1.56.0 | Review tab | Already in use [VERIFIED: venv] |
| pydantic | installed 2.13.3 | `CriticVerdict`, `ReviewDecision` models | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dateutil | installed (pyproject) | Parse reviewer-entered corrected dates | HITL date-field corrections |
| tenacity | installed | Bounded retry on transient 429/5xx in the critic adapter | Mirror `GeminiAnswerProvider._generate_content_with_retry` |
| pytest-socket | 0.8.0 installed | `--disable-socket` to prove offline tests | Optional guard in the phase gate command |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `langgraph==1.0.1` | Upgrade to langchain 1.x + `langgraph>=1.1` | Breaks RAGAS 0.4.3 (the pyproject comment documents missing `ChatVertexAI` / `ContextOverflowError`), which would regress EVAL-04. Rejected |
| `langgraph==1.0.1` | Separate venv for RAGAS | Two-venv ops burden on Windows, and the eval harness imports `answer_question` in-process. Rejected |
| Plain-function nodes over SDK providers | `langchain-google-genai` / `langchain-anthropic` chat models | CLAUDE.md prefers plain nodes. Existing fakes/seams are SDK-provider based. LangChain bindings would add churn. Rejected |
| Deterministic retrieval grader | LLM relevance grader (CRAG-style) | Adds Gemini calls per round. The free-tier quota (5 RPM / 20 RPD, per STATE.md) makes this costly. The gate already computes score + term coverage |
| Claude critic | Gemini-as-critic | Same-model self-critique is weaker (Pitfall C5). Keep Gemini only as a configured fallback |

**Installation (pyproject `dependencies`):**
```
"langgraph==1.0.1",          # last release compatible with langchain-core<1 (RAGAS 0.4.3 constraint)
"langfuse>=3.9,<4.0",        # propagate_attributes needs >=3.9
"anthropic>=1,<2",
```
Windows: `venv\Scripts\python.exe -m pip install "langgraph==1.0.1" "anthropic>=1,<2" "langfuse>=3.9,<4.0"`

**Version verification (done this session):** `uv pip compile` over {langgraph==1.0.1, ragas==0.4.3, langchain 0.3.x stack, langfuse<4, anthropic} resolves to langgraph 1.0.1 / langgraph-checkpoint 3.0.1 / langgraph-prebuilt 1.0.1 / langchain-core 0.3.86 / langfuse 3.15.0 / anthropic 1.8.0 [VERIFIED].

## Architecture Patterns

### System Architecture Diagram

```
 Streamlit Chat tab (answer_fn seam)          Eval harness / Phase 7 (answer_fn seam)
            │  question                                     │
            ▼                                               ▼
   ┌───────────────── trace_session(phase="phase2", session_id, tags) ──────────────┐
   │  answer_question_agentic(db_path, question, provider=, critic=)  [@observe root]│
   │        │ graph.invoke(state, {"callbacks":[handler|none], "recursion_limit":N}) │
   │        ▼                                                                        │
   │  [decompose] ──(heuristic: compound? → Gemini JSON ≤3 subqueries : [question])  │
   │        ▼                                                                        │
   │  [retrieve] ── retrieve_evidence(db, subq) per sub-query ──► SQLite FTS index   │
   │        │        (round r: r=0 original subqueries, r≥1 rewritten queries)       │
   │        ▼        merge+dedupe hits by (doc_id,page_num), keep max score          │
   │  [evaluate_retrieval]  deterministic: every sub-query has ≥1 strong hit?        │
   │        │                                                                        │
   │   sufficient ───────────────┐          insufficient                             │
   │        │                    │           ├─ rounds < 3 → [rewrite] → [retrieve]  │
   │        │                    │           └─ rounds = 3 → [abstain: retrieval_exhausted]
   │        ▼                                                                        │
   │  [draft] ── GeminiAnswerProvider.answer(bounded evidence) ──► Gemini API        │
   │        ▼                                                                        │
   │  [critique] ── CriticProvider.critique(question, draft, evidence) ──► Claude    │
   │        │                                                                        │
   │   supported & score≥τ → [finalize: ANSWERED, citations from hits only]          │
   │   unsupported & regen=0 → [draft (with critic feedback)] → [critique]           │
   │   unsupported & regen=1 → [abstain: critic_rejected]                            │
   │   critic error/malformed → [abstain: critic_error]   (fail closed)              │
   │        ▼                                                                        │
   │  AnswerResult(status, answer_text, citations, diagnostics+agentic fields)       │
   └───────────── mask() redacts span I/O; allowlisted metadata only ─────────────────┘
            │
            ▼ Langfuse v3 (OTEL): root span → node spans (CallbackHandler) → generation spans

 Review tab ──► list_review_queue(db) ◄── extractions ⋈ documents (needs_review / abstained / conf<τ)
     │  approve / correct / confirm_absent (st.form)
     ▼
 apply_field_review(db, doc_id, field, action, value, note)   [@observe, trace_session(phase)]
     ├─ INSERT extraction_reviews (append-only audit: before/after, reviewer, ts)
     ├─ UPDATE extractions (latest row only) → review_state='reviewed', needs_review=0
     └─ rebuild SDFExtractionRecord → compute_record_risk → UPDATE compliance_records
        (extraction_history / compliance_record_history are NEVER touched)
```

### Recommended Project Structure
```
src/
├── rag/
│   ├── agentic/
│   │   ├── __init__.py        # exports answer_question_agentic, build_agentic_graph
│   │   ├── state.py           # AgenticState TypedDict + limits dataclass (MAX_RETRIEVAL_ROUNDS=3, MAX_REGENERATIONS=1)
│   │   ├── nodes.py           # pure node functions (decompose, retrieve, evaluate, rewrite, draft, critique, finalize, abstain) with injected deps
│   │   ├── routing.py         # pure router functions (route_after_evaluate, route_after_critique)
│   │   ├── graph.py           # build_agentic_graph(deps) (lazy `import langgraph`) + answer_question_agentic()
│   │   ├── decompose.py       # is_compound() heuristic + optional LLM decomposer
│   │   └── rewrite.py         # domain-synonym deterministic rewrite + optional LLM rewrite
│   ├── critic.py              # CriticProvider protocol, CriticVerdict model, AnthropicCritic, GeminiCritic, build_critic_provider
│   ├── models.py              # (extend) new AnswerReasonCode values + optional agentic diagnostics fields
│   └── service.py             # unchanged linear path (phase1 baseline)
├── extraction/
│   └── review.py              # list_review_queue, apply_field_review, ReviewQueueItem, ReviewAction
├── dashboard/
│   ├── review.py              # render_review_tab (HITL)
│   └── chat.py                # (extend) pipeline selection + agentic diagnostics + new reason hints
├── db/schema.py               # (extend) extraction_reviews table + idempotent migration
├── tracing.py                 # (extend) trace_session, build_callback_handler, mask_trace_payload, observe_generation helpers
└── config.py                  # (extend) rag_pipeline, pipeline_phase, anthropic_api_key, critic_model, critic_provider, critic_min_faithfulness
tests/
├── rag/agentic/               # graph routing, nodes, critic adapters
├── test_review_repository.py
├── test_dashboard_review_tab.py
└── test_tracing_phase.py
```

### Pattern 1: Same output contract, new orchestration
**What:** `answer_question_agentic(db_path, question, *, provider, critic=None, **kw) -> AnswerResult`, with the same positional signature as `answer_question` so the Chat tab `answer_fn` seam and `src/eval/ragas_quality.compute_ragas_quality(answer_fn=...)` accept it unchanged.
**When:** Always. Phase 7 benchmark switches on `settings.rag_pipeline` (`"linear"` = phase1, `"agentic"` = phase2).
**Detail:** Extend `AnswerDiagnostics` with **defaulted** trailing fields (`pipeline: str = "linear"`, `retrieval_rounds: int = 0`, `regeneration_count: int = 0`, `sub_query_count: int = 0`, `critic_verdict: str | None = None`, `critic_score: float | None = None`). Frozen dataclasses accept defaulted fields at the end without breaking existing constructors. Add `AnswerReasonCode` values: `RETRIEVAL_EXHAUSTED`, `CRITIC_REJECTED`, `CRITIC_ERROR`. **Every new enum value needs a `_REASON_HINTS` entry in `src/dashboard/chat.py`** (otherwise the generic fallback message renders).

### Pattern 2: State with explicit counters, not recursion as a loop guard
```python
# src/rag/agentic/state.py
import operator
from typing import Annotated
from typing_extensions import TypedDict

MAX_RETRIEVAL_ROUNDS = 3      # 1 initial + ≤2 retries (RAG-03)
MAX_REGENERATIONS = 1         # ≤1 regen (RAG-03)
GRAPH_RECURSION_LIMIT = 30    # upper bound on super-steps; worst path ≈ 12 (see Pitfall 4)

class AgenticState(TypedDict, total=False):
    question: str
    sub_queries: list[str]
    active_queries: list[str]          # queries used in the current round (rewritten on retries)
    retrieval_round: int               # incremented in retrieve node
    evidence: tuple                    # merged, deduped RetrievalHit tuple (bounded top_k)
    per_query_strong: list[bool]
    run_id: str | None
    top_score: float
    evidence_reason: str
    draft: str | None
    critic_feedback: str | None        # in-memory only, never traced/persisted
    critic_verdict: str | None
    critic_score: float | None
    regeneration_count: int
    outcome: str                        # "answered" | "abstained" | "provider_error"
    reason_code: str
    error_class: str | None
    steps: Annotated[list[str], operator.add]   # node names for diagnostics/tests
```
Routers are pure functions of state. Unit-test them without langgraph:
```python
def route_after_evaluate(state) -> str:
    if all(state.get("per_query_strong") or [False]):
        return "draft"
    if state.get("retrieval_round", 0) < MAX_RETRIEVAL_ROUNDS:
        return "rewrite"
    return "abstain"

def route_after_critique(state) -> str:
    if state.get("error_class"):
        return "abstain"                       # fail closed
    if state.get("critic_verdict") == "supported":
        return "finalize"
    if state.get("regeneration_count", 0) < MAX_REGENERATIONS:
        return "draft"                         # regenerate with critic feedback
    return "abstain"
```

### Pattern 3: Dependency injection into nodes (offline-testable)
`build_agentic_graph(deps: AgenticDeps)` where `AgenticDeps` is a frozen dataclass holding `db_path`, `retrieve_fn` (default `retrieve_evidence`), `answer_provider`, `critic`, `decomposer` (optional LLM callable), `rewriter`, `top_k`, `critic_min_faithfulness`. Nodes are closures, or `functools.partial` over pure functions. Tests inject fake `retrieve_fn` returning canned `EvidenceGateResult`s and fake providers/critics. **No fake scores ever enter a reported metric.** This mirrors the Phase 5 metric-integrity rule: tests assert routing, bounds, and contract shape only.

### Pattern 4: Deterministic retrieval evaluation and "re-retrieve" strategy
- **Evaluate:** sufficient iff every active sub-query produced `is_strong=True` from the existing gate (score ≥ 0.45, term coverage ≥ 0.50, hits ≥ 1). **Never relax gate thresholds on retry.** Relaxing them would weaken the no-hallucination gate (D016).
- **Re-retrieve (round ≥ 1):** rewrite only the sub-queries that failed. Order: (a) deterministic domain-synonym expansion (expiry ↔ expiration/"use by"/"valid until"; manufacturing ↔ mfg/"date of manufacture"/production; CoA ↔ "certificate of analysis"; CoQ ↔ "certificate of quality"; revision ↔ rev/version), then (b) Gemini rewrite to keyword form only if a provider is configured. If the rewritten query equals a query already tried, go to abstain (monotonic progress check, PITFALLS M2).
- **Decompose:** run the LLM decomposer only when `is_compound(question)` (e.g., contains " and "/" vs "/"compare"/multiple "?", or ≥2 SDF field names). Otherwise `sub_queries=[question]`. Cap at 3 sub-queries. If the LLM output is malformed, fall back to `[question]`, record a step, and do not abstain.
- **Draft evidence:** merged hits sorted by score, top `_MAX_EVIDENCE_ITEMS=5` (existing Gemini provider bound). Citations are built with the existing `_citations_from_hits` logic, so they are service-owned (D016).

### Pattern 5: HITL review repository (writes latest tables + audit only)
```python
# src/extraction/review.py (sketch)
class ReviewAction(str, Enum):
    APPROVE = "approve"            # accept current value as correct
    CORRECT = "correct"            # replace value (reviewer-entered)
    CONFIRM_ABSENT = "confirm_absent"  # field genuinely not in document

def list_review_queue(db_path: str, *, threshold: float) -> list[ReviewQueueItem]:
    # SELECT e.doc_id, d.filename, e.field_name, e.field_value, e.normalized_value, e.confidence,
    #        e.source_page, e.verbatim_span, e.evidence_type, e.review_state, e.abstention_reason
    # FROM extractions e JOIN documents d USING(doc_id)
    # WHERE e.review_state IN ('needs_review','abstained')
    #    OR (e.confidence < ? AND COALESCE(e.review_state,'') <> 'reviewed')
    # AND NOT EXISTS (SELECT 1 FROM extraction_reviews r WHERE r.doc_id=e.doc_id AND r.field_name=e.field_name
    #                 AND r.action='confirm_absent' AND r.reviewed_at >= COALESCE(e.updated_at, e.created_at))
    # ORDER BY e.confidence ASC, d.filename, e.field_name

def apply_field_review(db_path, *, doc_id, field_name, action, corrected_value=None,
                       source_page=None, note=None, reviewer="demo-reviewer", today=None) -> ReviewOutcome:
    # one transaction:
    # 1. load current record via get_extraction_record (validated Pydantic)
    # 2. build new ExtractedField (model_copy/update) → validates
    # 3. INSERT extraction_reviews (audit)       ← before/after values, previous confidence/state
    # 4. UPDATE extractions latest row only
    # 5. recompute SDFExtractionRecord + compute_record_risk(record, today) → UPDATE compliance_records
```
New table (additive, idempotent migration in `init_db`, mirroring `_migrate_visual_index_runs_table`):
```sql
CREATE TABLE IF NOT EXISTS extraction_reviews (
    review_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id              TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    field_name          TEXT NOT NULL,
    action              TEXT NOT NULL CHECK (action IN ('approve','correct','confirm_absent')),
    previous_value      TEXT,
    new_value           TEXT,
    previous_confidence REAL,
    previous_review_state TEXT,
    source_page         INTEGER,
    reviewer            TEXT NOT NULL,
    note                TEXT,
    run_id              TEXT,          -- extraction run the reviewed value came from
    trace_id            TEXT,          -- Langfuse trace of the review action
    reviewed_at         TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_extraction_reviews_doc_field ON extraction_reviews(doc_id, field_name);
```

### Pattern 6: Review tab (Streamlit, FakeStreamlit-testable)
- Add a 4th tab `"Review"` in `src/app.py` → `render_review_tab(db_path)`. Signature takes injectable `queue_fn` / `apply_fn` seams like `render_chat_tab(answer_fn=...)`.
- Layout: summary metric (queue size, abstained vs low-confidence counts), a `st.dataframe` of the queue, then a `st.selectbox` for one queue item and a detail pane (source page image via existing `get_page_image`, current value, confidence, evidence span, abstention reason). Then **one `st.form(key=f"review_{doc_id}_{field}")`** with `st.radio(action)`, `st.text_input(corrected value)`, `st.number_input(source page, 1-based display)`, `st.text_area(note)`, `st.form_submit_button`. On submit: call `apply_fn`, show `st.success`/`st.error`, then `st.rerun()`.
- Bound all displayed text (reuse the `_bounded_text` / `_safe_detail_text` pattern). Never render raw DB errors.

### Pattern 7: Tracing: one session context, masked I/O, phase tag everywhere
Extend `src/tracing.py`:
1. `PHASE_TAGS = {"linear": "phase1", "agentic": "phase2"}`. `Settings.pipeline_phase` (default `"phase2"`) covers non-RAG entry points.
2. `trace_session(*, phase: str, session_id: str | None, tags: Iterable[str] = (), metadata: Mapping | None = None)`: a context manager that (a) calls `_ensure_langfuse_initialized()`, (b) enters `langfuse.propagate_attributes(tags=[phase, *tags], session_id=..., metadata={"phase": phase, **allowlisted_str_metadata})` when Langfuse is available and enabled, and (c) otherwise yields a `nullcontext`. It never raises. Wrap every **entry point**: the Chat tab submit, the Review tab submit, `extract`/`extract-all` CLI commands, the retrieval index CLI, the eval CLI, and the ingestion CLI. Put `propagate_attributes` **inside** the root `@observe` span or immediately before the root call (see Pitfall 10).
3. `mask_trace_payload(*, data, **kwargs)`: passed as `Langfuse(mask=...)` in `_ensure_langfuse_initialized`. Mappings keep only keys in a global safe-key set, with values run through `_safe_trace_value`. Bare strings longer than a short bound become `"[redacted:len=N]"`. Dataclasses and objects are dropped. This also fixes the **pre-existing leak**: current `@observe(name=...)` decorators use default `capture_input=True` and so send `question` and `db_path` arguments today.
4. `build_callback_handler() -> Any | None`: returns `langfuse.langchain.CallbackHandler()` only when tracing is enabled and keys are present. Otherwise returns `None`. Constructing it without keys logs "Authentication error ... Client will be disabled" (observed in the smoke test), which is noisy but harmless.
5. Generation spans: wrap `GeminiAnswerProvider.answer` / critic `.critique` / decomposer / rewriter SDK calls with `observe(name="generation.<role>", as_type="generation", capture_input=False, capture_output=False)` and call `get_client().update_current_generation(model=..., usage_details={"input": n, "output": m})` using the existing `_extract_usage_metadata` shape.
6. Node spans: the `CallbackHandler` creates one span per LangGraph node automatically. Also add allowlisted per-node metadata via a `safe_update_current_span` sibling of `safe_update_current_trace`: `retrieval_round`, `sub_query_count`, `critic_score`, `critic_verdict`, `regeneration_count`, `citation_count`, `doc_id`, `page_number` (the CLAUDE.md audit keys).
7. Stable span taxonomy (PITFALLS M9): `rag.agentic`, `agent.decompose`, `agent.retrieve`, `agent.evaluate`, `agent.rewrite`, `agent.draft`, `agent.critique`, `hitl.review`. Keep existing names (`rag_answer_question`, `retrieval_evidence_gate`, `sdf_extract_document`) unchanged.

### Anti-Patterns to Avoid
- **Using LangGraph `recursion_limit` as the retry cap.** Caps live in state counters. `recursion_limit` is only a backstop, and `GraphRecursionError` is caught and turned into an abstention.
- **LLM-generated citations.** Citations must come only from retrieval hits (D016). The critic never adds citations.
- **Answering when the critic fails.** Timeout, malformed JSON, or missing key must abstain (`CRITIC_ERROR`). Returning an unverified draft is a hallucination risk.
- **Writing HITL corrections through `upsert_extraction_record`.** That writes `extraction_history` / `compliance_record_history` under the run_id and would contaminate per-run extraction F1 (Pitfall 7).
- **Putting `evidence_text` / question into trace metadata or allowlists.** Use counts, ids, and scores only.
- **Using `graph.astream` / async nodes in Streamlit.** Event-loop conflicts (PITFALLS M4). Use sync `graph.invoke`. Streaming is out of scope.
- **Storing the compiled graph or checkpointer in `st.session_state`.** Not needed: each question is a stateless run. Build the graph once per process (module-level `functools.lru_cache` on a deps key) or per call. Compiling is cheap.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cyclic agent control flow | while-loop state machine | `langgraph.StateGraph` + `add_conditional_edges` | Locked stack. Node spans come for free via CallbackHandler. Also gives Phase 7 a diagrammable graph (`graph.get_graph().draw_mermaid()` for POLISH-01) |
| Trace-level tag/session propagation | manual `update_current_trace` in every module | `langfuse.propagate_attributes` (v3.9+) | Propagates to all child spans. Late `update_current_trace` misses earlier spans (docstring warning) |
| PII/content scrubbing of auto-captured I/O | per-decorator `capture_input=False` everywhere | `Langfuse(mask=fn)` global mask + allowlists | Covers CallbackHandler spans too, which you cannot configure per-node |
| Date parsing of reviewer input | regex parser | `dateutil.parser.parse` + existing `_parse_iso_date` / risk `_parse_date` | Pharma date formats vary ("01-JAN-2024") |
| Risk recompute after correction | new rule code | `compute_record_risk(record, today=...)` | Single source of truth for D008/D010 |
| Retry of transient API errors | custom loops | `tenacity.Retrying` (existing pattern in `src/rag/gemini.py`) | Consistent semantics |
| JSON-ish LLM output parsing | ad-hoc `json.loads` | Pydantic `CriticVerdict.model_validate_json` after `_strip_simple_fences` | Validation errors map to the `AnswerValidationError`/`CRITIC_ERROR` path |

**Key insight:** Nearly every hard part (evidence gate, citation ownership, provider sanitization, risk policy, trace allowlists) already exists. Phase 6 is orchestration and wiring. The risk is breaking existing contracts, not missing capability.

## Runtime State Inventory

Not a rename/refactor phase, but it does change schema and trace state:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `compliance.db` (local, gitignored): `extractions` / `compliance_records` rows will be mutated by HITL; new `extraction_reviews` table | Additive idempotent migration in `init_db`. No data migration. Never stage `compliance.db` |
| Live service config | Langfuse cloud project: existing traces tagged `phase1` (ingest/db_writer hard-code `tags=["phase1", ...]`) | Code edit: replace hard-coded tags with `trace_session` phase injection. Historical traces are left as-is |
| OS-registered state | None (verified: no schedulers/services in repo) | None |
| Secrets/env vars | New `ANTHROPIC_API_KEY`, optional `CRITIC_PROVIDER`, `CRITIC_MODEL`, `RAG_PIPELINE`, `PIPELINE_PHASE` | Add to `Settings` + `.env.example`. Do not commit `.env` |
| Build artifacts | Windows venv has a stray `site-packages/langgraph/` directory (only `cache/`, `checkpoint/`, `store/` subpackages, no langgraph dist-info) | `pip install langgraph==1.0.1` will populate it. Verify `import langgraph.graph` in the Wave 0 smoke test |

## Common Pitfalls

### Pitfall 1: LangGraph ≥1.1 is not installable with the RAGAS langchain-0.3 stack
**What goes wrong:** `pip install "langgraph>=1.1,<2"` either fails to resolve or silently upgrades langchain-core to 1.x, which breaks RAGAS imports (EVAL-04) at load time.
**Why:** langgraph 1.1.7+ requires `langchain-core>=1.3`. 1.1.0–1.1.6 require `langgraph-prebuilt>=1.0.8`, which requires `langchain-core>=1.0`. `uv pip compile` reports "langgraph>=1.1.0 depends on langchain-core>=1.0.0 … unsatisfiable" [VERIFIED].
**How to avoid:** Pin `langgraph==1.0.1`. Record a decision deviating from the CLAUDE.md `>=1.1.0` floor (user confirmation needed). Add a pin-guard test like `test_langfuse_v3_pinned`: assert `version("langgraph") == "1.0.1"` and `version("langchain-core").startswith("0.3.")`.
**Warning signs:** `pip` output shows langchain-core 1.x being installed; RAGAS `ImportError: ChatVertexAI`.

### Pitfall 2: Auto-captured I/O leaks page text to Langfuse
**What goes wrong:** `CallbackHandler` records each node's input/output state (question, `evidence` hits with `evidence_text`, draft). The existing `@observe` decorators already capture function args by default.
**How to avoid:** Global `mask` (Pattern 7.3) plus `capture_input=False, capture_output=False` on new generation wrappers. Add a test that runs `mask_trace_payload` over a realistic state dict and asserts forbidden keys and long strings are gone (reuse `_FORBIDDEN_TRACE_KEYS` from `tests/test_tracing.py`).

### Pitfall 3: Critic self-correction fallacy / over-critical critic
**What goes wrong:** The critic rejects good answers, so the abstention rate spikes, or regeneration changes a correct answer (PITFALLS C5).
**How to avoid:** Give the critic the **evidence text** (new information), not just the draft. Use a different model family (Claude). Cap at 1 regen. Log `critic_verdict` and `critic_score` to trace metadata so the rejection rate is observable. Make the threshold configurable (`critic_min_faithfulness`, default 0.8).
**Warning signs:** >50% of answerable gold questions end as `CRITIC_REJECTED`.

### Pitfall 4: Recursion limit too tight or too loose
**What goes wrong:** langgraph 1.0.1 default `recursion_limit` is **25** [VERIFIED: `_internal/_config.py` in the 1.0.1 wheel]. Newer langgraph uses 10007. The worst legal path is decompose + 3×(retrieve+evaluate) + 2×rewrite + 2×(draft+critique) + terminal ≈ 14 super-steps.
**How to avoid:** Pass `{"recursion_limit": 30}` explicitly. Catch `langgraph.errors.GraphRecursionError` and map it to an abstain with `error_class="GraphRecursionError"`. Add a test with an always-insufficient fake retriever asserting exactly 3 retrieval rounds and an `ABSTAINED`/`RETRIEVAL_EXHAUSTED` result.

### Pitfall 5: Free-tier Gemini quota exhaustion in agentic mode
**What goes wrong:** STATE.md records the Gemini key at 5 RPM / 20 RPD. The agentic path can make up to 1 decompose + 2 rewrites + 2 drafts = 5 Gemini calls per question.
**How to avoid:** Deterministic-first decompose/rewrite (Pattern 4), a deterministic evaluator, and the critic on Anthropic. Provider 429 after bounded retry → `PROVIDER_ERROR`, never a fabricated answer.

### Pitfall 6: Compound questions with partial coverage
**What goes wrong:** One sub-query is strong, one is weak, and the drafter answers the covered half and guesses the rest.
**How to avoid:** Require all sub-queries to be covered (Pattern 4). After retries are exhausted, abstain. (Alternative: answer with an explicit "no evidence for X" statement. This is a discretion item, see Open Questions.)

### Pitfall 7: HITL corrections pollute run history and eval F1
**What goes wrong:** `upsert_extraction_record(record)` with `record.run_id` set runs `ON CONFLICT DO UPDATE` on `extraction_history` and `compliance_record_history` for that run. `extraction_eval_runner` scores by run, so human values would inflate model F1.
**How to avoid:** `apply_field_review` updates only `extractions` + `compliance_records` + inserts into `extraction_reviews`. Test: after a correction, `extraction_history` rows for the run are byte-identical.

### Pitfall 8: `ExtractedField` validators reject corrected or absent values
**What goes wrong:** A non-abstained field requires a value **and** `evidence.verbatim_span`, and `evidence_type` must be `text|visual`. A correction to a previously abstained field has no span. For `ABSTAINED`, `needs_review` is a computed property that is always True, so "confirm absent" can never leave the queue through the model alone.
**How to avoid:** (a) Extend the `SourceEvidence.evidence_type` validator to allow `"human"`. For `CORRECT`, set `verbatim_span` to the reviewer-entered value (or the original span if present) and `evidence_type="human"`, and require a source page. Grep all `evidence_type` consumers (`src/extraction/pipeline.py`, `repository.py`, dashboard, eval) so `"human"` is handled. (b) Keep `CONFIRM_ABSENT` fields `ABSTAINED` (with abstention_reason prefixed `"Reviewer confirmed: "`) and exclude them from the queue through the `extraction_reviews` NOT EXISTS clause. For `compliance_records.needs_review`, compute it in `apply_field_review` as "any field still unresolved", where confirmed-absent counts as resolved.

### Pitfall 9: Streamlit form/key collisions and stale queues
**What goes wrong:** Duplicate widget keys across queue items raise `DuplicateWidgetID`. After submit, the queue shows stale data until the next interaction.
**How to avoid:** Keys include `doc_id` + `field_name`. Call `st.rerun()` after a successful write. Keep the selection in `st.session_state` (`pfizer_review_selected`).

### Pitfall 10: Phase tag missing on early spans / on CLI traces
**What goes wrong:** `propagate_attributes` only affects the current span and spans created afterward. The existing `safe_update_current_trace(tags=[...])` calls in retriever/service pass tags but no phase.
**How to avoid:** Open `trace_session` at each entry point **before** the first `@observe` span, or as the first statement inside a root `@observe` wrapper. Also add `phase` automatically in `safe_update_current_trace` (append the current phase tag from a module-level `ContextVar` set by `trace_session`). Test: fake context records `tags` containing `"phase2"` for the retriever, service, and extraction updates.

### Pitfall 11: Traces lost on short-lived processes / Streamlit sessions
**What goes wrong:** Spans are batched. CLI exits normally flush through the SDK's atexit hook (resource_manager registers atexit [VERIFIED in wheel]). Streamlit reruns can drop the tail.
**How to avoid:** Call `get_client().flush()` (guarded, no-raise) at the end of each Chat/Review submit handler.

## Code Examples

### Graph builder (verified API on langgraph 1.0.1 + langchain-core 0.3.86 via local smoke run)
```python
# src/rag/agentic/graph.py
def build_agentic_graph(deps: "AgenticDeps"):
    from langgraph.graph import END, START, StateGraph  # lazy: keeps src.rag import light

    from src.rag.agentic import nodes, routing
    from src.rag.agentic.state import AgenticState

    b = StateGraph(AgenticState)
    b.add_node("decompose", lambda s: nodes.decompose(s, deps))
    b.add_node("retrieve", lambda s: nodes.retrieve(s, deps))
    b.add_node("evaluate", lambda s: nodes.evaluate(s, deps))
    b.add_node("rewrite", lambda s: nodes.rewrite(s, deps))
    b.add_node("draft", lambda s: nodes.draft(s, deps))
    b.add_node("critique", lambda s: nodes.critique(s, deps))
    b.add_node("finalize", lambda s: nodes.finalize(s, deps))
    b.add_node("abstain", lambda s: nodes.abstain(s, deps))

    b.add_edge(START, "decompose")
    b.add_edge("decompose", "retrieve")
    b.add_edge("retrieve", "evaluate")
    b.add_conditional_edges("evaluate", routing.route_after_evaluate,
                            {"draft": "draft", "rewrite": "rewrite", "abstain": "abstain"})
    b.add_edge("rewrite", "retrieve")
    b.add_edge("draft", "critique")
    b.add_conditional_edges("critique", routing.route_after_critique,
                            {"finalize": "finalize", "draft": "draft", "abstain": "abstain"})
    b.add_edge("finalize", END)
    b.add_edge("abstain", END)
    return b.compile()
```
Invocation (errors from the draft provider route to `abstain`/`provider_error` inside nodes, never raised out):
```python
@observe(name="rag.agentic", capture_input=False, capture_output=False)
def answer_question_agentic(db_path, question, *, provider, critic=None, top_k=5) -> AnswerResult:
    graph = build_agentic_graph(AgenticDeps(db_path=db_path, answer_provider=provider, critic=critic, top_k=top_k))
    config = {"recursion_limit": GRAPH_RECURSION_LIMIT}
    handler = build_callback_handler()
    if handler is not None:
        config["callbacks"] = [handler]
    try:
        final = graph.invoke({"question": question, "retrieval_round": 0, "regeneration_count": 0, "steps": []}, config)
    except GraphRecursionError:
        return _abstained(..., reason_code=AnswerReasonCode.RETRIEVAL_EXHAUSTED, error_class="GraphRecursionError")
    return _result_from_state(final)   # builds AnswerResult + agentic diagnostics
```

### Langfuse v3 session + tags (verified in langfuse 3.15.0 wheel; `propagate_attributes` exists since 3.9.0)
```python
from contextlib import contextmanager, nullcontext

@contextmanager
def trace_session(*, phase: str, session_id: str | None = None, tags=(), metadata=None):
    cm = nullcontext()
    if _ensure_langfuse_initialized():
        try:
            from langfuse import propagate_attributes
            safe_meta = {k: str(v) for k, v in filter_trace_metadata(metadata, _SESSION_KEYS).items()}
            cm = propagate_attributes(tags=[phase, *tags], session_id=session_id,
                                      metadata={"phase": phase, **safe_meta})
        except Exception:
            cm = nullcontext()
    token = _CURRENT_PHASE.set(phase)
    try:
        with cm:
            yield
    finally:
        _CURRENT_PHASE.reset(token)
```
The CallbackHandler also honors `config["metadata"]["langfuse_tags" | "langfuse_session_id"]` [VERIFIED: `langfuse/langchain/CallbackHandler.py` in 3.15.0; CITED: langfuse.com/docs/integrations/langchain/tracing].

### Global mask wiring
```python
_Langfuse(public_key=..., secret_key=..., host=..., mask=mask_trace_payload)
# MaskFunction protocol: __call__(self, *, data: Any, **kwargs) -> Any   [VERIFIED: langfuse/types.py]
```

### Claude critic adapter (anthropic 1.x: no `temperature` kwarg)
```python
class CriticVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    verdict: Literal["supported", "partially_supported", "unsupported"]
    faithfulness: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=5)

def critique(self, request: CriticRequest) -> CriticVerdict:
    msg = self._get_client().messages.create(
        model=self.model,                      # "claude-sonnet-4-6"
        max_tokens=512,
        system=CRITIC_SYSTEM_PROMPT,           # "judge ONLY against <evidence>; output JSON {verdict, faithfulness, unsupported_claims}"
        messages=[{"role": "user", "content": _build_critic_prompt(request)}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return CriticVerdict.model_validate_json(_strip_simple_fences(text))   # ValidationError → CriticValidationError
```
Accept iff `verdict == "supported" and faithfulness >= critic_min_faithfulness`. `unsupported_claims` go only into the regen prompt, never into traces or the UI.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `langfuse.decorators.langfuse_context` (v2) | `from langfuse import observe, get_client, propagate_attributes` (v3) | v3 (2025); `propagate_attributes` in 3.9.0 | Already migrated (quick 260610-2y6). Use `propagate_attributes` for tags/session |
| `update_current_trace(tags=...)` | `propagate_attributes(...)` | 3.9+ docstring: "See Also: propagate_attributes: Recommended replacement" | Keep `safe_update_current_trace` for metadata. Use propagation for phase/session |
| anthropic 0.x `messages.create(temperature=0)` | 1.x: sampling kwargs removed (use `extra_body` if needed) | anthropic 1.0.0, 2026-08-20 | Don't pass `temperature` |
| LangGraph default recursion_limit 25 | 10007 in current main | after 1.0.x | On 1.0.1 it is 25. Set explicitly |

**Deprecated/outdated:** CLAUDE.md's `langgraph>=1.1.0` recommendation. It is incompatible with the project's own RAGAS pin (see Pitfall 1).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | User accepts `langgraph==1.0.1` instead of the CLAUDE.md `>=1.1` floor | Standard Stack | If rejected: RAGAS must be isolated or upgraded, which is a large re-scope |
| A2 | "phase tag" means pipeline phase labels `phase1`/`phase2` (linear vs agentic), consistent with existing `tags=["phase1", ...]` in ingest and ARCHITECTURE.md `session_tags=["phase1"\|"phase2"]` | Pattern 7 | Wrong filter semantics for the Phase 7 benchmark. Cheap to change (one constant map) |
| A3 | Chat tab defaults to `rag_pipeline="agentic"`. The eval harness stays `linear` unless told otherwise | Pattern 1 | Demo shows the baseline instead of the upgrade, or eval numbers shift unexpectedly |
| A4 | Critic failure → abstain (fail-closed), including a missing `ANTHROPIC_API_KEY` when no Gemini fallback is configured | Anti-patterns | Higher abstention in demos without an Anthropic key. Mitigation: `critic_provider="gemini"` fallback setting |
| A5 | Human-corrected fields get `confidence=1.0`, `review_state="reviewed"`, `evidence_type="human"` | Pitfall 8 | Aggregate confidence semantics change. The audit table keeps the originals |
| A6 | Compound questions require every sub-query covered; otherwise abstain | Pattern 4 / Pitfall 6 | Over-abstention on multi-part questions |
| A7 | Reviewer identity is a free-text/default value (no auth; RBAC out of scope) | Pattern 5 | Weak audit attribution. Acceptable for a single-user demo |
| A8 | Langfuse merges tags from `propagate_attributes` with tags from `update_current_trace` (union) rather than replacing them | Pitfall 10 | Phase tag could be overwritten by a later module tag update. Mitigated by also injecting the phase into `safe_update_current_trace` |

## Open Questions (RESOLVED)

1. **LangGraph version deviation (A1).** Recommendation: pin 1.0.1 and log a decision. Surface this to the user at plan approval. **RESOLVED:** user locked D-01 (`langgraph==1.0.1`, recorded as D028 in 06-01).
2. **Critic fallback when no Anthropic key.** Recommendation: `critic_provider: "anthropic" | "gemini"`, default `"anthropic"`. If the key is missing, the Chat tab shows a config hint and the agentic path abstains with `CRITIC_ERROR`. Using a Gemini fallback is an explicit opt-in. **RESOLVED:** user locked D-02 (fail closed; Gemini opt-in only; 06-01/06-04).
3. **Should "confirm absent" be in scope?** Recommendation: yes. It is small with the audit-table approach, and abstained fields otherwise stay in the queue forever. **RESOLVED:** in scope via 06-02 `CONFIRM_ABSENT`.
4. **Should visual-fused retrieval be used inside the agentic graph?** Local `visual-fused` raises by design (no GPU). The graph calls `retrieve_evidence` with the configured `retrieval_mode`, so it inherits whatever is configured. Do not add GPU work in this phase. **RESOLVED:** graph inherits `retrieval_mode` (06-01/06-05); no GPU work.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (Windows venv) | all | ✓ | 3.11.9 | — |
| langfuse | OBS-01 | ✓ | 3.14.6 (≥3.9 needed for `propagate_attributes`) | — |
| langchain-core | langgraph + CallbackHandler | ✓ | 0.3.86 | — |
| langgraph | RAG-03 | ✗ (stray dir only) | — | Install `langgraph==1.0.1` (Wave 0) |
| anthropic | critic | ✗ | — | Install `anthropic>=1,<2`. Gemini critic fallback |
| google-genai | draft/decompose | ✓ | 2.7.0 | — |
| streamlit | HITL tab | ✓ | 1.56.0 | — |
| pytest / pytest-socket | validation | ✓ | 9.0.3 / 0.8.0 | — |
| ANTHROPIC_API_KEY / GEMINI_API_KEY / LANGFUSE keys | live demo only | unknown (not needed for tests) | — | Offline fakes. Langfuse no-op |

**Missing, no fallback:** none. **Missing, with fallback:** langgraph and anthropic (installable in Wave 0).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (+ pytest-cov, pytest-socket) |
| Config file | `pytest.ini` / `pyproject.toml` (`addopts = -x --tb=short`, `gpu` marker) |
| Quick run command | `venv\Scripts\python.exe -m pytest tests/rag/agentic tests/test_review_repository.py tests/test_dashboard_review_tab.py tests/test_tracing_phase.py -q` |
| Full suite command | `venv\Scripts\python.exe -m pytest -q -m "not gpu"` |
| Offline proof (phase gate) | `venv\Scripts\python.exe -m pytest -q -m "not gpu" -p pytest_socket --disable-socket --allow-unix-socket` (drop the flag if `test_app.py` needs localhost) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RAG-03 | Pinned langgraph 1.0.1 + langchain-core 0.3.x importable; trivial graph compiles | unit | `venv\Scripts\python.exe -m pytest tests/rag/agentic/test_stack_pins.py -x` | ❌ Wave 0 |
| RAG-03 | Router functions: sufficient→draft; insufficient→rewrite while rounds<3; →abstain at 3 | unit | `... -m pytest tests/rag/agentic/test_routing.py -x` | ❌ Wave 0 |
| RAG-03 | Always-weak fake retriever → exactly 3 retrieve calls, ABSTAINED/RETRIEVAL_EXHAUSTED, provider never called | integration (graph, fakes) | `... -m pytest tests/rag/agentic/test_graph.py::test_retrieval_retries_capped -x` | ❌ Wave 0 |
| RAG-03 | Weak then strong on retry → answered with retrieval_rounds=2 | integration | `...test_graph.py::test_reretrieve_recovers -x` | ❌ Wave 0 |
| RAG-03 | Critic rejects twice → exactly 2 drafts, 2 critiques, ABSTAINED/CRITIC_REJECTED | integration | `...test_graph.py::test_regeneration_capped_then_abstain -x` | ❌ Wave 0 |
| RAG-03 | Critic rejects then accepts → ANSWERED, regeneration_count=1 | integration | `...test_graph.py::test_regenerate_then_accept -x` | ❌ Wave 0 |
| RAG-03 / SC-4 | Critic raises / malformed JSON / missing → ABSTAINED/CRITIC_ERROR (fail closed) | integration | `...test_graph.py::test_critic_failure_fails_closed -x` | ❌ Wave 0 |
| RAG-03 | Citations only from retrieval hits (provider text containing fake citations ignored) | integration | `...test_graph.py::test_citations_service_owned -x` | ❌ Wave 0 |
| RAG-03 | Compound decomposition (heuristic + malformed-LLM fallback), ≤3 sub-queries | unit | `... -m pytest tests/rag/agentic/test_decompose_rewrite.py -x` | ❌ Wave 0 |
| RAG-03 | Anthropic/Gemini critic adapters with injected fake clients: parse, fences, validation error, no `temperature` kwarg | unit | `... -m pytest tests/rag/test_critic_provider.py -x` | ❌ Wave 0 |
| RAG-03 | Chat tab routes to agentic when `rag_pipeline="agentic"`; new reason codes have hints; agentic diagnostics rendered bounded | unit (FakeStreamlit) | `... -m pytest tests/test_dashboard_chat_tab.py tests/test_chat_dashboard.py -x` | ✅ extend |
| RAG-03 | `answer_question_agentic` usable as `answer_fn` in `compute_ragas_quality` (signature compat) | unit | `... -m pytest tests/rag/agentic/test_graph.py::test_eval_answer_fn_compat -x` | ❌ Wave 0 |
| HITL-01 | Queue lists needs_review, abstained, conf<τ. Excludes reviewed and confirmed-absent. Ordered by confidence | unit (tmp sqlite) | `... -m pytest tests/test_review_repository.py::test_queue_selection -x` | ❌ Wave 0 |
| HITL-01 | Correct date field → extractions updated, compliance_records field + risk recomputed, audit row inserted | unit | `...test_review_repository.py::test_correct_updates_compliance_db -x` | ❌ Wave 0 |
| HITL-01 | Approve / confirm_absent semantics. Invalid date rejected with no write (transaction rollback) | unit | `...test_review_repository.py -k "approve or absent or invalid" -x` | ❌ Wave 0 |
| HITL-01 | extraction_history / compliance_record_history unchanged after review | unit | `...test_review_repository.py::test_history_untouched -x` | ❌ Wave 0 |
| HITL-01 | Schema migration idempotent (init_db twice). extraction_reviews exists | unit | `... -m pytest tests/test_db.py -k review -x` | ✅ extend |
| HITL-01 | Review tab renders queue, form submit calls apply_fn with the right args, empty-state, error display bounded | unit (FakeStreamlit) | `... -m pytest tests/test_dashboard_review_tab.py -x` | ❌ Wave 0 |
| HITL-01 | App has 4 tabs incl. Review; headless start | smoke | `... -m pytest tests/test_app.py -x` | ✅ extend |
| OBS-01 | `trace_session` is a no-op without keys/SDK, never raises. Sets phase ContextVar | unit | `... -m pytest tests/test_tracing_phase.py -x` | ❌ Wave 0 |
| OBS-01 | `safe_update_current_trace` auto-appends the active phase tag (retriever, service, extraction, review fake contexts) | unit | `...test_tracing_phase.py::test_phase_tag_on_all_boundaries -x` | ❌ Wave 0 |
| OBS-01 | `mask_trace_payload` strips evidence_text/snippet/page_text/question/secrets/bytes from nested state | unit | `...test_tracing_phase.py::test_mask_redacts_state -x` | ❌ Wave 0 |
| OBS-01 | `build_callback_handler()` returns None when disabled. Graph passes it in config when present (spy) | unit | `...test_tracing_phase.py::test_callback_handler_wiring -x` | ❌ Wave 0 |
| OBS-01 | Entry points (Chat submit, Review submit, extraction/retrieval/eval CLIs) open `trace_session` with the phase (monkeypatched spy) | unit | `... -m pytest tests/test_tracing_phase.py::test_entry_points_open_session -x` | ❌ Wave 0 |
| OBS-01 | Langfuse pin still v3 | unit | `... -m pytest tests/test_tracing.py::test_langfuse_v3_pinned -x` | ✅ |
| OBS-01 | Live trace shows root + node + generation spans with `phase2` tag | **manual** (needs Langfuse keys) | Run one chat question, inspect Langfuse UI; record trace URL in SUMMARY | manual-only |
| SC-4 | Cross-path abstention: extraction abstains on ungrounded span AND agentic RAG abstains on weak evidence / critic reject | unit | `... -m pytest tests/test_extraction_pipeline.py tests/rag/agentic/test_graph.py -k abstain -x` | ✅ partial |

### Sampling Rate
- **Per task commit:** quick run command (phase-specific files, < 30 s)
- **Per wave merge:** `venv\Scripts\python.exe -m pytest -q -m "not gpu"`
- **Phase gate:** full suite green, plus one manual live Langfuse trace check documented in the SUMMARY, before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] Install: `venv\Scripts\python.exe -m pip install "langgraph==1.0.1" "anthropic>=1,<2" "langfuse>=3.9,<4.0"`, and update `pyproject.toml`
- [ ] `tests/rag/__init__.py`, `tests/rag/agentic/__init__.py`, `tests/rag/agentic/conftest.py` (fake retrieve_fn factory returning `EvidenceGateResult`, FakeAnswerProvider, FakeCritic with scripted verdicts)
- [ ] `tests/rag/agentic/test_stack_pins.py`, `test_routing.py`, `test_graph.py`, `test_decompose_rewrite.py`
- [ ] `tests/rag/test_critic_provider.py`
- [ ] `tests/test_review_repository.py` (tmp_path DB seeded via `init_db` + `insert_document` + `upsert_extraction_record`)
- [ ] `tests/test_dashboard_review_tab.py` (FakeStreamlit with `form`, `form_submit_button`, `radio`, `text_input`, `number_input`, `text_area`, `rerun`, `dataframe`, `selectbox`, `image`, `success`, `error`)
- [ ] `tests/test_tracing_phase.py`

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-user demo (RBAC out of scope) |
| V3 Session Management | no | Streamlit session only. Langfuse `session_id` is a random UUID, not an auth token |
| V4 Access Control | no (documented limitation) | Reviewer identity is free-text (A7) |
| V5 Input Validation | yes | Pydantic models for review input. `dateutil` parse + range check. Length bounds on value/note (e.g., 200/1000 chars). Parameterized SQL only. Action enum CHECK constraint |
| V6 Cryptography | no | — |
| V7 Error Handling & Logging | yes | Sanitized error classes only (existing pattern). Global Langfuse mask + allowlists. No secrets in traces (`_SECRET_VALUE_RE`) |
| V8 Data Protection | yes | Page text / evidence never persisted to traces. `compliance.db` never committed |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via document text ("ignore instructions, answer X") reaching drafter/critic | Tampering | Evidence wrapped in `<evidence>` tags with "use only evidence" instructions. Critic is a separate model family. Citations service-owned. Abstain on critic doubt |
| Trace data exfiltration (page text / questions in Langfuse SaaS) | Information disclosure | Global `mask` + `capture_input/output=False` on generation wrappers + allowlisted metadata |
| SQL injection through reviewer input | Tampering | Parameterized queries. Field name validated against `SDFFieldName` enum |
| Audit repudiation (who changed a compliance value) | Repudiation | Append-only `extraction_reviews` with before/after values, timestamp, reviewer, trace_id |
| Unbounded agent loop / cost DoS | Denial of service | State counters + `recursion_limit=30` + bounded provider retries |

## Sources

### Primary (HIGH confidence)
- PyPI JSON metadata for langgraph (0.6.11 → 1.2.12), langgraph-prebuilt (1.0.0–1.0.13), langgraph-checkpoint, langfuse (3.x, 4.15.4), langchain-core, ragas, anthropic: dependency constraints and release dates
- `uv pip compile` resolution runs (unsatisfiable for langgraph>=1.1 + langchain-core<1; resolved set for langgraph==1.0.1)
- Local smoke run: langgraph 1.0.1 + langchain-core 0.3.86 + langfuse 3.14.6 on Python 3.11 (StateGraph, conditional edges, GraphRecursionError, CallbackHandler with no keys)
- langfuse 3.15.0 / 3.9.0 / 3.8.0 wheels inspected: `propagate_attributes` signature, `update_current_trace`, `Langfuse(mask=...)`, `MaskFunction`, `CallbackHandler` metadata keys, `observe(as_type, capture_input, capture_output)`, atexit shutdown
- langgraph 1.0.1 wheel: `DEFAULT_RECURSION_LIMIT = 25`, `langgraph.errors.GraphRecursionError`
- Context7 `/langchain-ai/langgraph`: StateGraph / add_conditional_edges / recursion_limit usage
- Windows venv `site-packages` listing (installed versions) and `pyvenv.cfg`
- Codebase: `src/rag/*`, `src/retrieval/retriever.py`, `src/retrieval/models.py`, `src/extraction/{models,pipeline,repository,risk}.py`, `src/db/schema.py`, `src/tracing.py`, `src/config.py`, `src/dashboard/*`, `tests/test_tracing.py`, `tests/test_dashboard_chat_tab.py`, `.planning/research/{ARCHITECTURE,PITFALLS}.md`, `.gsd/DECISIONS.md` (D016, D027), Phase 5 CONTEXT/SUMMARYs

### Secondary (MEDIUM confidence)
- [Langfuse LangChain/LangGraph integration docs](https://langfuse.com/docs/integrations/langchain/tracing): `from langfuse.langchain import CallbackHandler`, `langfuse_tags` / `langfuse_session_id` metadata
- [anthropic-sdk-python v1.0.0 MIGRATION.md](https://github.com/anthropics/anthropic-sdk-python/blob/v1.0.0/MIGRATION.md): sampling kwargs removed, `output_config`, httpx2
- [anthropic on PyPI](https://pypi.org/project/anthropic/): 1.8.0 latest, Python ≥3.10
- [Claude Sonnet 4.6 announcement](https://www.anthropic.com/news/claude-sonnet-4-6) / [Model IDs docs](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions): `claude-sonnet-4-6` model ID

### Tertiary (LOW confidence)
- None relied upon for recommendations

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. Resolver-verified and smoke-tested with the exact installed versions.
- Architecture: HIGH for the integration seams (read from code). MEDIUM for policy thresholds (design choices, see Assumptions).
- Pitfalls: HIGH. Most were confirmed in code or package source (history upsert, validators, recursion default, I/O capture).

**Research date:** 2026-09-23
**Valid until:** 2026-10-23 (the langgraph/langchain/anthropic ecosystem moves fast. Re-check if the RAGAS pin changes)
