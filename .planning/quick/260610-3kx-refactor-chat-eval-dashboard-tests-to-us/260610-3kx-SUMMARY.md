---
phase: quick-260610-3kx
plan: 01
subsystem: testing
tags: [pytest, tmp_path, sqlite, dashboard, streamlit]
requires: []
provides:
  - "Chat/eval dashboard tests isolated from repo root filesystem via tmp_path"
affects: []
tech-stack:
  added: []
  patterns:
    - "tmp_path-derived db paths for all dashboard render-function tests (pattern from f2bf580)"
key-files:
  created: []
  modified:
    - tests/test_chat_dashboard.py
    - tests/test_dashboard_chat_tab.py
    - tests/test_dashboard_eval_tab.py
decisions:
  - "Used local db_path variable (str(tmp_path / 'chat.db')) instead of the tmp_db_path fixture because the path string is embedded in assertions"
metrics:
  duration: ~3 minutes
  completed: 2026-06-10
  tasks: 2
  files: 3
---

# Quick Task 260610-3kx: Refactor Chat/Eval Dashboard Tests to Use tmp_path Summary

Replaced bare relative SQLite paths ("chat.db", "empty-eval.db") with tmp_path-derived paths in three dashboard test files so sqlite3 can never create stray .db files in the repo root if mocking regresses.

## What Was Done

### Task 1: tmp_path-derived db paths in three test files (commit 57ce32f)

**tests/test_chat_dashboard.py** — added `from pathlib import Path`; all four tests now take `tmp_path: Path`, define `db_path = str(tmp_path / "chat.db")`, and pass it to `render_chat_tab`:
- `test_answered_question_persists_turns_and_renders_service_owned_citation` — call-tuple assertion updated to `assert calls == [(db_path, ...)]`
- `test_unrelated_question_abstains_with_no_citations`
- `test_provider_setup_error_is_safe_and_does_not_leak_raw_details`
- `test_provider_error_result_is_bounded_and_rerun_without_prompt_does_not_call_answer_again` — both renders share the same `db_path` so session state persists across reruns

**tests/test_dashboard_chat_tab.py** — added `Path` import; `test_chat_tab_renders_consistent_header_and_tips` uses tmp_path-derived `db_path`.

**tests/test_dashboard_eval_tab.py** — `test_render_eval_tab_empty_state_does_not_crash` uses `db_path = str(tmp_path / "empty-eval.db")`; the caption assertion updated to the f-string `f"Looking for persisted runs in \`{db_path}\`."`. Other tests in the file already used `tmp_db_path` and were untouched.

### Task 2: Repo root clean check + commit

- `glob.glob('*.db')` in repo root returned empty after the test run — verification command passed ("repo root clean")
- `git status --porcelain` clean after commit; no file deletions in the commit
- Single commit touching only the three test files

## Verification Results

| Check | Result |
|-------|--------|
| `python -m pytest tests/test_chat_dashboard.py tests/test_dashboard_chat_tab.py tests/test_dashboard_eval_tab.py -q` | 14 passed |
| Grep for `render_chat_tab("` / `render_eval_tab("` with quoted literal path | No matches |
| `*.db` files in repo root | None |
| `git diff` scope | Tests only, no src/ changes |

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — test-only refactor; T-quick-01 mitigation (tmp_path isolation of repo root) implemented as planned.

## Commits

| Hash | Message |
|------|---------|
| 57ce32f | test(quick-260610-3kx): use tmp_path for chat/eval dashboard test db paths |

## Self-Check: PASSED

- tests/test_chat_dashboard.py — FOUND, contains `str(tmp_path / "chat.db")`
- tests/test_dashboard_chat_tab.py — FOUND, contains `str(tmp_path / "chat.db")`
- tests/test_dashboard_eval_tab.py — FOUND, contains `str(tmp_path / "empty-eval.db")`
- Commit 57ce32f — FOUND in git log
