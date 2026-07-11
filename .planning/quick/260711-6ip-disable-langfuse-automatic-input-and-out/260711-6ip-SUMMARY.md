---
phase: quick-260711-6ip
plan: 01
status: complete
subsystem: observability
tags: [langfuse, tracing, privacy]
requires: []
provides:
  - Fail-closed project observe wrapper with automatic input and output capture disabled
  - Regression coverage for decorator forms, override attempts, offline fallback, and source consumers
affects: [src/tracing.py, tests/test_tracing.py]
tech-stack:
  added: []
  patterns:
    - "Sensitive boundaries import src.tracing.observe; the wrapper owns Langfuse capture policy"
key-files:
  created: []
  modified:
    - src/tracing.py
    - tests/test_tracing.py
metrics:
  completed: "2026-07-11"
  tasks: 2
  tests: "81 passed"
---

# Quick Task 260711-6ip: Disable Langfuse Automatic Input and Output Capture

Langfuse-decorated pipeline boundaries now fail closed: the project wrapper always forwards `capture_input=False` and `capture_output=False`, including when a caller attempts to enable either flag.

## Changed Files

- `src/tracing.py`
  - Imports the Langfuse SDK decorator under the private `_langfuse_observe` name.
  - Exposes a project `observe` wrapper that overwrites both automatic capture flags with `False` for direct and configured decorator forms.
  - Preserves an explicit `_noop_observe` implementation for transparent offline behavior when Langfuse is unavailable.
- `tests/test_tracing.py`
  - Verifies direct `@observe`, configured `@observe(name=...)`, and explicit capture-override attempts all forward both flags as `False`.
  - Verifies the unavailable-SDK no-op remains transparent.
  - Enumerates source modules through their AST and rejects any `@observe` consumer that does not import the project wrapper or imports the SDK decorator directly.

## Verification Evidence

- `venv\Scripts\python.exe -m pytest tests\test_tracing.py -q`
  - Result: `17 passed in 6.26s`
- `venv\Scripts\python.exe -m pytest tests\test_tracing.py tests\test_ingest.py tests\test_extraction_pipeline.py tests\test_retriever.py tests\test_answer_service.py tests\test_retrieval_eval_runner.py -q`
  - Result: `81 passed in 51.60s`
  - Warnings: 15 pre-existing dependency deprecations from Docling and Torch; no test failures.
- `git diff --check`
  - Result: exit code 0.

## Deviations from Plan

None. The implementation and verification remained limited to `src/tracing.py` and `tests/test_tracing.py`. No commit was created, as explicitly requested. `ROADMAP.md` and `STATE.md` were not modified.

## Self-Check: PASSED

- Fail-closed flags are enforced centrally for every project decorator invocation.
- Direct, configured, override-attempt, and offline fallback forms are verified.
- All current production `@observe` consumers are guarded by a source-level regression.
- Both exact Windows verification commands and `git diff --check` passed.
