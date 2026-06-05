---
id: T03
parent: S01
milestone: M004
key_files:
  - src/extraction/cli.py
  - src/eval/repository.py
  - tests/test_extraction_cli.py
  - tests/test_eval_repository.py
key_decisions:
  - Eval run-scoped predictions read only `extraction_history` for an explicit run id and intentionally do not fall back to latest-write rows.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:18:25.325Z
blocker_discovered: false
---

# T03: Wired explicit extraction run IDs through CLI commands and added run-scoped eval prediction reads from extraction history.

**Wired explicit extraction run IDs through CLI commands and added run-scoped eval prediction reads from extraction history.**

## What Happened

Added optional `--run-id` support to both `extract` and `extract-all`. The CLI now passes the supplied run id through `_extract_one()` to `run_extraction()`, and batch extraction reuses the same supplied run id for every ingested document while keeping output bounded to identifiers, counts, trace status, and review diagnostics. Added `list_predicted_extractions_for_run()` in the eval repository to read deterministic `doc_id`, `field_name`, `normalized_value`, and `review_state` rows from `extraction_history` for one explicit run without changing existing latest-write `list_predicted_extractions()` behavior. Updated CLI tests to assert explicit single-doc and batch run ids reach the fake provider and persist queryable run history, and updated eval repository tests to assert selected-run history reads ignore overwritten latest rows and return empty rows for missing runs.

## Verification

Ran the required Windows-safe pytest command via `gsd_exec` node wrapper: `venv\Scripts\python.exe -m pytest -q tests/test_extraction_cli.py tests/test_eval_repository.py tests/test_extraction_persistence.py`. All 29 targeted tests passed, covering CLI run-id propagation, persisted run history for single and batch commands, latest-write compatibility, and eval selected-run reads without fallback.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_extraction_cli.py tests/test_eval_repository.py tests/test_extraction_persistence.py` | 0 | ✅ pass | 10165ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/cli.py`
- `src/eval/repository.py`
- `tests/test_extraction_cli.py`
- `tests/test_eval_repository.py`
