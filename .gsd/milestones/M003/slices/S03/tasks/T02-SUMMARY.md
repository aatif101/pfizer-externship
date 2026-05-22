---
id: T02
parent: S03
milestone: M003
key_files:
  - src/eval/repository.py
  - src/eval/retrieval_eval_runner.py
  - tests/test_retrieval_eval_runner.py
key_decisions:
  - Treat retrieved top-k hits as citations for citation accuracy during retrieval eval (until a separate RAG pipeline provides explicit citations).
duration: 
verification_result: passed
completed_at: 2026-05-21T19:03:05.500Z
blocker_discovered: false
---

# T02: Added provider-free retrieval eval runner that computes recall@k and page-level citation accuracy from SQLite gold queries and persists results into eval_runs/eval_metrics with idempotent upserts.

**Added provider-free retrieval eval runner that computes recall@k and page-level citation accuracy from SQLite gold queries and persists results into eval_runs/eval_metrics with idempotent upserts.**

## What Happened

Extended src/eval/repository.py with small retrieval-index helpers (latest run_id lookup + listing pages) to support evaluation without pulling retrieval DTOs. Implemented src/eval/retrieval_eval_runner.py, which creates an eval_run row (eval_type=retrieval_eval), loads gold queries/targets, runs the existing SQLite-backed retriever (retrieve_evidence) for each query, and persists both global and per-query metrics into eval_metrics using stable metric names and scope fields. Runner is empty-state safe (no index run or no gold queries => marks run complete with no metrics) and error-safe (marks run error with sanitized reason). Added deterministic tests that build a minimal SQLite corpus + retrieval index, insert gold queries/targets, run the eval, and assert persisted metrics and empty-state behavior.

## Verification

Ran pytest for the new retrieval eval runner test suite.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_runner.py -q` | 0 | ✅ pass | 4140ms |

## Deviations

Used the existing HybridTextRetriever (retrieve_evidence) directly for evaluation and treated the top-k retrieved pages as citations, matching the slice-level page-based citation definition from T01.

## Known Issues

None.

## Files Created/Modified

- `src/eval/repository.py`
- `src/eval/retrieval_eval_runner.py`
- `tests/test_retrieval_eval_runner.py`
