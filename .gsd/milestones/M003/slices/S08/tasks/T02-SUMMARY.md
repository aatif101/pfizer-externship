---
id: T02
parent: S08
milestone: M003
key_files:
  - .gsd/milestones/M003/slices/S08/s08-uat-populated.db
  - .gsd/milestones/M003/slices/S08/s08-uat-populated-apptest-debug.json
  - .gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md
key_decisions:
  - Used Streamlit AppTest plus a sanitized debug JSON bundle for Eval-tab evidence because direct browser automation packages/tools were unavailable in the harness.
  - Scoped Streamlit DB_PATH through a Node child-process environment wrapper to avoid Windows shell quoting/env assignment issues.
duration: 
verification_result: passed
completed_at: 2026-05-27T21:37:28.857Z
blocker_discovered: false
---

# T02: Captured sanitized populated Eval-tab UAT evidence showing two synthetic persisted runs, retrieval/RAG metrics, and comparison deltas rendered from SQLite.

**Captured sanitized populated Eval-tab UAT evidence showing two synthetic persisted runs, retrieval/RAG metrics, and comparison deltas rendered from SQLite.**

## What Happened

Seeded `.gsd/milestones/M003/slices/S08/s08-uat-populated.db` with the T01 helper, adapting the invocation to the helper's implemented positional CLI. Started the real Streamlit app on port 8608 with `DB_PATH` scoped to the seeded database through a Node child-process environment wrapper after shell-level env assignment proved unreliable in this harness. Exercised the Eval surface with Streamlit's first-party `streamlit.testing.v1.AppTest` render harness against `src/app.py`, selected `s08-uat-eval-run-b` as primary and `s08-uat-eval-run-a` as comparison, and wrote a sanitized debug bundle containing only tab labels, widget state, run-table rows, metric rows, and comparison rows. Also checked the live `http://localhost:8608` endpoint returned the Streamlit shell. Wrote `.gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md` documenting the command used, DB path, synthetic run IDs, metric families observed, assertions, evidence artifact paths, and redaction boundaries.

## Verification

Verified the seed helper created two complete synthetic runs; verified the real app render tree showed Evaluation, Run history, Metrics, `rag.faithfulness.avg`, `retrieval.recall@5`, both synthetic run IDs, and nonzero comparison deltas without exceptions or traceback; verified the live Streamlit endpoint returned HTTP 200; verified final DB/debug/markdown artifacts contain required evidence and no obvious secret values. The Streamlit server was stopped after capture.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe scripts/seed_s08_uat_eval_db.py .gsd/milestones/M003/slices/S08/s08-uat-populated.db` | 0 | ✅ pass | 1071ms |
| 2 | `bg_shell start/wait_for_ready Streamlit src/app.py on port 8608 with DB_PATH=.gsd/milestones/M003/slices/S08/s08-uat-populated.db` | 0 | ✅ pass | 2000ms |
| 3 | `venv\Scripts\python.exe -c <streamlit AppTest populated Eval comparison assertions>` | 0 | ✅ pass | 5035ms |
| 4 | `GET http://localhost:8608` | 0 | ✅ pass | 40ms |
| 5 | `venv\Scripts\python.exe -c <verify-s08-populated-uat-artifacts>` | 0 | ✅ pass | 690ms |

## Deviations

The task plan's example seed command used `--db-path`, but the implemented T01 helper accepts the DB path as a positional argument, so verification used the actual CLI contract. Direct browser automation packages/tools were unavailable in this harness, so runtime UI evidence used Streamlit's first-party `AppTest` render harness plus a live HTTP 200 check and sanitized debug JSON bundle rather than a screenshot.

## Known Issues

None.

## Files Created/Modified

- `.gsd/milestones/M003/slices/S08/s08-uat-populated.db`
- `.gsd/milestones/M003/slices/S08/s08-uat-populated-apptest-debug.json`
- `.gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md`
