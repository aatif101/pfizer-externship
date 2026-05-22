---
id: S02
parent: M003
milestone: M003
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - src/eval/extraction_metrics.py
  - src/eval/repository.py
  - tests/test_extraction_eval_metrics.py
key_decisions: []
patterns_established:
  - (none)
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-05-21T18:57:39.618Z
blocker_discovered: false
---

# S02: S02

**Implemented deterministic extraction field-level precision/recall/F1 evaluation from SQLite gold vs predictions, with normalization and rerun-safe persistence, backed by offline tests.**

## What Happened

This slice adds the extraction evaluation core needed for M003’s dashboard evaluation harness. It implements deterministic field-level scoring (precision, recall, F1) by comparing gold extraction labels against persisted extraction predictions, including explicit normalization rules so formatting differences (whitespace/case/date-like string noise) do not create spurious mismatches. The implementation reads the necessary rows from SQLite, computes per-field counts and metrics with robust handling of missing/empty values, and persists results into the existing eval_runs/eval_metrics tables using rerun-safe upsert semantics so Streamlit reruns do not duplicate runs or metrics. Offline pytest coverage exercises normalization, scoring edge cases (missing/wrong/partial), and persistence behavior to ensure the metric definitions are stable and credible for evaluators and downstream UI use.

## Verification

pytest (venv python) against the slice test suite: `venv\\Scripts\\python.exe -m pytest tests/test_extraction_eval_metrics.py -q` (executed via gsd_exec using node spawn on Windows). Result: 6 passed in 0.63s.

## Requirements Advanced

- R007 — Implemented and tested deterministic extraction field-level precision/recall/F1 computation with SQLite-backed persistence to eval_runs/eval_metrics for dashboard consumption.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

This slice evaluates extraction only; retrieval and RAG evaluation metrics are not included and remain S03 scope.

## Follow-ups

Wire these persisted extraction eval runs into the Streamlit Eval tab (S04) and add retrieval/RAG metrics (S03).

## Files Created/Modified

None.
