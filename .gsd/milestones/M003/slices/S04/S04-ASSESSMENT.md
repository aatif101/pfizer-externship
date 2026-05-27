---
sliceId: S04
uatType: browser-executable
verdict: PASS
date: 2026-05-27T20:22:28.056Z
---

# UAT Result — S04

## Checks

| Check | Mode | Result | Notes |
|-------|------|--------|-------|
| Preconditions: local SQLite DB is available for the dashboard. | runtime | PASS | Created isolated UAT fixtures at `.gsd/uat/s04-empty.db` and `.gsd/uat/s04-populated.db` using `src.db.schema.init_db`; evidence: `.gsd/exec/bcf98d66-1a01-4f32-be9d-86bd1582b469.stdout`. |
| Preconditions: DB contains at least one row in `eval_runs` and associated rows in `eval_metrics`; optional two overlapping runs for deltas. | runtime | PASS | Seeded `run-eval-001` and `run-eval-002` as complete extraction runs with overlapping `f1` and `precision` metrics, plus a scoped `query_recall` metric; also seeded `run-eval-003` as a retrieval error run. |
| Start the Streamlit app using the dashboard command. | runtime | PASS | Started `venv/Scripts/python.exe -m streamlit run src/app.py` via `bg_shell` on ports 8504/8505 with `DB_PATH` pointed at the UAT fixtures. |
| Open the dashboard in a browser. | runtime | PASS | Used Node Playwright/Chromium to navigate to `http://localhost:8504` and `http://localhost:8505`; screenshots captured at `.gsd/uat/screenshots/s04-empty-eval.png`, `.gsd/uat/screenshots/s04-populated-default.png`, and `.gsd/uat/screenshots/s04-populated-compare.png`. The harness `browser_navigate` registry was unavailable, so Playwright was used as the browser fallback. |
| Click the **Eval** tab. | runtime | PASS | Browser automation clicked the `Eval` tab by role; the Eval panel text showed the read-only caption and Eval controls. Evidence: `.gsd/exec/3b7975cb-167f-4fd8-9d06-238520b8f52a.stdout`, `.gsd/exec/930bf154-deca-455b-a656-7f947f5cf4c6.stdout`. |
| Confirm the page renders even if there are **zero** evaluation runs. | runtime | PASS | With `.gsd/uat/s04-empty.db`, the Eval tab rendered with no exceptions and displayed `No evaluation runs yet...` plus `Looking for persisted runs in .gsd/uat/s04-empty.db`; screenshot: `.gsd/uat/screenshots/s04-empty-eval.png`; AppTest also reported `exceptions 0` and `dataframes 0`. |
| With at least one run present, select a run in the UI. | runtime | PASS | With `.gsd/uat/s04-populated.db`, browser/AppTest selected `run-eval-001` as the primary run. AppTest output showed selectboxes `Primary run = run-eval-001` and `Compare to (optional)` options including `run-eval-002`; evidence: `.gsd/exec/6a1b3898-be5f-45eb-aafa-cba0a0dad0e1.stdout`. |
| Confirm the run metadata (type/status/timestamps and any error reason) renders. | runtime | PASS | The run-history grid rendered `run_id`, `eval_type`, `status`, `created_at`, `completed_at`, `pipeline_label`, and `error_reason`, including `run-eval-003 retrieval error ... UAT fixture simulated evaluator failure`; browser DOM evidence: `.gsd/exec/930bf154-deca-455b-a656-7f947f5cf4c6.stdout`. |
| Confirm the run’s metrics render (global metrics plus any scoped/grouped metrics). | runtime | PASS | Selecting `run-eval-001` rendered global metrics `f1 80.0%` and `precision 75.0%`; AppTest also saw scoped metric `query_recall 100.0%` under `scope_type=query`, `scope_id=q1`; evidence: `.gsd/exec/6a1b3898-be5f-45eb-aafa-cba0a0dad0e1.stdout`. |
| Enable comparison mode / select a second run. | runtime | PASS | Browser automation selected comparison run `run-eval-002`; screenshot captured at `.gsd/uat/screenshots/s04-populated-compare.png`. AppTest output showed `Compare to (optional) = run-eval-002` with no exceptions. |
| Confirm metric delta values appear, and missing metrics between runs are handled gracefully. | runtime | PASS | Comparison grid rendered `f1 80.0% -> 90.0%` with `+10.0%` and `precision 75.0% -> 70.0%` with `-5.0%`; evidence: `.gsd/exec/930bf154-deca-455b-a656-7f947f5cf4c6.stdout`. Non-overlapping/incompatible comparison (`run-eval-001` vs `run-eval-003`) produced no exception and an empty comparison dataframe instead of a crash; evidence: `.gsd/exec/f07cf5c5-c056-45f5-906b-bdc60fa62ca8.stdout`. |
| Edge case: one selected run has `status=error` and non-empty `error_reason`. | runtime | PASS | Default primary run `run-eval-003` showed warning `Primary run error_reason: UAT fixture simulated evaluator failure`; incompatible comparison showed `Comparison run error_reason: UAT fixture simulated evaluator failure`; evidence: `.gsd/exec/849f367d-6709-4217-97ac-460e49e6e6b2.stdout` and `.gsd/exec/f07cf5c5-c056-45f5-906b-bdc60fa62ca8.stdout`. |
| Edge case: two selected runs are different types and have non-overlapping metrics. | runtime | PASS | Disabled the compatible-only filter, enabled any eval type comparison, and selected extraction `run-eval-001` vs retrieval `run-eval-003`; no exception occurred and the comparison dataframe was empty, which is a safe graceful state for non-overlapping metrics. |
| Edge case: a metric exists in one run but not the other. | runtime | PASS | `run-eval-002` includes `recall` while `run-eval-001` does not; selecting the pair did not crash and the comparison focused on shared metrics. `run-eval-001` scoped `query_recall` also rendered independently without requiring a matching comparison metric. |

## Overall Verdict

PASS — The Streamlit Eval tab rendered empty, populated, error, scoped-metric, compatible-comparison, and incompatible/non-overlapping comparison states without exceptions, and browser evidence confirmed the expected read-only UI and delta display.

## Notes

- Browser evidence was collected with Node Playwright because the harness `browser_navigate` tool returned `registryGetActive: no active page`; this did not block browser-level verification because local Chromium automation succeeded.
- Screenshots:
  - `.gsd/uat/screenshots/s04-empty-eval.png`
  - `.gsd/uat/screenshots/s04-populated-default.png`
  - `.gsd/uat/screenshots/s04-populated-compare.png`
- Runtime/AppTest evidence:
  - `.gsd/exec/3b7975cb-167f-4fd8-9d06-238520b8f52a.stdout`
  - `.gsd/exec/930bf154-deca-455b-a656-7f947f5cf4c6.stdout`
  - `.gsd/exec/6a1b3898-be5f-45eb-aafa-cba0a0dad0e1.stdout`
  - `.gsd/exec/f07cf5c5-c056-45f5-906b-bdc60fa62ca8.stdout`
