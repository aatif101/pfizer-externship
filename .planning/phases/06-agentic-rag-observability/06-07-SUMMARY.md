---
phase: 06-agentic-rag-observability
plan: 07
subsystem: observability
tags: [langfuse, tracing, typer, cli, obs-01, d-03]

requires:
  - phase: 06-03
    provides: trace_session, current_phase, PHASE_TAGS, the auto phase tag in safe_update_current_trace, Settings.pipeline_phase
provides:
  - Phase-tagged trace_session around extract, extract-all, retrieval build/status, and ingest (phase=settings.pipeline_phase)
  - Eval CLI run inside trace_session(phase="phase1") (linear harness, D-03)
  - Ingestion and storage trace tags with no hard-coded phase (the phase comes from the active session)
  - D-03 regression guard showing the RAGAS harness default answer_fn is still the linear answer_question
affects: [06-08, phase 7 benchmark]

actuals:
  tokens: 16000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "CLI entry points wrap the command body in `with trace_session(phase=..., tags=(\"cli\", <command>))`. Exits raised in the body pass through the session unchanged."
    - "Module-level tag lists never include a phase. trace_session supplies the phase through the ContextVar."
    - "Entry-point tests replace module.trace_session with a recording context manager (monkeypatch raising=False)."

key-files:
  created:
    - tests/test_tracing_entry_points.py
  modified:
    - src/extraction/cli.py
    - src/retrieval/cli.py
    - src/pipeline/ingest.py
    - src/pipeline/db_writer.py
    - src/eval/cli.py

key-decisions:
  - "The whole command body goes inside the session, including early validation exits, so an ingest run with no PDFs still opens its session first. Eval is the exception: its db_missing precheck stays outside the session and only the run call and its result echo are wrapped, as the plan specifies."
  - "db_writer._trace_storage also drops its hard-coded phase1 tag. Otherwise storage traces in a phase2 ingest session would carry both phase2 and phase1."

requirements-completed: [OBS-01]  # partial contribution. Per orchestrator instruction the REQUIREMENTS.md tick is deferred to 06-08

coverage:
  - id: D1
    description: "The extract and extract-all CLIs open a trace_session tagged with settings.pipeline_phase and the tags cli/extract or cli/extract-all. Output and exit codes are unchanged."
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_extract_opens_session"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_extract_all_opens_session"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_extract_body_runs_under_active_phase"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_session_body_exceptions_propagate"
        status: pass
    human_judgment: false
  - id: D2
    description: "The retrieval build and status CLIs open phase-tagged sessions (retrieval-build and retrieval-status). Exit codes are unchanged."
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_retrieval_build_and_status_open_session"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_retrieval_missing_db_exit_code_unchanged"
        status: pass
    human_judgment: false
  - id: D3
    description: "The ingest CLI opens a phase-tagged session. Ingestion and storage trace tags no longer hard-code phase1."
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_ingest_opens_session_and_no_hardcoded_phase"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_storage_trace_tags_are_phase_neutral"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_ingestion_trace_carries_session_phase_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "The eval CLI runs inside a phase1 (linear) session, and the RAGAS harness default stays linear (D-03)."
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_eval_run_opens_linear_session"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_eval_run_failure_keeps_bounded_error"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_eval_missing_db_unchanged"
        status: pass
      - kind: unit
        ref: "tests/test_tracing_entry_points.py#test_ragas_harness_default_is_linear"
        status: pass
    human_judgment: false

duration: 5 min
completed: 2026-09-25
status: complete
---

# Phase 6 Plan 07: Phase-Tagged Trace Sessions at CLI Entry Points Summary

**Every offline CLI (extract, extract-all, retrieval build/status, ingest, eval run) now runs inside a Langfuse v3 `trace_session`. The extraction, retrieval, and ingest CLIs are tagged with `pipeline_phase`. Eval is pinned to `phase1` because it stays on the linear pipeline (D-03). The hard-coded `"phase1"` tags in ingestion and storage traces are gone.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-25T02:23:38Z
- **Completed:** 2026-09-25T02:28:59Z
- **Tasks:** 2
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- The extraction, retrieval-index, and ingestion commands open `trace_session(phase=get_settings().pipeline_phase, tags=("cli", <command>))` around their whole body. The echo text, exit codes, and exception mapping are the same as before; in the diff, only the added `with` lines differ once whitespace is ignored.
- The eval `run` command replaces its best-effort `_ensure_langfuse_initialized()` block with `trace_session(phase=PHASE_TAGS["linear"], tags=("cli", "eval"))`. trace_session initializes Langfuse itself and never raises.
- `_trace_ingestion` and `_trace_storage` now emit `["ingestion"]` and `["storage"]`. Inside a session the tags become `["phase2", "ingestion"]`, with exactly one phase tag.
- A D-03 guard confirms that `compute_ragas_quality(answer_fn=None)` calls the linear `answer_question` and never `answer_question_agentic`.

## Task Commits

1. **Task 1: Phase-tagged sessions for extraction, retrieval, and ingestion CLIs**
   - RED `89dbf28` (test), GREEN `6fed3ff` (feat)
2. **Task 2: Eval CLI on the linear phase tag and a D-03 guard for the RAGAS harness**
   - RED `857ff1d` (test), GREEN `8492439` (feat)

## Files Created/Modified
- `tests/test_tracing_entry_points.py`: 13 offline tests (343 lines) using a recording `trace_session` fake and typer CliRunner
- `src/extraction/cli.py`: `extract_command` and `extract_all_command` bodies wrapped in trace_session
- `src/retrieval/cli.py`: `build_command` and `status_command` bodies wrapped. Added imports for get_settings and trace_session
- `src/pipeline/ingest.py`: `ingest` body wrapped. `_trace_ingestion` tags changed to `["ingestion"]`
- `src/pipeline/db_writer.py`: `_trace_storage` tags changed to `["storage"]` (deviation 1)
- `src/eval/cli.py`: run body wrapped in a phase1 trace_session with a D-03 comment. `_ensure_langfuse_initialized` block removed

## Decisions Made
- The extraction, retrieval, and ingest commands wrap their whole body, including the early validation exits. That way a run that exits early is still attributed to a session. The session re-raises `typer.Exit`, and `test_session_body_exceptions_propagate` shows the exit code is unchanged.
- Eval keeps its `db_missing` precheck outside the session, as the plan requires. Only the run call and its result echo are inside.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed the hard-coded "phase1" from the storage trace tags in db_writer**
- **Found during:** Task 1
- **Issue:** `src/pipeline/db_writer.py::_trace_storage` still passed `tags=["phase1", "storage"]`. Inside a phase2 ingest session, the 06-03 auto-prepend would have tagged storage traces `["phase2", "phase1", "storage"]`, which puts the wrong phase on them. The orchestrator's note from 06-03 flagged this file as well.
- **Fix:** Tags changed to `["storage"]`, so the phase comes from the active session.
- **Files modified:** src/pipeline/db_writer.py
- **Verification:** `test_storage_trace_tags_are_phase_neutral` and `test_ingestion_trace_carries_session_phase_once`. The existing `tests/test_ingest.py` still passes.
- **Committed in:** 6fed3ff

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Needed to meet the must-have "ingestion trace updates no longer hard-code 'phase1'". No scope creep.

## TDD Gate Compliance
- Both tasks have a RED `test(06-07)` commit before their GREEN `feat(06-07)` commit. No refactor commits were needed.
- Task 2 RED: `test_eval_missing_db_unchanged` and `test_ragas_harness_default_is_linear` passed during the RED phase. This is expected: both guard existing behavior that must not change (the plan says not to modify ragas_quality.py). The session tests that were actually new (`test_eval_run_opens_linear_session` and `test_eval_run_failure_keeps_bounded_error`) failed on their assertions, as required.

## Verification
- `venv/bin/python -m pytest tests/test_tracing_entry_points.py -x -q`: 13 passed
- `venv/bin/python -m pytest tests/test_extraction_cli.py tests/test_retrieval_cli.py tests/test_ingest.py tests/eval/test_eval_cli.py -x -q -m "not gpu"`: green
- `venv/bin/python -m pytest -q -m "not gpu"`: 602 passed, 7 skipped
- grep acceptance: `trace_session(` appears 2/2/1 times in the extraction/retrieval/ingest CLIs and once in the eval CLI (with `PHASE_TAGS["linear"]`). There is no `"phase1"` in ingest.py or db_writer.py, `git diff src/eval/ragas_quality.py` is empty, and ragas_quality contains no `answer_question_agentic`.

## Issues Encountered
- I first tried to wrap the command bodies with a first-match text script. It matched the wrong `typer.echo(` in extraction/cli.py. I reverted that single file with `git checkout -- src/extraction/cli.py` before committing and redid the edit with a function-scoped re-indent. Nothing broken was committed.

## User Setup Required
None. With no Langfuse keys, trace_session does nothing and CLI output is unchanged.

## Next Phase Readiness
- OBS-01 now covers the CLI entry points. 06-08 is the last plan for RAG-03/OBS-01 and will tick them in REQUIREMENTS.md.
- Phase 7 can add an explicit pipeline flag to the eval CLI. It currently hard-codes `PHASE_TAGS["linear"]`.

---
*Phase: 06-agentic-rag-observability*
*Completed: 2026-09-25*

## Self-Check: PASSED

- FOUND: tests/test_tracing_entry_points.py, 06-07-SUMMARY.md
- FOUND commits: 89dbf28, 6fed3ff, 857ff1d, 8492439
