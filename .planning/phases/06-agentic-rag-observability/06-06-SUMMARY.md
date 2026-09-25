---
phase: 06-agentic-rag-observability
plan: 06
subsystem: dashboard
tags: [hitl, streamlit, review-queue, langfuse, tracing, obs-01]

requires:
  - phase: 06-02
    provides: list_review_queue, apply_field_review, ReviewInputError reason codes, ReviewQueueItem/ReviewOutcome
  - phase: 06-03
    provides: trace_session(phase, tags), flush_traces, Settings.pipeline_phase
provides:
  - src/dashboard/review.py render_review_tab (queue_fn / apply_fn / image_fn seams)
  - 4th Streamlit tab "Review" (Compliance, Chat, Review, Eval)
  - src.dashboard export render_review_tab
affects: [06-08 phase verification, phase 7 demo walkthrough]

actuals:
  tokens: 60000
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Dashboard write paths go through repository seams only and render reason_code / exception class name, never str(exc)"
    - "Review submit: with trace_session(phase=settings.pipeline_phase, tags=('hitl','review')) around the write, flush_traces() in finally, st.rerun() only on success"
    - "Selection persisted in st.session_state['pfizer_review_selected'] and passed back as selectbox index (no widget key, so a stale selection after rerun falls back to index 0)"

key-files:
  created:
    - src/dashboard/review.py
    - tests/test_dashboard_review_tab.py
  modified:
    - src/app.py
    - src/dashboard/__init__.py
    - tests/test_app.py

key-decisions:
  - "Review selectbox has no widget key; the selection is written to session_state and fed back via index, so a reviewed item leaving the queue never raises a stale-key error"
  - "Abstained items do not offer 'approve' (only correct / confirm_absent), matching the repository's approve_requires_value rule"
  - "corrected_value and source_page are sent only for 'correct'; the 1-based page is converted to 0-based and range-checked downstream (source_page_out_of_range)"

patterns-established:
  - "Streamlit form fakes: FakeContext for st.form plus scripted radio/text_input/number_input/text_area/form_submit_button"

requirements-completed: [HITL-01]

coverage:
  - id: D1
    description: "Review tab lists the queue with metrics (queued/abstained/low-confidence) and a bounded table, or a safe empty state"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_queue_metrics_and_table"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_empty_queue_shows_empty_state"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_missing_table_is_safe"
        status: pass
    human_judgment: false
  - id: D2
    description: "Selector keyed doc_id::field_name with evidence pane and source page image (safe fallback on image errors)"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_selector_options_unique"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_detail_shows_source_image"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_detail_image_error_is_safe"
        status: pass
    human_judgment: false
  - id: D3
    description: "Form submit writes approve/correct/confirm-absent through apply_field_review with 0-indexed page; errors bounded to reason code / class name"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_submit_correct_calls_apply_fn"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_submit_approve_omits_value"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_submit_invalid_shows_reason_code_only"
        status: pass
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_submit_unexpected_error_bounded"
        status: pass
    human_judgment: false
  - id: D4
    description: "Review submit runs inside a phase-tagged trace_session and flushes traces"
    requirement: OBS-01
    verification:
      - kind: unit
        ref: "tests/test_dashboard_review_tab.py#test_submit_opens_trace_session"
        status: pass
    human_judgment: false
  - id: D5
    description: "The Review tab is reachable in the app (tabs Compliance, Chat, Review, Eval)"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_app.py#test_app_declares_review_tab"
        status: pass
      - kind: integration
        ref: "tests/test_app.py#test_streamlit_starts"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-09-24
---

# Phase 6 Plan 06: HITL Review Tab Summary

**A Streamlit "Review" tab that lists low-confidence and abstained extractions and shows each field's evidence and source page. Reviewers approve, correct, or confirm-absent through a form that calls `apply_field_review` inside a phase-tagged `trace_session`. Errors are limited to reason codes.**

## Performance

- **Duration:** about 6 min
- **Tasks:** 2
- **Files:** 2 created, 3 modified

## Accomplishments
- `render_review_tab(db_path=None, *, queue_fn, apply_fn, image_fn)` shows:
  - a header and three metrics: Queued, Abstained, Low confidence / needs review
  - a bounded table of queued fields (value and span cut at 120 characters, page shown 1-based, "-" when missing)
  - a `doc_id::field_name` selector, with the choice saved in session_state
  - an evidence pane, capped at 1000 characters, showing the value, confidence, state, evidence type, page, verbatim span, and abstention reason
  - the source page image. If the image can't be loaded, a caption is shown instead.
- The review form is keyed `review_{doc_id}_{field_name}`. It has a decision radio, a corrected-value input (max 200 characters), a 1-based page number input, and a note (max 1000 characters). On submit it calls `apply_fn(db_path, doc_id=..., field_name=..., action=..., corrected_value=..., source_page=<0-based>, note=...)`.
- Every write runs inside `trace_session(phase=settings.pipeline_phase, tags=("hitl", "review"))`, and `flush_traces()` runs in `finally`. A successful save shows `st.success` and calls `st.rerun()`. A `ReviewInputError` shows only its `reason_code`, and any other exception shows only its class name.
- If the database or table is missing, or `sqlite3.Error`/`OSError` is raised, the tab shows "Review queue unavailable" instead of an error.
- `src/app.py` now has 4 tabs: Compliance, Chat, Review, Eval. `render_review_tab` is exported from `src.dashboard`.

## Task Commits

1. **Task 1: render_review_tab**
   - RED `7d750bb` (test), GREEN `b389c83` (feat)
2. **Task 2: App and package wiring**: `42750b0` (feat)

## Files Created/Modified
- `src/dashboard/review.py` (251 lines): the Review tab renderer and bounded display helpers
- `tests/test_dashboard_review_tab.py` (515 lines): 13 FakeStreamlit tests
- `src/app.py`: added the fourth tab and updated the docstring
- `src/dashboard/__init__.py`: added the export
- `tests/test_app.py`: added `test_app_declares_review_tab`

## Verification
- `venv/bin/python -m pytest tests/test_app.py tests/test_dashboard_review_tab.py tests/test_compliance_dashboard.py tests/test_dashboard_chat_tab.py -x -q`: 29 passed
- `venv/bin/python -m pytest -q -m "not gpu"`: 589 passed, 7 skipped (the baseline was 575 passed, so 14 tests were added)
- A headless `streamlit.testing.v1.AppTest` render of `src/app.py` gave tabs `['Compliance', 'Chat', 'Review', 'Eval']` and raised no exceptions. With no DB, the Review tab shows "Review queue unavailable".
- Acceptance greps: `str(exc)` does not appear anywhere. `st.form(key=f"review_`, `trace_session(` and `flush_traces()` each appear exactly once.

## Decisions Made
- The selectbox has no widget key. The selection is stored in `session_state["pfizer_review_selected"]` and passed back as `index`. When a reviewed item drops out of the queue after the rerun, the selector falls back to the first item instead of hitting a stale-value error.
- For abstained items the form offers only correct and confirm_absent, because approving an empty value would fail `approve_requires_value`.
- `corrected_value` and `source_page` are sent only for "correct". A note that is empty or only spaces is sent as `None`.

## Deviations from Plan

None. The plan was executed as written, with two small additions:
- Extra tests: `test_detail_image_error_is_safe` (split out of the image test), `test_no_submit_no_write`, and `test_default_db_path_resolves_from_settings`.
- `_bounded_code` limits the rendered reason_code to 64 characters as defence in depth.

## Threat Mitigations
- T-06-27: only the reason_code or exception class name is rendered, and the tests use a leaky `__str__` to check this.
- T-06-28: the inputs have max_chars, and the page number goes from 1-based to 0-based with repository-side validation.
- T-06-29: the form key includes the doc and field, the selection is kept in session_state, and the tab reruns after a successful save.
- T-06-30: the session carries only the phase and tags. Values and notes are never passed to `trace_session`.

## Known Stubs
None.

## Next Phase Readiness
HITL-01 is complete: the 06-02 repository and this plan's UI together meet it. OBS-01 now also covers review actions, and 06-08 will finalize that requirement.

## Self-Check: PASSED
- FOUND: src/dashboard/review.py, tests/test_dashboard_review_tab.py
- FOUND commits: 7d750bb, b389c83, 42750b0
