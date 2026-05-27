---
estimated_steps: 15
estimated_files: 2
skills_used: []
---

# T02: Capture populated Eval tab walkthrough

---
estimated_steps: 8
estimated_files: 3
skills_used:
  - write-docs
  - verify-before-complete
---
Why: Unit tests are not enough for S08. The slice must prove the real Streamlit app renders persisted metric history and comparison deltas from SQLite without triggering evaluator computation on rerun.

Do: Run the T01 seed helper to create .gsd/milestones/M003/slices/S08/s08-uat-populated.db. Start Streamlit through bg_shell or an equivalent Windows-safe command with DB_PATH set to that DB and port 8608. Use browser automation to navigate to http://localhost:8608, select the Eval tab, and assert visible text includes Evaluation, Run history, Metrics, at least one retrieval metric, and at least one rag metric such as rag.faithfulness.avg. Select the alternate synthetic run as comparison and assert that a comparison or delta table is visible with nonzero deltas. Capture screenshot or browser debug bundle evidence focused only on the Eval tab. Write .gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md with the command used, DB path, synthetic run IDs, metric families observed, browser assertions, screenshot or debug bundle paths, and redaction note.

Done when: A future reviewer can open the populated evidence markdown and see that the real dashboard runtime rendered two persisted runs, optional RAG or operational metrics, and comparison deltas from synthetic data only.

Threat Surface Q3: Evidence capture must not expose raw document contents. Keep the browser on the Eval tab and avoid Compliance or Chat screenshots. Seeded data must be synthetic.

Requirement Impact Q4: Directly advances R007 dashboard observability proof; preserves R010 redaction boundary. No existing requirements should be weakened because app code should not change in this task.

Failure Modes Q5: If Streamlit does not start, capture server output highlights and stop. If the browser cannot find the Eval tab or metrics, record the failing assertion in the evidence markdown and treat as blocker. If screenshots accidentally include sensitive content, discard and recapture Eval-only synthetic evidence.

Load Profile Q6: Single local Streamlit process and tiny SQLite DB. Stop the server after capture to avoid stale DB_PATH confusion.

Negative Tests Q7: The browser assertions must fail if metrics are absent, if the comparison table does not render, or if the app displays a traceback.

## Inputs

- `scripts/seed_s08_uat_eval_db.py`
- `src/app.py`
- `src/config.py`
- `src/dashboard/eval.py`
- `src/eval/repository.py`

## Expected Output

- `.gsd/milestones/M003/slices/S08/s08-uat-populated.db`
- `.gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md`

## Verification

venv/Scripts/python.exe scripts/seed_s08_uat_eval_db.py --db-path .gsd/milestones/M003/slices/S08/s08-uat-populated.db
Browser assertion: http://localhost:8608 Eval tab shows Run history, Metrics, rag.faithfulness.avg, retrieval.recall@5, and a comparison delta for two synthetic runs.

## Observability Impact

Captures runtime UI evidence and DB path used for future failure diagnosis. Does not add live tracing or log output to the application.
