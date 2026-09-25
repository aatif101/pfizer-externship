---
phase: 06-agentic-rag-observability
plan: 02
subsystem: database
tags: [hitl, sqlite, audit, review-queue, langfuse, pydantic, dateutil]

requires:
  - phase: 02-extraction
    provides: extractions / compliance_records latest tables, _upsert_* helpers, compute_record_risk
  - phase: 05
    provides: evidence_type tiers (text/visual), run-history tables
provides:
  - extraction_reviews append-only audit table + idx_extraction_reviews_doc_field
  - SourceEvidence.evidence_type "human" tier
  - src/extraction/review.py (ReviewAction, ReviewInputError, ReviewQueueItem, ReviewOutcome, list_review_queue, apply_field_review)
affects: [06-06 Review tab, phase 7 extraction benchmark, dashboard compliance table]

actuals:
  tokens: 13000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "HITL writes touch only the latest tables plus an append-only audit row, never run history"
    - "Review read-modify-write runs in one BEGIN IMMEDIATE transaction on one connection"
    - "Confirmed-absent is encoded by the abstention_reason prefix 'Reviewer confirmed:' (queue exclusion without an audit subquery)"

key-files:
  created:
    - src/extraction/review.py
    - tests/test_review_repository.py
  modified:
    - src/db/schema.py
    - src/extraction/models.py
    - tests/test_db.py

key-decisions:
  - "apply_field_review reads the record inside its own BEGIN IMMEDIATE transaction (not via get_extraction_record beforehand), so concurrent reviews on the same document serialize and never recompute risk from a stale sibling field"
  - "Reviewer dates: ISO first, then dateutil month-first; partial dates (e.g. 2024-05) are rejected as invalid_date instead of letting dateutil invent missing components"
  - "Added reason code source_page_out_of_range: a correction must cite a page that exists (source_page < documents.page_count)"
  - "compliance_records.review_state is set to reviewed/pending/needs_review so it agrees with needs_review when confirmed-absent fields exist"

patterns-established:
  - "Review trace: @observe(name='hitl.review', capture_input=False, capture_output=False) + _REVIEW_TRACE_ALLOWED_KEYS; error_class carries reason_code or exception class name only"

requirements-completed: [HITL-01]

coverage:
  - id: D1
    description: "extraction_reviews audit table is created idempotently with an action CHECK constraint and a doc/field index"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_db.py#test_init_db_twice_creates_one_extraction_reviews_table_and_index"
        status: pass
      - kind: unit
        ref: "tests/test_db.py#test_extraction_reviews_rejects_unknown_action"
        status: pass
    human_judgment: false
  - id: D2
    description: "The review queue lists needs_review, abstained, and low-confidence unreviewed fields (confirmed-absent excluded), lowest confidence first"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_review_repository.py#test_queue_selection"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_queue_orders_ties_by_filename_then_field"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_queue_item_shape"
        status: pass
    human_judgment: false
  - id: D3
    description: "Corrections update the Compliance DB (extractions + compliance_records + recomputed risk) atomically with an audit row, and never write run history"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_review_repository.py#test_correct_updates_compliance_db"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_history_untouched"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_mid_transaction_failure_rolls_back"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_reapply_same_review_is_state_idempotent"
        status: pass
    human_judgment: false
  - id: D4
    description: "Approve / confirm-absent semantics and input validation reject bad input before any write"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_review_repository.py#test_approve"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_confirm_absent"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_input_validation"
        status: pass
      - kind: unit
        ref: "tests/test_review_repository.py#test_invalid_date_rolls_back"
        status: pass
    human_judgment: false
  - id: D5
    description: "hitl.review trace metadata is allowlisted; values, notes, and reviewer text never reach Langfuse"
    requirement: HITL-01
    verification:
      - kind: unit
        ref: "tests/test_review_repository.py#test_review_trace_metadata_allowlist"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-09-25
status: complete
---

# Phase 6 Plan 02: HITL Review Repository Summary

**Append-only `extraction_reviews` audit table, a `"human"` evidence tier, and `src/extraction/review.py`. The module lists low-confidence/abstained fields and applies approve/correct/confirm-absent. Each action runs in one transaction that updates the latest extraction and compliance rows, recomputes risk, and writes an audit row. Run history is never touched.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-25T01:40:53Z
- **Completed:** 2026-09-25T01:48:14Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `extraction_reviews` table (review_id … reviewed_at, action CHECK) and `idx_extraction_reviews_doc_field`. Both are idempotent through `CREATE ... IF NOT EXISTS`.
- `SourceEvidence.evidence_type` now accepts `"human"`. Grep of `evidence_type` consumers: `src/extraction/pipeline.py` only produces text/visual (lines 583-614). `src/extraction/repository.py` passes the value through as TEXT with a NULL→"text" read default. No db CHECK exists, and no dashboard/eval code branches on it (the `"visual"` matches in `src/retrieval/` are the unrelated retrieval `score_components.source`). No consumer fails on `"human"`.
- `list_review_queue(db_path, *, threshold)` runs one parameterized join, ordered by confidence, then filename, then field_name.
- `apply_field_review(...)`:
  - Validates input before any write, using typed `ReviewInputError.reason_code`.
  - Parses dates strictly.
  - Runs one IMMEDIATE transaction covering the audit insert, `_upsert_extraction_field`, `compute_record_risk`, `_upsert_compliance_record`, and the document needs_review/review_state update. Any failure rolls back all of them.
  - Has a `hitl.review` span with allowlisted metadata.

## Task Commits

1. **Task 1 RED:** `389f80b` (test: audit table, human tier, review queue)
2. **Task 1 GREEN:** `921d856` (feat: schema, models, list_review_queue)
3. **Task 2 RED:** `c025200` (test: apply_field_review)
4. **Task 2 GREEN:** `8f25666` (feat: apply_field_review)

## Files Created/Modified

- `src/db/schema.py`: `extraction_reviews` table in SCHEMA_SQL; index in POST_MIGRATION_INDEX_SQL
- `src/extraction/models.py`: `"human"` evidence tier (validator + description)
- `src/extraction/review.py`: review repository (queue, actions, date parsing, trace seams)
- `tests/test_review_repository.py`: 29 tmp-sqlite tests
- `tests/test_db.py`: idempotent init + CHECK constraint tests

## Decisions Made

- The queue excludes confirmed-absent fields by the `Reviewer confirmed:` abstention prefix, as the plan specified. A re-extraction overwrites the reason, so the field re-enters the queue.
- The latest `extractions.trace_id` keeps the extraction trace link (`record.trace_id`). The review's own `trace_id` goes on the audit row, so upserting never nulls the extraction trace.
- `audit.new_value` stores the normalized dashboard value, e.g. `01-JAN-2024` → `2024-01-01`. The raw reviewer text stays in `extractions.field_value` / `verbatim_span`.
- For confirm_absent, `extractions.needs_review` is cleared to 0 for that field. This keeps the row consistent with "resolved".
- `reviewer` is stripped. If it is blank it falls back to `demo-reviewer`, because the column is NOT NULL. RBAC is out of scope (T-06-12 accepted).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale-read race in the read-modify-write**
- **Found during:** Task 2
- **Issue:** The plan loaded the record with `get_extraction_record` before opening the write connection. Two concurrent reviews of different fields in the same document could then recompute `compliance_records` from a stale sibling value. The result: `compliance_records` disagrees with `extractions`.
- **Fix:** The review opens `BEGIN IMMEDIATE` and reads the record on the same connection via `_get_extraction_record_with_queries`, using the same SQL as `get_extraction_record`. Side effect: `record_not_found` is raised inside the (empty) transaction instead of before a connection opens. No write happens either way.
- **Files modified:** src/extraction/review.py
- **Verification:** All no-write tests pass. An ad-hoc two-thread run (20 corrections on one field) produced 20 audit rows, and extractions/compliance_records agreed.
- **Committed in:** 8f25666

**2. [Rule 2 - Missing critical] Partial reviewer dates rejected**
- **Found during:** Task 2
- **Issue:** `dateutil.parse("2024-05")` silently invents a day. The eval module guards against the same problem.
- **Fix:** Parse against two different defaults. Any difference means a component was missing, which gives `invalid_date`.
- **Files modified:** src/extraction/review.py
- **Verification:** `test_invalid_date_rolls_back[2024-05]`
- **Committed in:** 8f25666

**3. [Rule 2 - Missing critical] Cited page must exist**
- **Found during:** Task 2
- **Issue:** A correction could cite a page beyond the document. That breaks the "every answer is grounded in a cited source page" core value.
- **Fix:** New reason code `source_page_out_of_range`, raised when `source_page >= documents.page_count`, before any write. 06-06 renders reason codes generically, so no UI change is needed.
- **Files modified:** src/extraction/review.py
- **Verification:** `test_input_validation[kwargs6-source_page_out_of_range]`
- **Committed in:** 8f25666

**4. [Rule 1 - Bug] Document review_state consistent with needs_review**
- **Found during:** Task 2
- **Issue:** Suppose a document has a confirmed-absent field and no other unresolved fields. The aggregate `dashboard_review_state` would still say `needs_review` while `needs_review=0`.
- **Fix:** The review sets `review_state` to `needs_review` if anything is unresolved. Otherwise it sets `reviewed` when all fields are reviewed or confirmed-absent, and `pending` in every other case.
- **Files modified:** src/extraction/review.py
- **Verification:** `test_confirm_absent`, `test_all_fields_resolved_marks_document_reviewed`
- **Committed in:** 8f25666

---

**Total deviations:** 4 auto-fixed (2 bug, 2 missing critical)
**Impact on plan:** All are correctness/integrity hardening inside the planned module. There are no contract changes, apart from one extra reason code.

## TDD Gate Compliance

- Task 1: RED `389f80b` (schema/evidence tests failed on assertions; queue tests failed on the missing module) → GREEN `921d856`.
- Task 2: RED `c025200` (all apply tests failed: `apply_field_review` / seams not present) → GREEN `8f25666`.
- The module-missing failures are import errors, not assertion failures. The schema and evidence tests in the same RED commit failed on real assertions. No REFACTOR commit was needed.

## Issues Encountered

None.

## User Setup Required

None. No external service configuration required.

## Next Phase Readiness

- 06-06 (Review tab) can use `list_review_queue(db_path, threshold=settings.extraction_low_confidence_threshold)` and `apply_field_review(...)` directly. `ReviewInputError.reason_code` is the only error text it should render.
- Full suite: 473 passed, 7 skipped (`-m "not gpu"`).

---
*Phase: 06-agentic-rag-observability*
*Completed: 2026-09-25*

## Self-Check: PASSED

- FOUND: src/extraction/review.py, tests/test_review_repository.py, src/db/schema.py, src/extraction/models.py, tests/test_db.py
- FOUND commits: 389f80b, 921d856, c025200, 8f25666
