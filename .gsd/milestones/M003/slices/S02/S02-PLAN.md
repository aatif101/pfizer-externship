# S02: Extraction evaluation metrics (field-level F1)

**Goal:** Compute deterministic field-level extraction evaluation metrics (precision/recall/F1) from SQLite gold labels vs persisted predictions, persist results as eval_runs/eval_metrics rows, and prove behavior with offline tests (including normalization + empty/partial data handling).
**Demo:** Given gold extraction labels and predicted extraction rows in SQLite, compute per-field precision, recall, and F1 and persist an extraction eval run with summary metrics.

## Must-Haves

- Given SQLite gold_extraction_labels and persisted extractions rows, the code computes per-field precision/recall/F1 deterministically.
- Metrics are persisted to eval_runs/eval_metrics using rerun-safe upserts (no duplication) with clear scoping for per-field metrics.
- New offline pytest coverage proves normalization rules, scoring edge cases (missing/wrong), and persistence semantics.

## Proof Level

- This slice proves: contract + integration (SQLite-backed, offline)

## Integration Closure

Consumes: `gold_extraction_labels` and `extractions` tables (from ingestion/extraction pipeline) and S01 evaluation repository helpers.
Produces: extraction metric computation module + tests; persists metrics via existing `eval_runs`/`eval_metrics` contract for S04 UI consumption.
Remaining for milestone usability: S03 retrieval/RAG metrics and S04 Streamlit Eval tab wiring/rendering.

## Verification

- Primary signal is persisted SQLite eval run history (eval_runs/eval_metrics) that downstream UI can query; failures are surfaced as pytest failures in this slice.

## Tasks

- [x] **T01: Implement extraction F1 metric computation with normalization and SQLite data access** `est:2.5h`
  Why:
  - M003 needs credible, repeatable extraction quality metrics. Field-level F1 is the simplest evaluator-friendly baseline, but it must be deterministic and robust to missing values.
  - Files: `src/eval/extraction_metrics.py`, `src/eval/repository.py`
  - Verify: venv\\Scripts\\python.exe -m pytest tests/test_extraction_eval_metrics.py -q

- [x] **T02: Add offline tests proving extraction eval metrics, normalization, and persistence via eval repository** `est:2.5h`
  Why:
  - Metrics credibility depends on explicit, executable definitions: how normalization works, how missing/abstained fields are treated, and how results are persisted without Streamlit duplication.
  - Files: `tests/test_extraction_eval_metrics.py`
  - Verify: venv\\Scripts\\python.exe -m pytest tests/test_extraction_eval_metrics.py -q

## Files Likely Touched

- src/eval/extraction_metrics.py
- src/eval/repository.py
- tests/test_extraction_eval_metrics.py
