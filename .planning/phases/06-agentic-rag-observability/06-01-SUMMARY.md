---
phase: 06-agentic-rag-observability
plan: 01
subsystem: rag
tags: [langgraph, agentic-rag, critic, pydantic, langfuse, anthropic]

requires:
  - phase: 05
    provides: linear answer_question service, retrieval evidence gate, eval harness answer_fn seam
provides:
  - "langgraph==1.0.1 / anthropic>=1,<2 / langfuse>=3.9,<4.0 pins with D028 decision record"
  - "src/rag/agentic: build_agentic_graph, answer_question_agentic (bounded LangGraph graph returning AnswerResult)"
  - "src/rag/critic.py: CriticProvider/CriticVerdict/CriticRequest contracts, typed critic errors, parse_critic_verdict"
  - "AnswerReasonCode retrieval_exhausted/critic_rejected/critic_error; agentic AnswerDiagnostics fields; AnswerProviderRequest.revision_hint"
affects: [06-04 critic adapters, 06-05 decompose/rewrite, 06-08 chat default, eval harness, phase 7]

actuals:
  tokens: 14360
  tasks: 2
  commits: 4

tech-stack:
  added: [langgraph 1.0.1, anthropic 1.8.0, langfuse 3.15.0]
  patterns:
    - "Nodes are plain functions node(state, deps) -> partial dict; langgraph imported lazily only in graph.py"
    - "Loop bounds enforced by pure routers over state counters, with recursion_limit=30 as a backstop"
    - "Fail closed: missing/erroring/malformed critic -> ABSTAINED critic_error; provider never called when no critic"

key-files:
  created:
    - src/rag/critic.py
    - src/rag/agentic/__init__.py
    - src/rag/agentic/state.py
    - src/rag/agentic/routing.py
    - src/rag/agentic/nodes.py
    - src/rag/agentic/graph.py
    - tests/rag/agentic/test_graph.py
    - tests/rag/agentic/test_routing.py
    - tests/rag/agentic/test_critic_contract.py
  modified:
    - pyproject.toml
    - CLAUDE.md
    - .gsd/DECISIONS.md
    - src/rag/models.py
    - src/rag/providers.py

key-decisions:
  - "D028: pin langgraph==1.0.1 because every langgraph>=1.1 needs langchain-core>=1.0, which conflicts with RAGAS 0.4.3"
  - "abstain node checks critic rejection before retrieval exhaustion (evidence can turn strong on round 3 and still be rejected)"
  - "finalize builds citations via _citations_from_hits from merged retrieval hits and fails closed if none exist"

patterns-established:
  - "Agentic state keys trace_id and citations added to AgenticState so provider trace ids and service-owned citations survive to the result builder"

requirements-completed: [RAG-03]

coverage:
  - id: D1
    description: "Stack pinned (langgraph 1.0.1 + langchain-core 0.3.x + langfuse >=3.9 + ragas importable) with D028 recorded"
    requirement: RAG-03
    verification:
      - kind: unit
        ref: "tests/rag/agentic/test_stack_pins.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "One question flows through the compiled LangGraph graph to an AnswerResult with agentic diagnostics"
    requirement: RAG-03
    verification:
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_answered_happy_path"
        status: pass
    human_judgment: false
  - id: D3
    description: "Retrieval capped at 3 rounds, regeneration capped at 1, gate thresholds never relaxed, recursion backstop abstains"
    requirement: RAG-03
    verification:
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_retrieval_retries_capped_abstain"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_regeneration_capped_then_abstain"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_gate_thresholds_never_relaxed"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_recursion_backstop"
        status: pass
      - kind: unit
        ref: "tests/rag/agentic/test_routing.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Critic failure (raise, validation error, missing, malformed) fails closed; citations only from retrieval hits"
    requirement: RAG-03
    verification:
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_critic_failure_fails_closed"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_citations_service_owned"
        status: pass
    human_judgment: false
  - id: D5
    description: "answer_question_agentic is call-compatible with the eval answer_fn seam; linear path and dashboard tests unaffected"
    requirement: RAG-03
    verification:
      - kind: integration
        ref: "tests/rag/agentic/test_graph.py#test_eval_answer_fn_compat"
        status: pass
      - kind: other
        ref: "venv/bin/python -m pytest -q -m 'not gpu' (442 passed, 7 skipped)"
        status: pass
    human_judgment: false

duration: 6min (this resumed session; prior executor's Task 1 scaffold time not measured)
completed: 2026-09-25
status: complete
---

# Phase 6 Plan 01: Agentic RAG Tracer Summary

**LangGraph 1.0.1 agentic RAG graph (decompose -> retrieve -> evaluate -> rewrite* -> draft -> critique -> finalize|abstain) that returns the shared AnswerResult. Retrieval is capped at 3 rounds and regeneration at 1, the critic fails closed, and citations come only from retrieval hits.**

## Performance

- **Duration:** about 6 min for this resumed session (01:32Z to 01:38Z). The previous executor's scaffold commit f94217c is not counted.
- **Started:** 2026-09-25T01:32:24Z
- **Completed:** 2026-09-25T01:38:30Z
- **Tasks:** 2/2
- **Files modified:** 14 source and doc files (plus the 4 test files from the WIP commit)

## Accomplishments
- Pinned `langgraph==1.0.1`, `anthropic>=1,<2` and `langfuse>=3.9,<4.0`. langchain-core stays at 0.3.86 and ragas 0.4.3 still imports. Added the D028 decision row and updated both langgraph rows in CLAUDE.md.
- Added `src/rag/critic.py` with `CriticVerdict` (pydantic, extra=ignore), the `CriticRequest` and `CriticProvider` protocol, three typed errors with `reason_code="critic_error"`, and `parse_critic_verdict` (fence stripping, validation mapped to `CriticValidationError`). No SDK is imported.
- Added the `src/rag/agentic/` package. It has pure routers, node functions with no langgraph import, and a lazily imported StateGraph. `answer_question_agentic` is decorated with `@observe(name="rag.agentic", capture_input=False, capture_output=False)` and never raises. A GraphRecursionError maps to ABSTAINED/retrieval_exhausted and any other error maps to ABSTAINED/retrieval_error.
- Extended the shared contracts: three new `AnswerReasonCode` values, six defaulted agentic `AnswerDiagnostics` fields, and `AnswerProviderRequest.revision_hint`. `src/rag/service.py` is unchanged.
- Added 48 offline agentic tests. The full non-GPU suite has 442 passed and 7 skipped, up from a 394-passed baseline.

## Task Commits

1. **Task 1 (RED scaffold from the previous executor):** `f94217c` (wip: stack pin tests plus fakes; reviewed and kept unchanged)
2. **Task 1 RED:** `ac970f1` (test: graph tracer tests)
3. **Task 1 GREEN:** `236cd96` (feat: pins, D028, contracts, agentic package)
4. **Task 2:** `94f1e89` (test: loop bounds, fail-closed critic, citations, recursion backstop, eval compatibility, critic parser)

## Files Created/Modified
- `pyproject.toml`: langgraph, anthropic and langfuse pins with comments
- `.gsd/DECISIONS.md`: D028 row
- `CLAUDE.md`: langgraph version cell and pinning-strategy row (no other lines touched)
- `src/rag/models.py`: new reason codes and agentic diagnostics fields
- `src/rag/providers.py`: `revision_hint` (in-memory only, never traced or persisted)
- `src/rag/critic.py`: critic contracts
- `src/rag/agentic/{__init__,state,routing,nodes,graph}.py`: the agentic pipeline
- `tests/rag/agentic/test_graph.py` (368 lines), `test_routing.py` (15 tests), `test_critic_contract.py`

## Decisions Made
- The abstain node checks for a critic rejection before it checks for retrieval exhaustion. Evidence can become strong on the last round and the draft can still be rejected afterwards.
- Below-threshold "supported" verdicts count as a rejection, which triggers one regeneration. They are not treated as an error (research A4).
- A critic that returns something other than a `CriticVerdict` is mapped to `error_class="CriticValidationError"`, so the run fails closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] finalize builds citations and fails closed when there are none**
- **Found during:** Task 1
- **Issue:** The plan built citations only in the result builder. An "answered" outcome with empty merged evidence would have returned an uncited answer, and the key_link expects `_citations_from_hits` in nodes.py.
- **Fix:** `finalize` calls `_citations_from_hits(evidence)` and stores the result in a new `citations` state key. If the tuple is empty, it abstains with retrieval_exhausted. `_result_from_state` uses those citations.
- **Files modified:** src/rag/agentic/nodes.py, src/rag/agentic/state.py, src/rag/agentic/graph.py
- **Committed in:** 236cd96

**2. [Rule 2 - Missing Critical] `trace_id` state key**
- **Found during:** Task 1
- **Issue:** The planned AgenticState had no field for the provider trace id, so ANSWERED and blank-answer results would lose it. The linear path keeps it.
- **Fix:** Added `trace_id` to AgenticState. The draft node sets it and the result builder reads it.
- **Committed in:** 236cd96

**3. [Rule 2 - Missing Critical] Malformed critic verdicts fail closed**
- **Found during:** Task 1
- **Issue:** The plan listed "malformed verdict" under critic_error, but the critique node did not type-check the verdict.
- **Fix:** A result that is not a `CriticVerdict` becomes critic_error with `CriticValidationError`. This is tested by test_malformed_critic_verdict_fails_closed.
- **Committed in:** 236cd96, 94f1e89

**4. [Environment override] WSL paths and install tool**
- Verification used `venv/bin/python -m pytest`, and installs used `uv pip`, as the orchestrator authorized. The PLAN verify commands were not rewritten. Packages were already installed by the previous executor, and langchain-core did not move.

**Extra tests (beyond plan):** empty question, repeated rewrite stopping early, critic_min_faithfulness override, provider exception, retrieval exception, malformed verdict, and the parse_critic_verdict contract.

---

**Total deviations:** 3 auto-fixed (all Rule 2) plus 1 environment override.
**Impact on plan:** These make the fail-closed and citation guarantees stricter. No architectural change.

## TDD Gate Compliance
- Task 1: the RED commits (`f94217c` scaffold, `ac970f1` graph tests) come before GREEN `236cd96`.
- Task 2: the tests passed on the first run. Task 1's implementation already included the plan's expected fixes (a) to (d): abstain reason selection, `revision_hint` only on regeneration, the `critic_min_faithfulness` threshold, and a module-global recursion limit. So Task 2 has a test-only commit and no separate RED-failure/GREEN pair. This is a warning, not a gap in coverage.

## Issues Encountered
None.

## Known Stubs
- `decompose` passes the question through as a single sub-query, and `deps.decomposer` is not used yet. This is intentional; plan 06-05 adds real decomposition. `rewrite` uses `deps.rewriter` when one is injected, and live rewriter wiring comes in 06-04/06-05.

## User Setup Required
None. The critic adapters that need `ANTHROPIC_API_KEY` arrive in 06-04.

## Next Phase Readiness
- 06-04 can implement `CriticProvider` adapters against `src/rag/critic.py` and set `AgenticDeps.critic_error_class`.
- 06-05 can use `deps.decomposer` and `deps.rewriter` inside the existing nodes.
- 06-08 can switch Chat to `answer_question_agentic`, which has the same call shape as `answer_question`.

---
*Phase: 06-agentic-rag-observability*
*Completed: 2026-09-25*

## Self-Check: PASSED
