---
id: T02
parent: S04
milestone: M003
key_files:
  - src/dashboard/eval.py
  - tests/test_dashboard_eval_tab.py
key_decisions:
  - Comparison defaults to same eval_type filtering with explicit override to allow cross-type comparisons; comparison table uses (metric_name, scope_type, scope_id) keys and tolerates missing metrics by emitting blanks.
duration: 
verification_result: passed
completed_at: 2026-05-22T17:56:55.842Z
blocker_discovered: false
---

# T02: Added Eval tab run-to-run comparison UI with metric deltas and tests for comparison/filter behavior.

**Added Eval tab run-to-run comparison UI with metric deltas and tests for comparison/filter behavior.**

## What Happened

Extended `src/dashboard/eval.py` to support selecting an optional comparison run with a default compatibility filter (same eval_type), plus an explicit override to allow cross-type comparisons. Added a dedicated comparison section that builds a deterministic table keyed by (metric_name, scope_type, scope_id) showing value A, value B, and delta (B - A), with toggles for "show only changed" and whether to include per-scope metrics. Implemented robust behavior when metrics are missing on either side (blank values and no delta) so the UI never crashes. Updated and expanded `tests/test_dashboard_eval_tab.py` to cover two-run comparisons with deltas, floating-point-safe assertions, and default incompatible-type filtering.

## Verification

Ran pytest for the eval dashboard tests; all passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_dashboard_eval_tab.py -q` | 0 | ✅ pass | 4380ms |

## Deviations

Used `bash` to run pytest because `gsd_exec` in this environment cannot exec /bin/bash (WSL relay error).

## Known Issues

None.

## Files Created/Modified

- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`
