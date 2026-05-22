# S04: S04 — UAT

**Milestone:** M003
**Written:** 2026-05-22T18:12:26.858Z

# UAT: Streamlit Eval tab (run history + comparison)

## UAT Type
Manual UI verification (local dev)

## Preconditions
1. Create/choose a local SQLite DB file used by the dashboard.
2. DB contains at least one row in `eval_runs` and associated rows in `eval_metrics`.
   - Optional: have two runs with overlapping metrics to validate deltas.
3. Start the Streamlit app (same command used for the rest of the dashboard).

## Steps
1. Open the dashboard in a browser.
2. Click the **Eval** tab.
3. Confirm the page renders even if there are **zero** evaluation runs.
4. With at least one run present, select a run in the UI.
5. Confirm the run metadata (type/status/timestamps and any error reason) renders.
6. Confirm the run’s metrics render (global metrics plus any scoped/grouped metrics).
7. Enable comparison mode / select a second run.
8. Confirm metric delta values appear, and that missing metrics between runs are handled gracefully (no crash; delta display is sensible).

## Expected Results
- With no runs: a friendly empty state is shown and no exception is raised.
- With one run: metrics and run status metadata render without triggering any background evaluation computation.
- With two runs: delta view clearly indicates which run improved/regressed per metric.

## Edge Cases to Check
- One of the selected runs has `status=error` and a non-empty `error_reason`.
- Two selected runs are different types (e.g., extraction vs retrieval) and have non-overlapping metrics.
- A metric exists in one run but not the other.

## Not Proven By This UAT
- Correctness of the underlying metric calculations (those are validated by earlier evaluation harness slices).
- Performance characteristics on very large run histories.
- Any live provider integration (Eval tab is intentionally provider-free/read-only).
