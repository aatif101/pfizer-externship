# S05 Research: Real Five Document Comparison and UAT

**Depth:** Targeted — known patterns, one missing orchestrator module, no novel technology.

## Summary

S05 is the M004 capstone. All prior slices delivered the required building blocks: run-scoped extraction history (S01), compliance dashboard run selector (S02), Gemini usage observations (S03), and targeted visual fallback (S04). S05 must wire them together into a final measurable comparison:

1. Create the missing **extraction eval runner** (`src/eval/extraction_eval_runner.py`) — the only new module.
2. Write offline unit tests for that runner.
3. Execute a real visual-fallback candidate run against the local `compliance.db` (live API, not part of routine tests).
4. Run extraction eval for the new candidate plus existing baseline/candidate runs to populate `eval_runs` + `eval_metrics`.
5. Browser-verify both the Compliance tab (run selector from S02) and Eval tab (comparison view from M003).
6. Confirm confidential artifacts remain untracked with `git status`.

## What Exists

### Repository surface (confirmed)

- `src/eval/repository.py` — `list_predicted_extractions_for_run(db_path, run_id)` reads `extraction_history` by explicit `run_id` with no latest-write fallback (line 562). `list_gold_extraction_labels(db_path)` reads `gold_extraction_labels`. Both are already tested in `tests/test_eval_repository.py`.
- `src/eval/extraction_metrics.py` — `compute_extraction_field_scores(gold_rows, pred_rows)` returns per-field `FieldScore(tp, fp, fn, precision, recall, f1)`. `compute_macro_averages(per_field_scores)` returns `{"precision", "recall", "f1"}`. Deterministic, provider-free.
- `src/eval/extraction_usage_eval.py` — exact model for the new runner: `create_eval_run` → load observations → aggregate → `upsert_eval_metric` → `mark_eval_run_complete`. Has `@observe`, sanitized error handling, and bounded trace metadata. The extraction eval runner must follow the same skeleton.
- `src/eval/repository.py` — `create_eval_run`, `upsert_eval_metric`, `mark_eval_run_complete`, `mark_eval_run_error` are all implemented and tested.
- `src/extraction/cli.py` — `extract-all --visual-fallback --run-id <id>` is wired and working (from S04).
- `src/dashboard/eval.py` — `render_eval_tab()` already supports primary + compare run selection, metric delta display, and per-scope metrics via expander. **No dashboard changes needed**: once eval runs are persisted with the right `eval_type`, the Eval tab renders them automatically.
- `src/dashboard/compliance.py` — Run selector from S02 is complete. No changes needed.

### What is MISSING

- `src/eval/extraction_eval_runner.py` — **does not exist** (`glob src/eval/extraction_eval_runner.py` returned no match). This is the only new module required by S05.
- No `tests/test_extraction_eval_runner.py` exists.
- No `scripts/` helper for running extraction eval on real data (the real run is done ad-hoc via Python, not a separate CLI command — this is acceptable).

### Confidential artifact status

`.gitignore` already covers: `compliance.db`, `*.db`, `*.sqlite`, `.env`, `SDFs/`, `data/sdfs/`, `data/pdfs/`, `private/`, `local_data/`, `reports/private/`, `*.pdf`, `*.png`, `*.jpg`, `*.jpeg`, `*.webp`. All confidential SDF artifacts are covered.

## Implementation Landscape

### T01 — Create `src/eval/extraction_eval_runner.py` + tests

**File to create:** `src/eval/extraction_eval_runner.py`

Pattern: mirror `extraction_usage_eval.py` exactly:
- `@observe(name="extraction_eval_run")` decorator on the public function
- `run_extraction_eval(db_path, *, source_run_id, eval_run_id=None, pipeline_label="extraction_eval")` → returns `str` (eval_run_id)
- Loads gold labels via `list_gold_extraction_labels(db_path)` 
- Loads predicted extractions via `list_predicted_extractions_for_run(db_path, source_run_id)` (reads `extraction_history`, no fallback)
- Computes `compute_extraction_field_scores(gold, preds)` → per-field FieldScore
- Computes `compute_macro_averages(per_field_scores)` → macro dict
- Persists global metrics: `extraction.macro.f1`, `extraction.macro.precision`, `extraction.macro.recall` (no scope)
- Persists scoped metrics: `extraction.f1`, `extraction.precision`, `extraction.recall` with `scope_type="field"`, `scope_id=<field_name>`
- Safe empty-state: if no gold labels or no predicted rows → complete with no metrics (not an error)
- Handles `sqlite3.OperationalError` for missing `gold_extraction_labels` or `extraction_history` tables gracefully (return empty, still marks run complete)
- Bounded trace metadata: `boundary`, `status`, `eval_type`, `run_id`, `source_run_id`, `gold_count`, `pred_count`, `metric_count`, `error_class` — no field values, spans, raw text

**File to create:** `tests/test_extraction_eval_runner.py`

Tests needed (all use `tmp_path`, no live API):
1. `test_run_extraction_eval_produces_macro_and_field_metrics` — seed gold + predicted rows in `extraction_history`, verify `extraction.macro.f1` persisted
2. `test_run_extraction_eval_with_no_gold_labels_completes_with_no_metrics` — empty gold table → run status=complete, no metrics
3. `test_run_extraction_eval_with_no_predicted_rows_completes_with_no_metrics` — run_id not in extraction_history → run complete, no metrics
4. `test_run_extraction_eval_is_idempotent_on_repeated_calls` — calling twice upserts same metrics (no dupe rows)
5. `test_run_extraction_eval_marks_run_complete_on_success`
6. `test_run_extraction_eval_persists_per_field_scoped_metrics` — verify `scope_type="field"`, `scope_id` matches a field name

Seeding helpers: use `init_db(db_path)`, `insert_document`, `upsert_extraction_record` (writes to latest-write `extractions` and `extraction_history`), seed `gold_extraction_labels` via direct SQL insert.

### T02 — Real visual-fallback candidate run against compliance.db

This task executes live API calls and persists the final comparison. It is **not a pytest test** — it is a scripted sequence documented in the task verification.

Steps:
1. Decide a stable candidate run_id: e.g. `vf-candidate-20260607` 
2. Run extract-all with visual fallback against compliance.db:
   ```
   venv\Scripts\python.exe -m src.extraction.cli extract-all --db-path compliance.db --run-id vf-candidate-20260607 --visual-fallback
   ```
3. Run extraction eval for the visual-fallback candidate:
   ```python
   from src.eval.extraction_eval_runner import run_extraction_eval
   run_extraction_eval("compliance.db", source_run_id="vf-candidate-20260607")
   ```
4. Repeat `run_extraction_eval` for any previously persisted baseline and packet-aware candidate run IDs (read from `eval_runs` table or known from prior real runs).
5. Record eval_run_ids for comparison in the Eval tab UAT.

Verification evidence: `gsd_exec runtime=node` spawning the above Python commands, checking exit_code=0 and output (no `/bin/bash`).

### T03 — Dashboard browser UAT

Two verification checkpoints:
1. **Compliance tab** — start `venv\Scripts\python.exe -m streamlit run src/app.py`, navigate to Compliance tab, confirm run selector shows visual-fallback candidate, select it, confirm rows load correctly with appropriate label (Candidate run or Historical run).
2. **Eval tab** — navigate to Eval tab, confirm visual-fallback eval run appears in run history, select it as Primary run, select baseline eval run as Compare, confirm metric delta rows appear.

Browser tooling: use the `browser_navigate` tool against `http://localhost:8501` after starting Streamlit. The Streamlit process must be started in bg_shell before UAT steps.

### T04 — Git ignored artifact check + full test suite closeout

```
git status --short
```
Must show NO tracked changes for: `compliance.db`, `*.db`, `.env`, `local_data/`, `SDFs/`, `*.pdf`, `*.png`.

Then full test suite:
```
venv\Scripts\python.exe -m pytest -q tests/
```
All existing 297 + new S05 tests must pass. Windows-native only (`gsd_exec runtime=node`).

## Metric Naming Convention

Following the `extraction.` prefix established in `operational_metrics.py`:

| Metric Name | Scope | Description |
|---|---|---|
| `extraction.macro.f1` | global | Macro-average F1 across all scored fields |
| `extraction.macro.precision` | global | Macro-average precision |
| `extraction.macro.recall` | global | Macro-average recall |
| `extraction.f1` | `scope_type="field"`, `scope_id=<field_name>` | Per-field F1 |
| `extraction.precision` | `scope_type="field"`, `scope_id=<field_name>` | Per-field precision |
| `extraction.recall` | `scope_type="field"`, `scope_id=<field_name>` | Per-field recall |

The Eval dashboard `_RATIO_METRIC_TOKENS` already includes `"f1"`, `"precision"`, `"recall"` so these metrics will render as percentages automatically.

## Risks and Constraints

- **Gold labels are confidential** — `gold_extraction_labels` is only in local `compliance.db`. Unit tests must seed their own tmp_path DB with fake gold rows via direct SQL. Never read from real `compliance.db` in tests.
- **`list_predicted_extractions_for_run` reads `extraction_history`** — confirmed. Unit tests must insert records into `extraction_history` (done via `upsert_extraction_record` with a `run_id`).
- **No eval runner CLI** — Running eval for real data uses Python directly (not a separate CLI command). This is acceptable for a demo; the task should document a reusable Python snippet.
- **Eval tab already complete** — do not add new dashboard logic. Run comparison is available via existing selector UI.
- **Windows-native verification only** — all `gsd_exec` calls must use `runtime=node` spawning `venv\Scripts\python.exe`. Never `runtime=bash` or `/bin/bash`.
- **297 existing tests must not regress** — the new runner adds ~6 tests; verify the full suite passes at T04 closeout.
