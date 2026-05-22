---
id: T01
parent: S02
milestone: M003
key_files:
  - src/eval/extraction_metrics.py
  - src/eval/repository.py
  - tests/test_extraction_eval_metrics.py
key_decisions:
  - Treat wrong non-null predictions (gold non-null, pred non-null but !=) as FP+FN to reflect both an incorrect answer and a missed correct value; skip gold-null instances from scoring.
duration: 
verification_result: passed
completed_at: 2026-05-21T18:56:26.178Z
blocker_discovered: false
---

# T01: Added provider-free extraction evaluation utilities: deterministic normalization (including date parsing) plus per-field TP/FP/FN precision/recall/F1 scoring, and a SQLite helper to list predicted extractions.

**Added provider-free extraction evaluation utilities: deterministic normalization (including date parsing) plus per-field TP/FP/FN precision/recall/F1 scoring, and a SQLite helper to list predicted extractions.**

## What Happened

Implemented a new `src/eval/extraction_metrics.py` module to normalize extracted values deterministically (whitespace collapse + casefold; best-effort ISO date normalization for date-like fields) and compute per-field extraction scores from gold vs predicted row lists using explicit TP/FP/FN rules (including FP+FN for wrong non-null predictions). Added macro-averaging helpers across fields with gold support.

Extended `src/eval/repository.py` with a minimal, provider-free SQLite read helper `list_predicted_extractions(db_path)` that returns extraction rows shaped for metric computation (doc_id, field_name, normalized_value, review_state). No provider/LLM imports were introduced.

## Verification

Ran the slice’s offline pytest to validate normalization behavior (including empty/partial handling) and deterministic per-field scoring + macro averages.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\\Scripts\\python.exe -m pytest tests/test_extraction_eval_metrics.py -q` | 0 | ✅ pass | 1848ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/eval/extraction_metrics.py`
- `src/eval/repository.py`
- `tests/test_extraction_eval_metrics.py`
