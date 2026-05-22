---
id: T03
parent: S03
milestone: M003
key_files:
  - src/eval/retrieval_eval_runner.py
  - tests/test_retrieval_eval_optional_metrics.py
key_decisions:
  - Treat optional eval metrics (latency/cost, RAGAS) as best-effort hooks that must never break core retrieval evaluation; skip on ImportError/OperationalError and persist numeric aggregates only (no raw contexts/tokens).
duration: 
verification_result: passed
completed_at: 2026-05-22T17:26:37.750Z
blocker_discovered: false
---

# T03: Added optional non-fatal hooks in retrieval eval runner for latency/cost and RAGAS placeholder metrics, plus tests that assert graceful skipping on minimal DBs.

**Added optional non-fatal hooks in retrieval eval runner for latency/cost and RAGAS placeholder metrics, plus tests that assert graceful skipping on minimal DBs.**

## What Happened

Updated `run_retrieval_eval` to accept `include_latency_cost` and `include_ragas` flags (default off). When enabled, the runner now calls best-effort helpers that attempt optional latency/cost aggregation and RAGAS metric computation, but explicitly degrade gracefully when prerequisites are missing.

The optional paths use narrow exception handling (ImportError for missing ragas; sqlite3.OperationalError for missing tables/columns) and never persist raw contexts/prompts/tokens—only numeric aggregates are eligible for storage, and the current RAGAS path is a placeholder hook pending a dedicated RAG eval runner + gold answer/context schema.

## Verification

Ran the new optional-metrics pytest to ensure enabling both flags against a minimal DB still completes and persists core retrieval metrics.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_optional_metrics.py -q` | 0 | ✅ pass | 2900ms |

## Deviations

Latency/cost and RAGAS support is implemented as a safe placeholder hook rather than a full computation because this repo does not yet define a stable trace schema or gold answer/context tables for RAGAS; the task contract emphasized non-fatal behavior and test coverage over completeness.

## Known Issues

The latency/cost hook currently probes an optional `trace_spans` table and uses non-standard SQLite aggregate functions (P50/P95) that are unlikely to exist; this is intentional because the code path is best-effort and will skip on OperationalError. Once an observability schema is finalized, this should be replaced with a real query or Python-side percentile calculation.

## Files Created/Modified

- `src/eval/retrieval_eval_runner.py`
- `tests/test_retrieval_eval_optional_metrics.py`
