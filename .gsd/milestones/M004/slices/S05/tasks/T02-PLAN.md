---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T02: Run real visual-fallback candidate extraction and populate eval runs

Why: R015 requires a measured final comparison of visual-fallback candidates against baselines in real compliance.db. This task performs the live Gemini API extraction run and persists eval_metrics for dashboard comparison. No tracked files are created; all writes go to gitignored compliance.db. Do (all via gsd_exec runtime=node, Windows-native only - no /bin/bash): (1) Choose stable candidate run_id: vf-candidate-20260607. (2) Run visual-fallback extraction for all 5 documents: execute Python module src.extraction.cli with args extract-all --db-path compliance.db --run-id vf-candidate-20260607 --visual-fallback. Confirm exit code 0. (3) Run extraction eval for the new candidate by running a small Python script that imports run_extraction_eval from src.eval.extraction_eval_runner and calls run_extraction_eval('compliance.db', source_run_id='vf-candidate-20260607'). Record the returned eval_run_id. (4) Find any prior baseline and packet-aware candidate extraction run_ids: query the extraction_history table in compliance.db for DISTINCT run_id values (excluding vf-candidate-20260607); identify the baseline run and any other candidate runs. (5) For each identified prior run_id that does not already have an extraction_eval eval_run, call run_extraction_eval('compliance.db', source_run_id=<run_id>). (6) Record all eval_run_ids in the task closeout evidence. Done when: compliance.db contains at least two eval_runs rows with eval_type='extraction_eval' (one for vf-candidate-20260607 and one for at least one prior run), each with persisted extraction.macro.f1 eval_metrics rows. Evidence captured via gsd_exec exit_code=0.

## Inputs

- `src/eval/extraction_eval_runner.py`
- `src/extraction/cli.py`
- `src/eval/repository.py`

## Expected Output

- Update the implementation and proof artifacts needed for this task.

## Verification

venv\Scripts\python.exe -m pytest -q tests/test_extraction_eval_runner.py tests/test_eval_repository.py
