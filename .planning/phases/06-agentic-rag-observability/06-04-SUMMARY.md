---
phase: 06-agentic-rag-observability
plan: 04
subsystem: rag
tags: [critic, anthropic, claude-sonnet, gemini, langgraph, langfuse, generation-spans, rag-03, obs-01]

requires:
  - phase: 06-01
    provides: agentic graph, critic contracts (CriticProvider/CriticVerdict/typed errors), AnswerProviderRequest.revision_hint
  - phase: 06-03
    provides: build_callback_handler, safe_update_current_generation, safe_update_current_trace phase tag, critic settings
provides:
  - "src/rag/critic.py: CRITIC_SYSTEM_PROMPT, build_critic_prompt, AnthropicCritic, GeminiCritic (opt-in), build_critic_provider (fail closed)"
  - "src/rag/gemini.py: GeminiAnswerProvider.complete_text, generation.draft / generation.aux spans, _usage_tokens, <revision_feedback> prompt block"
  - "src/rag/agentic/graph.py: critic resolution from settings, settings-driven threshold, CallbackHandler in RunnableConfig, allowlisted rag/agentic trace metadata, decomposer/rewriter seams from provider.complete_text"
affects: [06-05 decompose/rewrite, 06-08 chat default + OBS-01 manual check, phase 7 benchmark]

actuals:
  tokens: 90000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "LLM calls go through an observe(as_type='generation', capture_input=False, capture_output=False) method that reports model plus token usage only"
    - "The critic builder dispatches on CRITIC_PROVIDER with no try/except between providers, so a missing Anthropic key raises instead of falling back"
    - "answer_question_agentic is a thin traced wrapper around _run_agentic, and the allowlisted trace update runs on every return path"

key-files:
  created:
    - tests/rag/test_critic_provider.py
    - tests/rag/agentic/test_graph_wiring.py
    - .planning/phases/06-agentic-rag-observability/06-USER-SETUP.md
  modified:
    - src/rag/critic.py
    - src/rag/gemini.py
    - src/rag/agentic/graph.py
    - tests/test_answer_provider_gemini.py
    - tests/rag/agentic/test_graph.py

key-decisions:
  - "critic=None now resolves from settings. Without an Anthropic key the result is ABSTAINED/critic_error with error_class CriticConfigurationError (it used to be CriticNotConfigured). The draft node still skips the provider call"
  - "build_critic_provider is imported at module level in graph.py (src.rag.critic is SDK-free), which keeps it monkeypatchable"
  - "An explicit critic_min_faithfulness argument overrides the CRITIC_MIN_FAITHFULNESS setting. A settings failure falls back to the 0.8 default"
  - "Injected decomposer/rewriter callables are never overridden by the provider.complete_text seam"

requirements-completed: [RAG-03, OBS-01]  # contributes; checkboxes are ticked by 06-08 (last declaring plan)

coverage:
  - id: D1
    description: "Claude Sonnet critic: messages.create with no sampling kwargs, bounded injection-hardened prompt, retry, sanitized errors"
    requirement: RAG-03
    verification:
      - kind: unit
        ref: "tests/rag/test_critic_provider.py#test_anthropic_critique_parses_verdict_and_sends_no_sampling_kwargs"
        status: pass
      - kind: unit
        ref: "tests/rag/test_critic_provider.py#test_anthropic_nonretryable_error_is_sanitized_and_not_retried"
        status: pass
    human_judgment: false
  - id: D2
    description: "Fail-closed build_critic_provider with no silent Gemini fallback (D-02); Gemini critic opt-in only"
    requirement: RAG-03
    verification:
      - kind: unit
        ref: "tests/rag/test_critic_provider.py#test_build_critic_provider_missing_anthropic_key_never_falls_back"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_graph_wiring.py#test_critic_resolved_from_settings_fail_closed"
        status: pass
    human_judgment: false
  - id: D3
    description: "LangGraph run carries the Langfuse CallbackHandler when enabled, plus allowlisted rag/agentic trace metadata"
    requirement: OBS-01
    verification:
      - kind: integration
        ref: "tests/rag/agentic/test_graph_wiring.py#test_callback_handler_passed_when_enabled"
        status: pass
      - kind: integration
        ref: "tests/rag/agentic/test_graph_wiring.py#test_agentic_trace_metadata_allowlist"
        status: pass
    human_judgment: false
  - id: D4
    description: "Gemini draft/aux and critic generation spans report model + token usage; complete_text seam; revision_feedback on regeneration only"
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "tests/test_answer_provider_gemini.py#test_answer_reports_generation_usage"
        status: pass
      - kind: unit
        ref: "tests/test_answer_provider_gemini.py#test_revision_hint_in_prompt_only_when_present"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live Langfuse trace shows node spans and generations with usage and no prompt text"
    requirement: OBS-01
    human_judgment: true
    rationale: "Needs real Anthropic/Gemini/Langfuse keys. This is the manual OBS-01 check in 06-08"

duration: 7 min
completed: 2026-09-24
---

# Phase 6 Plan 04: Live Critic, Graph Tracing Wiring, and Generation Spans Summary

**The agentic pipeline now uses a Claude Sonnet faithfulness critic by default. If no Anthropic key is set it abstains and never falls back to Gemini. The LangGraph run passes the Langfuse CallbackHandler, and every Gemini and Claude call is traced as a generation span that records only the model and token usage.**

## Performance

- **Duration:** 7 min
- **Tasks:** 2 (both TDD, RED then GREEN)
- **Files modified:** 8 (3 src, 4 tests, 1 user-setup doc)

## Accomplishments
- `AnthropicCritic` calls `client.messages.create(model="claude-sonnet-4-6", max_tokens=512, system=CRITIC_SYSTEM_PROMPT, messages=[...])` with no temperature/top_p/top_k. It imports the SDK lazily, retries with tenacity (2 attempts, no wait), and exposes only the exception class name in errors. The system prompt tells the model to treat question and evidence text as data and to ignore any instructions inside them.
- `GeminiCritic` runs only when `CRITIC_PROVIDER=gemini` is set explicitly. `build_critic_provider` raises `CriticConfigurationError` when the Anthropic key is missing, even if `GEMINI_API_KEY` is set.
- `answer_question_agentic` resolves the critic from settings, reads the threshold from settings, and gets decomposer/rewriter from `provider.complete_text` (roles `decompose`/`rewrite`). It passes `callbacks=[handler]` only when `build_callback_handler()` returns a handler, and sends allowlisted `["rag","agentic"]` trace metadata with no question, draft, or evidence text.
- Gemini changes: a `generation.draft` span on `answer()`, a `generation.aux` span on `complete_text()`, a usage-only `safe_update_current_generation` call, and a bounded `<revision_feedback>` block that appears only on regeneration.

## Task Commits

1. **Task 1: Critic adapters and fail-closed builder.** RED `51bad48`, GREEN `35c05a6`
2. **Task 2: Graph wiring, CallbackHandler, trace metadata, Gemini spans and seams.** RED `757cf89`, GREEN `211eda0`

## Files Created/Modified
- `src/rag/critic.py`: added the critic prompt, the Anthropic/Gemini adapters, and the builder
- `src/rag/gemini.py`: added `complete_text`, the traced generation methods, `_usage_tokens`, and the revision block
- `src/rag/agentic/graph.py`: added critic/threshold/seam resolution, CallbackHandler config, trace seams, and the allowlist
- `tests/rag/test_critic_provider.py` (new, 19 tests), `tests/rag/agentic/test_graph_wiring.py` (new, 12 tests), `tests/test_answer_provider_gemini.py` (+6 tests)
- `tests/rag/agentic/test_graph.py`: updated the critic-missing case for 06-04 semantics

## Decisions Made
See `key-decisions` in the frontmatter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 06-01 critic-missing test expected the old error class**
- **Found during:** Task 2
- **Issue:** `test_critic_failure_fails_closed[critic-missing]` expected `error_class == "CriticNotConfigured"`. With lazy critic resolution, `critic=None` now surfaces `CriticConfigurationError`. The test also depended on the environment: an `ANTHROPIC_API_KEY` on the developer machine would have built a live critic.
- **Fix:** The test now pins `CRITIC_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=""`, clears the settings cache, and expects `CriticConfigurationError`. It still checks that the provider is never called.
- **Files modified:** tests/rag/agentic/test_graph.py
- **Commit:** 211eda0

**2. [Rule 1 - Acceptance] Critic docstring mentioned "temperature"**
- **Found during:** Task 1 acceptance gate
- **Issue:** `grep temperature src/rag/critic.py` also matched the AnthropicCritic docstring.
- **Fix:** Reworded the docstring so only the GeminiCritic config line matches.
- **Commit:** 35c05a6

**Total deviations:** 2 auto-fixed (both Rule 1). **Impact:** none on scope. The test update follows from the planned behavior change.

## Issues Encountered
None.

## User Setup Required
Needs an external service: see `06-USER-SETUP.md` (ANTHROPIC_API_KEY for the critic, Langfuse keys for live trace inspection).

## Verification
- `venv/bin/python -m pytest tests/rag/agentic tests/rag/test_critic_provider.py tests/test_answer_provider_gemini.py tests/test_answer_service.py -q`: 107 passed
- `venv/bin/python -m pytest -q -m "not gpu"`: 534 passed, 7 skipped (baseline 497 + 37 new)
- Acceptance greps: `as_type="generation"` matches 4 lines. `build_callback_handler`/`build_critic_provider` are present in graph.py. There is one `def complete_text`. No content keys appear in `_AGENTIC_TRACE_ALLOWED_KEYS`. There is no top-level anthropic import, and `temperature` appears only in GeminiCritic.

## TDD Gate Compliance
RED `test(06-04)` commits (51bad48, 757cf89) come before the GREEN `feat(06-04)` commits (35c05a6, 211eda0). Both RED runs failed first: an ImportError for Task 1, and 14 failures for Task 2.

## Next Phase Readiness
06-05 can use `deps.decomposer` / `deps.rewriter`, which are already wired to `GeminiAnswerProvider.complete_text`. 06-08 owns the live OBS-01 trace check and ticking RAG-03/OBS-01.

## Self-Check: PASSED
