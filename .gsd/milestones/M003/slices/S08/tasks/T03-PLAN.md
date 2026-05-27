---
estimated_steps: 15
estimated_files: 3
skills_used: []
---

# T03: Capture fresh database empty state and final evidence

---
estimated_steps: 9
estimated_files: 3
skills_used:
  - write-docs
  - verify-before-complete
---
Why: M003 success criteria require no crashes on missing prerequisites. S08 must prove the Eval tab handles a fresh or empty DB with actionable guidance and must package all evidence with final regression results.

Do: Create or use .gsd/milestones/M003/slices/S08/s08-fresh-empty.db with initialized schema and no eval_runs, or point DB_PATH at a missing file if the existing app behavior creates a safe empty state. Start Streamlit on port 8609 with that DB_PATH. Use browser automation to navigate to http://localhost:8609, open the Eval tab, assert the no-runs guidance is visible, and assert no Streamlit traceback appears. Capture screenshot or debug bundle evidence focused on the empty Eval tab. Write .gsd/milestones/M003/slices/S08/S08-UAT-EMPTY.md with the runtime command, DB state, assertions, and artifact paths. Then write the final .gsd/milestones/M003/slices/S08/S08-UAT-EVIDENCE.md summarizing populated and fresh DB walkthroughs, regression commands, pass/fail checklist, known limitations, and explicit R010 redaction compliance. Run the full focused regression suite after evidence capture.

Done when: The final evidence artifact demonstrates populated metrics, comparison deltas, fresh DB guidance, no crash, and no forbidden raw or secret content in UAT materials.

Threat Surface Q3: Evidence files are the main exposure surface. Only synthetic IDs, metric names, numeric values, DB paths, and screenshot or debug bundle paths may be included. Do not include provider payloads, raw prompts, answers, snippets, images of sensitive docs, Docling JSON, raw text, full hashes, or secrets.

Requirement Impact Q4: Completes S08 evidence for R007 and preserves R010. R008 remains prerequisite context only; do not attempt live Langfuse UAT.

Failure Modes Q5: If fresh DB startup fails because another tab raises on missing prerequisites, record the traceback location as a blocker instead of hiding it. If browser automation is unavailable, use Streamlit testing utilities as fallback and clearly label that fallback in the evidence artifact.

Load Profile Q6: Single local Streamlit process with no eval rows. The key load concern is not volume but rerun safety and graceful missing-table behavior.

Negative Tests Q7: Assert no evaluation runs state, no traceback text, and no forbidden raw-content terms in the final evidence artifact. Regression tests cover missing-table safety and provider-free dashboard imports.

## Inputs

- `.gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md`
- `src/app.py`
- `src/config.py`
- `src/dashboard/eval.py`
- `tests/test_dashboard_eval_tab.py`
- `tests/test_eval_repository.py`
- `tests/test_retrieval_eval_optional_metrics.py`
- `tests/test_app.py`
- `tests/test_s08_uat_seed.py`

## Expected Output

- `.gsd/milestones/M003/slices/S08/s08-fresh-empty.db`
- `.gsd/milestones/M003/slices/S08/S08-UAT-EMPTY.md`
- `.gsd/milestones/M003/slices/S08/S08-UAT-EVIDENCE.md`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_app.py tests/test_s08_uat_seed.py
Browser assertion: http://localhost:8609 Eval tab shows No evaluation runs yet and no traceback.

## Observability Impact

Packages final runtime observability evidence for M003. Future agents can inspect the evidence markdown, seeded DB paths, browser artifacts, and pytest output summary to localize any dashboard evidence regression.
