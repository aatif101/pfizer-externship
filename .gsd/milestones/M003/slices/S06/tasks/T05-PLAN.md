---
estimated_steps: 11
estimated_files: 12
skills_used: []
---

# T05: Run integrated R007 regression proof

---
estimated_steps: 4
estimated_files: 0
skills_used:
  - verify-before-complete
---

Why: The slice touches schema, repository, metric semantics, runner integration, and dashboard display. A final integrated test pass is needed before claiming R007 coverage has improved.

Do: Run the focused eval/dashboard regression suite with the project virtualenv. If failures expose missing contracts, fix the responsible implementation or tests in the earlier task files rather than broadening scope. Do not use `.gsd/` or gitignored artifacts as test inputs.

Done when: the focused pytest command passes and covers schema/repository, optional metric aggregation, retrieval runner integration, extraction metric regression, and Eval tab display.

Requirement Impact (Q4): Verifies R007 and preserves R008 dashboard/provider-free boundary.
Negative Tests (Q7): The included tests must cover absent optional services/data and missing DB/table behavior.

## Inputs

- `src/db/schema.py`
- `src/eval/repository.py`
- `src/eval/operational_metrics.py`
- `src/eval/retrieval_eval_runner.py`
- `src/eval/extraction_metrics.py`
- `src/dashboard/eval.py`
- `tests/test_eval_db_schema.py`
- `tests/test_eval_repository.py`
- `tests/test_retrieval_eval_optional_metrics.py`
- `tests/test_retrieval_eval_runner.py`
- `tests/test_extraction_eval_metrics.py`
- `tests/test_dashboard_eval_tab.py`

## Expected Output

- Update the implementation and proof artifacts needed for this task.

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_eval_db_schema.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py tests/test_extraction_eval_metrics.py tests/test_dashboard_eval_tab.py

## Observability Impact

No new code; produces executable evidence that optional metrics are visible when present and deterministic no-ops when absent.
