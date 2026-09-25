---
phase: 06-agentic-rag-observability
plan: 03
subsystem: observability
tags: [langfuse, tracing, privacy, contextvars, settings, obs-01]

requires:
  - phase: 01
    provides: src/tracing.py (safe_update_current_trace, filter_trace_metadata, _ensure_langfuse_initialized)
provides:
  - trace_session(phase, session_id, tags, metadata) over Langfuse v3 propagate_attributes
  - current_phase() / _CURRENT_PHASE ContextVar, auto phase tag on every safe_update_current_trace
  - mask_trace_payload global Langfuse MaskFunction + _MASK_SAFE_KEYS
  - build_callback_handler(), flush_traces(), safe_update_current_span(), safe_update_current_generation()
  - Settings: anthropic_api_key, critic_provider, critic_model, critic_min_faithfulness, rag_pipeline, pipeline_phase
affects: [06-04, 06-05, 06-06, 06-07, 06-08, phase 7 benchmark]

actuals:
  tokens: 60000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Entry points open trace_session(phase=...); the phase ContextVar makes every downstream trace update carry the phase tag"
    - "Tags are emitted as [phase, *module_tags], first-occurrence dedup, so order is deterministic"
    - "Global Langfuse(mask=mask_trace_payload): allowlist-only keys, strings >64 chars redacted, objects/bytes/secrets dropped, depth cap 4"
    - "Test seams _propagate_attributes_factory / _callback_handler_factory; langfuse.langchain imported lazily inside a function"

key-files:
  created:
    - tests/test_tracing_phase.py
  modified:
    - src/tracing.py
    - src/config.py
    - .env.example

key-decisions:
  - "trace_session only propagates exceptions raised by the with-body; propagate factory, __enter__ and __exit__ failures fall back to a no-op"
  - "The mask drops None-valued entries from mappings and sequences (a dropped value never leaves an empty key behind)"
  - "Session metadata allowlist is {pipeline, entry_point, command}; values are stringified to satisfy propagate_attributes Dict[str, str]"

requirements-completed: []  # OBS-01 foundation only; entry-point wiring lands in 06-04..06-08

duration: 8 min
completed: 2026-09-24
---

# Phase 6 Plan 03: Phase-Tagged Tracing, Global Mask, and Phase 6 Settings Summary

**Langfuse v3 `propagate_attributes` trace sessions with a ContextVar phase tag that is added to every trace update, plus a global allowlist mask (`Langfuse(mask=mask_trace_payload)`) that strips page text, questions, drafts, and field values from auto-captured span I/O**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-25T01:49:30Z
- **Completed:** 2026-09-25T01:57:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `trace_session()` sets the active phase and, when Langfuse keys are present, enters `propagate_attributes(tags=[phase, *tags], session_id=..., metadata={"phase": phase, ...})`. Tracing errors never reach the caller.
- `safe_update_current_trace` prepends the active phase tag without duplicates. With no session active it behaves as before, so the existing tests pass unchanged.
- `mask_trace_payload` is wired into client construction. This closes the existing leak where default `capture_input=True` on `@observe` decorators sent the question text and `db_path` to Langfuse.
- Added the `build_callback_handler` (LangGraph), `flush_traces`, `safe_update_current_span`, and `safe_update_current_generation` helpers. None of them raise.
- Added the Phase 6 settings and matching `.env.example` entries. All secret values are left empty.

## Task Commits

1. **Task 1: Settings + trace_session + auto phase tag + callback handler + flush**
   - RED `cdc1360` (test), GREEN `d1aa430` (feat)
2. **Task 2: Global privacy mask + span/generation helpers**
   - RED `2790e68` (test), GREEN `57b9453` (feat)

## Files Created/Modified
- `src/tracing.py`: added PHASE_TAGS, _CURRENT_PHASE, current_phase, _SESSION_METADATA_KEYS, _ordered_unique_tags, trace_session, build_callback_handler, flush_traces, _MASK_SAFE_KEYS, mask_trace_payload, safe_update_current_span, safe_update_current_generation, and the test seams
- `src/config.py`: added six Phase 6 settings. `critic_min_faithfulness` is validated to the range 0..1
- `.env.example`: added ANTHROPIC_API_KEY (empty), CRITIC_*, RAG_PIPELINE, PIPELINE_PHASE
- `tests/test_tracing_phase.py`: 25 offline tests (562 lines)

## Decisions Made
See the key-decisions list in the frontmatter. Everything else follows the plan as specified.

## Deviations from Plan

None. The plan was executed as written. The environment override applied: verification ran with `venv/bin/python -m pytest` instead of `venv\Scripts\python.exe`.

## Issues Encountered
None.

## TDD Gate Compliance
Each task has a RED `test(06-03)` commit followed by a GREEN `feat(06-03)` commit. No refactor commits were needed.

## Verification
- `venv/bin/python -m pytest tests/test_tracing_phase.py tests/test_tracing.py -x -q`: 38 passed (including test_langfuse_v3_pinned)
- `venv/bin/python -m pytest -q -m "not gpu"`: 497 passed, 7 skipped

## Next Phase Readiness
- Plans 06-04 through 06-08 can wrap entry points in `trace_session(phase=PHASE_TAGS[settings.rag_pipeline] or settings.pipeline_phase)`, pass `build_callback_handler()` into the LangGraph config, and call the span and generation helpers at node boundaries.
- Existing hard-coded `"phase1"` tags in the ingest and db_writer modules have not been touched. Moving them to session-based phase tags belongs to the entry-point wiring plans.

## Self-Check: PASSED
- FOUND: src/tracing.py, src/config.py, .env.example, tests/test_tracing_phase.py
- FOUND commits: cdc1360, d1aa430, 2790e68, 57b9453

---
*Phase: 06-agentic-rag-observability*
*Completed: 2026-09-24*
