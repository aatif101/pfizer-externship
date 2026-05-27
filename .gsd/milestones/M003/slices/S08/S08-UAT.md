# S08: Record Eval tab UAT evidence — UAT

**Milestone:** M003
**Written:** 2026-05-27T21:59:43.774Z

## UAT Type

Runtime dashboard walkthrough with deterministic synthetic data plus regression verification.

## Preconditions

- Use the project Python 3.11 virtual environment via `venv/Scripts/python.exe`.
- No live provider, Langfuse, RAGAS, or document corpus secrets are required.
- S08 artifacts are stored under `.gsd/milestones/M003/slices/S08/`.

## Steps and Expected Outcomes

1. Generate the populated UAT database with `venv/Scripts/python.exe scripts/seed_s08_uat_eval_db.py --db-path .gsd/milestones/M003/slices/S08/s08-uat-populated.db`.
   - Expected: command exits 0 and reports two seeded synthetic eval runs.
2. Open the Streamlit dashboard with `DB_PATH` pointing at `s08-uat-populated.db` and navigate to the Eval tab.
   - Expected: Eval tab shows Evaluation, Run history, Metrics, two complete synthetic run IDs, `retrieval.recall@5`, `rag.faithfulness.avg`, `rag.answer_relevancy.avg`, latency, cost, and token metrics.
3. Select one synthetic run as primary and the other as comparison.
   - Expected: Compare runs section renders a delta column with nonzero deltas such as faithfulness, recall, latency, and token differences; no traceback appears.
4. Initialize/use `.gsd/milestones/M003/slices/S08/s08-fresh-empty.db` with zero eval rows and open the Eval tab against it.
   - Expected: Eval tab displays `No evaluation runs yet. Run the evaluation CLI/tests to populate eval_runs and eval_metrics in the SQLite database.` and shows no Streamlit exception or traceback.
5. Run the focused regression suite.
   - Expected: `venv/Scripts/python.exe -m pytest -q tests/test_dashboard_eval_tab.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_app.py tests/test_s08_uat_seed.py` exits 0.

## Edge Cases

- Fresh DB with schema but no eval rows renders actionable guidance instead of crashing.
- Optional provider/Langfuse/RAGAS services are absent and are not required for UAT.
- Re-running the seed helper is deterministic and does not duplicate metric history.
- Artifacts remain sanitized: no raw prompts, generated answers, snippets, provider payloads, secrets, sensitive document images, Docling JSON, raw text, or full hashes are included.

## Evidence

- Populated evidence: `.gsd/milestones/M003/slices/S08/S08-UAT-POPULATED.md`
- Empty-state evidence: `.gsd/milestones/M003/slices/S08/S08-UAT-EMPTY.md`
- Final evidence package: `.gsd/milestones/M003/slices/S08/S08-UAT-EVIDENCE.md`
- Closeout regression: 30 passed.
- Closeout artifact validation: populated runs 2, required metrics 12, fresh eval row counts 0/0.
