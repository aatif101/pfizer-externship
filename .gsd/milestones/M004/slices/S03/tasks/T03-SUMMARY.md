---
id: T03
parent: S03
milestone: M004
key_files:
  - src/eval/operational_metrics.py
  - src/eval/extraction_usage_eval.py
  - tests/test_extraction_usage_eval_metrics.py
key_decisions:
  - Reused the existing eval_runs/eval_metrics lifecycle and absent-safe numeric aggregation pattern, but introduced extraction-prefixed metric names and mapped extraction estimated_cost_usd to extraction.cost_usd.* metrics.
  - Kept extraction usage eval provider-free and source-run scoped, treating missing observation tables as an empty optional observation set while allowing malformed persisted numerics and metric upsert failures to surface.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:50:44.592Z
blocker_discovered: false
---

# T03: Added a provider-free extraction usage eval runner that aggregates bounded observation rows into global eval_metrics for latency, cost, and token usage.

**Added a provider-free extraction usage eval runner that aggregates bounded observation rows into global eval_metrics for latency, cost, and token usage.**

## What Happened

Extended src/eval/operational_metrics.py with extraction-specific metric constants and aggregate_extraction_usage_metrics(), preserving the existing absent-safe numeric semantics: empty, missing, or null fields emit no metrics, while malformed non-null values raise visibly. Added src/eval/extraction_usage_eval.py as an offline-safe runner that creates an eval_runs row, loads extraction_usage_observations for a selected source run_id only, persists global eval_metrics, completes successfully with no metrics when observations or older observation tables are absent, and marks eval_runs error with a sanitized reason when persisted telemetry is malformed. Added tests covering run filtering, deterministic unsorted latency percentiles, null/no-zero behavior, missing-table noop behavior, sanitized error state, bounded trace metadata, and provider-free import safety.

## Verification

Ran the required targeted pytest command via gsd_exec runtime=node spawning Windows-native venv\\Scripts\\python.exe. The command passed with 26 tests covering the new extraction usage eval metrics plus existing retrieval optional metric and eval repository behavior.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\\Scripts\\python.exe -m pytest -q tests/test_extraction_usage_eval_metrics.py tests/test_retrieval_eval_optional_metrics.py tests/test_eval_repository.py` | 0 | ✅ pass | 9653ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/eval/operational_metrics.py`
- `src/eval/extraction_usage_eval.py`
- `tests/test_extraction_usage_eval_metrics.py`
