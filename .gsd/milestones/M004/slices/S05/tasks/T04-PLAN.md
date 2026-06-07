---
estimated_steps: 1
estimated_files: 5
skills_used: []
---

# T04: Git artifact check and full test suite closeout

Why: R016 requires no confidential files in git. R017 requires Windows-native verification only. The full test suite must pass with all 297 prior tests plus the 6 new S05 tests. Do: (1) Run git status --short via PowerShell (using gsd_exec runtime=node spawning git) and confirm the output contains NO entries for compliance.db, *.db, .env, SDFs/, local_data/, private/, *.pdf, *.png, *.jpg, *.jpeg, or *.webp. Flag any unexpected tracked confidential file as a blocker before proceeding. (2) Run the full pytest suite: venv\Scripts\python.exe -m pytest -q tests/ via gsd_exec runtime=node and confirm all tests pass with exit code 0 and count >=303. Done when: git status shows no confidential tracked files AND pytest reports all tests passing.

## Inputs

- `tests/test_extraction_eval_runner.py`
- `tests/test_eval_repository.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_visual_fallback_pipeline.py`

## Expected Output

- Update the implementation and proof artifacts needed for this task.

## Verification

venv\Scripts\python.exe -m pytest -q tests/
