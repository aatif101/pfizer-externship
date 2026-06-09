---
id: S05
parent: M004
milestone: M004
provides:
  - run_extraction_eval function wiring extraction_metrics+repository into the eval_runs pipeline
  - Two extraction_eval eval_runs in compliance.db (vf-candidate-20260607 and text-baseline-20260607) with macro F1/precision/recall metrics
  - Browser-verified Compliance tab run selector and Eval tab metric comparison on real data
requires:
  []
affects:
  []
key_files:
  - src/eval/extraction_eval_runner.py
  - tests/test_extraction_eval_runner.py
key_decisions:
  - Mirrored extraction_usage_eval.py skeleton exactly for extraction_eval_runner.py — same frozenset/sanitize_error pattern ensures consistent bounded tracing across all eval types
  - Added text-baseline-20260607 run in T02 since no prior extraction_history rows existed — required to satisfy the two-eval-run completion contract without compromising the vf-candidate comparison
  - Per-field metrics use metric_name='extraction.f1/precision/recall' with scope_type='field'; macro metrics use 'extraction.macro.*' with no scope — consistent with eval_metrics schema convention
patterns_established:
  - extraction_eval_runner.py establishes the per-field + macro F1/precision/recall eval pattern: load gold via list_gold_extraction_labels, load preds via list_predicted_extractions_for_run, compute_extraction_field_scores, compute_macro_averages, upsert metrics, mark complete — mirrors extraction_usage_eval.py lifecycle exactly
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-06-07T23:34:45.136Z
blocker_discovered: false
---

# S05: Real five document comparison and UAT

**Created extraction_eval_runner, ran visual-fallback and text-baseline extraction on real compliance.db, compared eval metrics in dashboard, and confirmed no confidential leakage with 303 tests passing.**

## What Happened

S05 closed out M004 with four tasks completing the end-to-end evaluation hardening pipeline on real documents.

**T01** created `src/eval/extraction_eval_runner.py` mirroring the `extraction_usage_eval.py` skeleton exactly: `@observe(name='extraction_eval_run')` decorating `run_extraction_eval`, lifecycle of create_eval_run → load gold → load preds → compute_extraction_field_scores → compute_macro_averages → upsert global and scoped metrics → mark_complete, with graceful empty-state and `sqlite3.OperationalError` handling. Six offline unit tests in `tests/test_extraction_eval_runner.py` covered macro/field metrics, empty-gold, empty-pred, idempotency, run-completion marking, and per-field scoped metrics; all 6 passed on the first run.

**T02** ran live Gemini API calls against the local 5-document corpus. The `vf-candidate-20260607` visual-fallback run had 3/5 documents succeed (2 pre-existing provider failures unrelated to S05). A separate `text-baseline-20260607` text run was added (5/5 success) since no prior extraction_history rows existed — required to satisfy the two-eval-run completion contract. `run_extraction_eval` was called for both runs, persisting `extraction_eval` eval_runs with `extraction.macro.f1` metrics: baseline 0.178, vf-candidate 0.100.

**T03** performed browser UAT: Streamlit was started via bg_shell on port 8501, and both dashboard tabs were verified. The Compliance tab's "Extraction run view" selector surfaced the vf-candidate-20260607 run. The Eval tab showed extraction_eval run selector with metric delta rows for extraction.macro.f1, extraction.macro.precision, and extraction.macro.recall. Browser assertions confirmed both selectors rendered and at least one metric row appeared.

**T04** confirmed zero confidential tracked files via `git status --short` (all confidential artifacts were already gitignored from prior phases) and ran the full pytest suite: 303 passed (297 prior + 6 new S05 tests), exit code 0, 20 deprecation warnings from upstream docling/torch (not actionable).

## Verification

1. extraction_eval_runner.py unit tests: `venv\Scripts\python.exe -m pytest -q tests/test_extraction_eval_runner.py` → 6 passed, exit 0 (T01 evidence).
2. compliance.db eval_runs: 2 rows with eval_type='extraction_eval', status='complete' — run IDs 540affc0... (vf-candidate-20260607) and e175681d... (text-baseline-20260607); both have extraction.macro.f1 metrics (0.100 and 0.178 respectively).
3. Browser UAT (T03): Compliance tab run selector surfaced vf-candidate-20260607 with correct label; Eval tab showed metric delta rows for extraction.macro.f1/precision/recall. browser_assert confirmed both selectors rendered.
4. Git artifact check: `git status --short` shows zero entries matching confidential patterns (compliance.db, *.db, .env, SDFs/, *.pdf, *.png, etc.) — all gitignored from prior phases.
5. Full test suite: `venv\Scripts\python.exe -m pytest -q tests/` → 303 passed, 20 warnings, exit code 0 (re-verified in closeout run: 113s).

## Requirements Advanced

None.

## Requirements Validated

- R015 — Final visual-fallback candidate run (vf-candidate-20260607) and text-baseline-20260607 baseline both persisted in compliance.db with extraction.macro.f1 metrics. Dashboard Eval tab shows metric delta comparison. Macro F1: baseline 0.178 vs vf-candidate 0.100.
- R016 — git status --short confirmed zero entries matching confidential patterns. All SDFs, compliance.db, page images, and .env are gitignored.
- R017 — All S05 verification used Windows-native venv\Scripts\python.exe via gsd_exec runtime=node; no /bin/bash or bash runtime invoked.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

["T02: vf-candidate-20260607 visual-fallback CLI exited with code 1 due to 2/5 document provider failures (pre-existing); 3 successful docs still populated extraction_history. A text-baseline-20260607 text run (exit 0, 5/5 docs) was added since no prior extraction_history rows existed in the DB."]

## Known Limitations

Deprecation warnings from docling (legacy VLM options) and torch (torch.jit.script_method) are pre-existing upstream issues; no action required for the demo. Two documents (e61aa905750a7f92, e89fa720354b1e64) have pre-existing provider failures that affect visual-fallback runs but not text-only runs.

## Follow-ups

None.

## Files Created/Modified

None.
