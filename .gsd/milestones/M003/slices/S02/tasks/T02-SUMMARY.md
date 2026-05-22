---
id: T02
parent: S02
milestone: M003
key_files:
  - tests/test_extraction_eval_metrics.py
key_decisions:
  - None (tests already encoded the metric definitions and persistence dedupe contract).
duration: 
verification_result: passed
completed_at: 2026-05-21T18:57:00.911Z
blocker_discovered: false
---

# T02: Verified offline tests cover extraction normalization, scoring rules, and SQLite eval metric upsert deduping end to end.

**Verified offline tests cover extraction normalization, scoring rules, and SQLite eval metric upsert deduping end to end.**

## What Happened

Reviewed the existing test suite and underlying eval/DB code to ensure T02’s requirements were satisfied: normalization tests cover whitespace+casefold and date parsing with deterministic fallback; scoring tests cover TP, FN, and FP+FN behavior for wrong non-null predictions; macro averaging behavior is explicit for empty and non-empty field sets; and persistence integration tests create a fresh SQLite DB with `init_db`, insert minimal FK-satisfying `documents`, load gold labels + predicted `extractions`, create an `eval_runs` row, upsert both field-scoped and global metrics, and verify `list_eval_metrics()` returns a single row per metric key (no duplication on rerun).

No code changes were required because `tests/test_extraction_eval_metrics.py` already implements the full T02 plan, including dedupe/overwrite semantics via the unique index + `ON CONFLICT` upsert in `upsert_eval_metric()`.

## Verification

Ran the targeted pytest file offline and confirmed all tests pass.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/test_extraction_eval_metrics.py -q` | 0 | ✅ pass | 640ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `tests/test_extraction_eval_metrics.py`
