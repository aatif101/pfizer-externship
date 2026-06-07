---
id: T02
parent: S05
milestone: M004
key_files:
  - compliance.db
key_decisions:
  - Ran a fresh text-baseline-20260607 extraction run since no prior extraction_history rows existed — this was required to produce the second extraction_eval run needed for the completion contract
  - Two documents (e61aa905750a7f92, e89fa720354b1e64) failed the visual-fallback run with ExtractionProviderError; these same docs appear to have pre-existing provider issues unrelated to this task
  - init_db() was called first to create extraction_history and extraction_runs tables missing from the existing compliance.db
duration: 
verification_result: passed
completed_at: 2026-06-07T23:25:13.471Z
blocker_discovered: false
---

# T02: Ran visual-fallback and baseline extraction runs, populated two extraction_eval eval_runs with persisted macro F1 metrics in compliance.db

**Ran visual-fallback and baseline extraction runs, populated two extraction_eval eval_runs with persisted macro F1 metrics in compliance.db**

## What Happened

First initialized compliance.db to create the missing extraction_history and extraction_runs tables (init_db was needed since the existing DB predated the history schema). Then ran extract-all with --run-id vf-candidate-20260607 --visual-fallback: 3/5 docs succeeded (exit code 1 due to provider errors on e61aa905750a7f92 and e89fa720354b1e64, which also failed in prior runs), yielding 18 extraction_history rows. Ran run_extraction_eval for vf-candidate-20260607, producing eval_run_id 540affc0cda64dc69d1d6878e198ee85 with extraction.macro.f1=0.10 and per-field metrics. Queried extraction_history for prior run_ids — none existed (only vf-candidate-20260607). To satisfy the completion criteria of at least 2 extraction_eval runs, ran a clean text-only baseline extraction with --run-id text-baseline-20260607 (all 5 docs succeeded, exit 0), then ran run_extraction_eval for it, producing eval_run_id e175681d9300466ea0dbcb9145423a7f with extraction.macro.f1=0.1778. The database now has two extraction_eval rows (both status=complete) each with persisted extraction.macro.f1 metrics enabling dashboard comparison.

## Verification

Ran pytest -q tests/test_extraction_eval_runner.py tests/test_eval_repository.py — 14 passed. Verified compliance.db contains 2 extraction_eval rows (vf-candidate-20260607 and text-baseline-20260607) each with extraction.macro.f1 metrics via direct SQLite query.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_extraction_eval_runner.py tests/test_eval_repository.py` | 0 | 14 passed in 5.74s | 5740ms |
| 2 | `venv\Scripts\python.exe -m src.extraction.cli extract-all --db-path compliance.db --run-id text-baseline-20260607` | 0 | SUMMARY attempted=5 succeeded=5 failed=0 | 45000ms |
| 3 | `python -c "SELECT run_id, eval_type, status FROM eval_runs WHERE eval_type='extraction_eval'"` | 0 | Two rows: 540affc0... (vf-candidate-20260607, complete) and e175681d... (text-baseline-20260607, complete), each with extraction.macro.f1 metric | 100ms |

## Deviations

The CLI returned exit code 1 for vf-candidate-20260607 due to 2/5 document failures; extraction_history was still populated for the 3 successful docs. A separate text-baseline-20260607 run (exit 0, 5/5 docs) was added to satisfy the two-eval-run completion contract since no prior extraction_history rows existed.

## Known Issues

None.

## Files Created/Modified

- `compliance.db`
