# S05: Real five document comparison and UAT — UAT

**Milestone:** M004
**Written:** 2026-06-07T23:34:45.138Z

# S05 UAT: Real Five Document Comparison and Dashboard Verification

## UAT Type
Final-assembly — real Gemini API calls, real compliance.db writes, browser verification of two dashboard tabs.

## Preconditions
- `compliance.db` populated by T02 with extraction_history rows for `vf-candidate-20260607` and `text-baseline-20260607`.
- Streamlit app running on localhost:8501.
- Both extraction_eval eval_runs complete with `extraction.macro.f1` metrics persisted.

---

## UAT-1: Extraction Eval Runner — Metric Persistence

**Steps:**
1. Query `compliance.db`: `SELECT run_id, eval_type, status FROM eval_runs WHERE eval_type='extraction_eval'`
2. Query macro F1: `SELECT run_id, metric_name, metric_value FROM eval_metrics WHERE metric_name='extraction.macro.f1'`

**Expected Outcome:**
- At least 2 rows with `eval_type='extraction_eval'` and `status='complete'`
- At least 2 rows with `metric_name='extraction.macro.f1'` (one per eval run)

**Actual Result:** ✅ PASS — 2 extraction_eval runs complete; macro F1 = 0.100 (vf-candidate) and 0.178 (text-baseline)

---

## UAT-2: Compliance Tab — Run Selector Surfaces vf-candidate-20260607

**Steps:**
1. Navigate to `http://localhost:8501`
2. Click Compliance tab
3. Locate "Extraction run view" selector
4. Confirm `vf-candidate-20260607` is listed as an option

**Expected Outcome:** Selector shows `vf-candidate-20260607` with a label indicating Candidate or Historical run; compliance rows load or empty state renders without error.

**Actual Result:** ✅ PASS — browser_assert confirmed selector visible and vf-candidate-20260607 option present.

---

## UAT-3: Eval Tab — Metric Delta Comparison

**Steps:**
1. Navigate to Eval tab in the dashboard
2. Select an extraction_eval run referencing vf-candidate-20260607 as Primary run
3. Select text-baseline extraction_eval run as Compare run
4. Confirm metric delta rows appear

**Expected Outcome:** Rows for `extraction.macro.f1`, `extraction.macro.precision`, and `extraction.macro.recall` visible in the comparison view.

**Actual Result:** ✅ PASS — browser_assert confirmed metric delta rows rendered for all three macro metrics.

---

## UAT-4: Git Confidential Artifact Isolation

**Steps:**
1. Run `git status --short`
2. Scan output for: compliance.db, *.db, .env, SDFs/, local_data/, private/, *.pdf, *.png, *.jpg, *.jpeg, *.webp

**Expected Outcome:** Zero entries matching confidential patterns.

**Actual Result:** ✅ PASS — git status shows only .gsd internal files; no confidential artifacts tracked.

---

## UAT-5: Full Test Suite Regression

**Steps:**
1. Run `venv\Scripts\python.exe -m pytest -q tests/`

**Expected Outcome:** ≥303 tests pass, exit code 0.

**Actual Result:** ✅ PASS — 303 passed, 20 warnings (upstream docling/torch deprecations), exit code 0.

---

## Edge Cases

- **2/5 document visual-fallback failures**: `e61aa905750a7f92` and `e89fa720354b1e64` failed with ExtractionProviderError during vf-candidate-20260607. Pre-existing provider issue; extraction_history populated for 3 successful docs; eval runner completed gracefully.
- **Empty gold labels**: `run_extraction_eval` completes with no metrics rather than erroring — tested in T01 unit tests.
- **Idempotent re-runs**: Repeated calls to `run_extraction_eval` with same params upsert without error — verified in T01.
