# S02: S02 — UAT

**Milestone:** M003
**Written:** 2026-05-21T18:57:39.619Z

# UAT: S02 Extraction evaluation metrics (field-level F1)

## UAT Type
Manual + offline (local dev, SQLite fixture DB)

## Preconditions
1. Project dependencies installed in the project virtualenv.
2. A SQLite database exists with:
   - `gold_extraction_labels` populated for at least one `(doc_id, field_name)` set.
   - `extractions` (predictions) populated for the same documents/fields (at least partially).
   - `eval_runs` and `eval_metrics` tables present (created by S01 schema).

## Steps
1. Run the extraction evaluation computation for a known dataset (fixture or local DB) using the code path introduced in `src/eval/extraction_metrics.py` / repository helpers.
2. Confirm an `eval_runs` row is created for an extraction evaluation run.
3. Confirm `eval_metrics` contains per-field metrics (precision/recall/F1 and supporting counts where applicable).
4. Re-run the same evaluation input (simulate Streamlit rerun) and confirm no duplicated run/metric rows are created (upsert/rerun-safe behavior).
5. Inspect a few fields with expected normalization differences (e.g., whitespace/case) and confirm they score as matches.
6. Inspect a few fields with missing predictions or missing gold labels and confirm the metrics handle them without crashing and with deterministic zeros/empty handling.

## Expected Outcomes
- Field-level metrics are computed deterministically and match the defined normalization rules.
- The eval run and its metrics are persisted to SQLite in `eval_runs`/`eval_metrics`.
- Re-running the same evaluation does not create duplicate rows.
- Missing/partial data does not crash; metrics remain well-defined.

## Edge Cases to Check
- A field exists in gold but prediction is empty/NULL.
- A field exists in prediction but gold is missing.
- Values differ only by whitespace/case/punctuation normalization.

## Not Proven By This UAT
- Retrieval recall, RAGAS-based generation metrics, citation accuracy, latency, or cost metrics (these are S03 scope).
- Streamlit Eval tab rendering and run comparison UI (S04 scope).
