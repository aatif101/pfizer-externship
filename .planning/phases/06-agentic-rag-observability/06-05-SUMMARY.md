---
phase: 06-agentic-rag-observability
plan: 05
subsystem: rag
tags: [langgraph, agentic-rag, query-decomposition, query-rewrite, langfuse, observability]

requires:
  - phase: 06-01
    provides: agentic StateGraph topology, AgenticDeps/AgenticState, decompose/rewrite node stubs
  - phase: 06-03
    provides: observe, safe_update_current_span allowlisted span helper
  - phase: 06-04
    provides: provider.complete_text wired as default decomposer/rewriter
provides:
  - Deterministic-first question decomposition (is_compound, heuristic_split, bounded LLM parse with heuristic fallback)
  - Pharma-domain synonym query rewrite with LLM fallback and tried-set monotonic-progress guard
  - Per-sub-query retrieval that re-retrieves only failing sub-queries; compound partial coverage abstains
  - agent.decompose|retrieve|evaluate|rewrite|draft|critique|finalize|abstain Langfuse spans with allowlisted metadata
affects: [06-06, 06-07, 06-08, chat, eval]

actuals:
  tokens: 9500
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Public node = @observe(name='agent.<node>', capture off) wrapper calling private _<node> impl, then _span_meta(allowlisted metadata)"
    - "LLM helpers in the graph are optional refinements over a deterministic default; malformed LLM output falls back, never abstains"

key-files:
  created:
    - src/rag/agentic/decompose.py
    - src/rag/agentic/rewrite.py
    - tests/rag/agentic/test_decompose_rewrite.py
  modified:
    - src/rag/agentic/nodes.py

key-decisions:
  - "doc_type field mentions exclude bare coa/coq/certificate: those are usually the question subject, and counting them would decompose single-intent questions like 'expiry date of the Sigma CoA'"
  - "rewrite_query strips a verbatim prompt echo before parsing, so an echoing LLM counts as no progress (keeps 06-01 fakes green unchanged and guards real models)"
  - "DOMAIN_SYNONYMS also maps expire/expires/expired/expiration to the expiry synonyms so natural-language 'when does it expire' questions get a deterministic rewrite before any LLM call"

patterns-established:
  - "Node span metadata allowlist (_NODE_SPAN_ALLOWED_KEYS) plus module seams _LANGFUSE_AVAILABLE / langfuse_context in nodes.py"

requirements-completed: [RAG-03, OBS-01]

coverage:
  - id: D1
    description: "Deterministic-first decomposition: single-intent never decomposed or LLM-called; compound split capped at 3; malformed LLM output falls back to heuristic"
    requirement: RAG-03
    verification:
      - kind: unit
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_decompose_single_never_calls_llm"
        status: pass
      - kind: unit
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_decompose_compound_llm_garbage_falls_back"
        status: pass
      - kind: unit
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_parse_llm_subqueries_rejects_malformed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Synonym-first rewrite with LLM fallback and tried-set progress guard"
    requirement: RAG-03
    verification:
      - kind: unit
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_rewrite_query_synonyms_first"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_synonym_rewrite_recovers"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_rewrite_no_progress_abstains"
        status: pass
    human_judgment: false
  - id: D3
    description: "Compound questions retrieve per sub-query, merge/dedupe citations, and abstain on partial coverage"
    requirement: RAG-03
    verification:
      - kind: integration
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_compound_question_retrieves_each_subquery"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_compound_partial_coverage_abstains"
        status: pass
    human_judgment: false
  - id: D4
    description: "Per-node agent.* Langfuse spans with allowlisted, content-free metadata"
    requirement: OBS-01
    verification:
      - kind: integration
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_node_spans_allowlisted"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_decompose_rewrite.py#test_node_spans_disabled_seam"
        status: pass
    human_judgment: false
  - id: D5
    description: "agent.* spans render as nested observations in a live Langfuse project"
    requirement: OBS-01
    verification: []
    human_judgment: true
    rationale: "Offline tests use a recording context seam; nesting in the real Langfuse UI needs live keys and a human look"

duration: 5min
completed: 2026-09-25
status: complete
---

# Phase 6 Plan 05: Decompose, Re-retrieve, and Node Spans Summary

**Deterministic-first compound-question decomposition, pharma-synonym query rewriting with a monotonic-progress guard, and one allowlisted agent.* Langfuse span per graph node**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-25T02:10:02Z
- **Completed:** 2026-09-25T02:15:08Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `decompose.py`: `is_compound` (2+ `?`, comparison, or 2+ SDF field mentions), `heuristic_split` keeping shared subject tokens ("expiry date Sigma CoA" / "manufacturing date Sigma CoA"), bounded `parse_llm_subqueries` (fences, list[str], 200-char items, cap 3), `decompose_question` returning single/heuristic/llm/llm_fallback without ever raising.
- `rewrite.py`: `DOMAIN_SYNONYMS` expansion (idempotent, returns None when nothing new), single-line `parse_llm_rewrite`, and `rewrite_query` that tries synonyms, then the LLM, and rejects any candidate already tried (case- and whitespace-insensitive).
- `nodes.py`: decompose/rewrite nodes use the new modules; only weak sub-queries are re-retrieved; a compound question is answered only when every original sub-query is strong. All 8 nodes are wrapped in `@observe(name="agent.<node>", capture_input=False, capture_output=False)` and emit only `_NODE_SPAN_ALLOWED_KEYS` metadata.

## Task Commits

1. **Task 1: Deterministic-first decomposition and domain-synonym rewrite** - `e923217` (test, RED), `59ae881` (feat, GREEN)
2. **Task 2: Wire decompose/rewrite into graph nodes + allowlisted spans** - `2597a38` (test, RED), `1e32a8f` (feat, GREEN)

## Files Created/Modified
- `src/rag/agentic/decompose.py` - FIELD_MENTIONS, is_compound, heuristic_split, build_decompose_prompt, parse_llm_subqueries, decompose_question
- `src/rag/agentic/rewrite.py` - DOMAIN_SYNONYMS, expand_with_synonyms, build_rewrite_prompt, parse_llm_rewrite, rewrite_query
- `src/rag/agentic/nodes.py` - decompose/rewrite wiring, _NODE_SPAN_ALLOWED_KEYS, _span_meta, _LANGFUSE_AVAILABLE/langfuse_context seams, 8 agent.* spans
- `tests/rag/agentic/test_decompose_rewrite.py` - 41 pure and graph-level tests

## Decisions Made
See key-decisions in frontmatter. All other behavior follows the plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] doc_type mentions exclude bare coa/coq/certificate**
- **Found during:** Task 1
- **Issue:** The plan's FIELD_MENTIONS put `coa`, `coq`, and `certificate` under doc_type. With those, "What is the expiry date of the Sigma CoA?" counts two fields and is_compound returns True, which contradicts the plan's own required behavior (it must be False).
- **Fix:** doc_type phrases are now "document type", "type of document", and "doc type".
- **Files modified:** src/rag/agentic/decompose.py
- **Verification:** test_is_compound_single_intent_false passes
- **Committed in:** 59ae881

**2. [Rule 1 - Bug] Prompt-echo stripping in rewrite_query**
- **Found during:** Task 1 design (checked against the 06-01 tests)
- **Issue:** Now that the rewriter receives a prompt instead of the raw query, the 06-01 fakes (`lambda q: q` and `f"{q} variant N"`) echo the prompt back. Taking the "first non-empty line" of the echo alone would either loop on a constant instruction line or treat a pure echo as progress, which breaks test_rewriter_repeating_query_stops_early or test_retrieval_retries_capped_abstain.
- **Fix:** rewrite_query removes a verbatim leading prompt echo before parse_llm_rewrite. A pure echo becomes empty, which means no progress.
- **Files modified:** src/rag/agentic/rewrite.py
- **Verification:** all 06-01 test_graph tests pass unchanged; test_rewrite_query_llm_echo_is_no_progress passes
- **Committed in:** 59ae881

**3. [Rule 2 - Missing critical] expire/expires/expired/expiration synonym keys**
- **Found during:** Task 1
- **Issue:** Most natural questions say "expire", not "expiry", so they would get no deterministic rewrite and would spend LLM quota instead.
- **Fix:** Added these keys, mapped to the expiry synonym set.
- **Files modified:** src/rag/agentic/rewrite.py
- **Committed in:** 59ae881

---

**Total deviations:** 3 auto-fixed (2 bug, 1 missing critical)
**Impact on plan:** These were needed to meet the plan's own behavior spec and to keep the 06-01 tests green unchanged. No scope creep.

## Issues Encountered
None

## Verification
- `venv/bin/python -m pytest tests/rag/agentic -q`: 101 passed
- `venv/bin/python -m pytest -q -m "not gpu"`: 575 passed, 7 skipped
- Acceptance greps: 4 decompose defs; at least 3 rewrite symbols; no langgraph/google/anthropic in the pure modules; 2 decompose_question/rewrite_query call sites; 8 `@observe(name="agent.` decorators; allowlist has no content keys

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Ready for 06-06. RAG-03/OBS-01 checkboxes stay unticked until 06-08.

---
*Phase: 06-agentic-rag-observability*
*Completed: 2026-09-25*

## Self-Check: PASSED
