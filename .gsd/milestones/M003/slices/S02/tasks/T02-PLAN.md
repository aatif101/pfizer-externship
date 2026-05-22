---
estimated_steps: 24
estimated_files: 1
skills_used: []
---

# T02: Add offline tests proving extraction eval metrics, normalization, and persistence via eval repository

Why:
- Metrics credibility depends on explicit, executable definitions: how normalization works, how missing/abstained fields are treated, and how results are persisted without Streamlit duplication.

Do:
- Add `tests/test_extraction_eval_metrics.py` covering:
  - Normalization:
    - whitespace collapse + casefold for string fields
    - date parsing success (e.g. "01-JAN-2024" => "2024-01-01")
    - date parsing fallback when value is non-date (returns cleaned string)
  - Scoring:
    - perfect match => TP and F1=1
    - missing prediction => FN
    - wrong prediction => FP+FN
    - macro average computed across fields with gold instances
  - Persistence integration (SQLite):
    - Create a temp DB, call `init_db`, insert minimal `documents` rows, insert gold labels into `gold_extraction_labels`, insert predictions into `extractions` (using existing extraction repository OR direct inserts with placeholders), then:
      - create an eval run (`eval_type='extraction'`)
      - compute and upsert metrics:
        - per-field metrics as scoped metrics: `scope_type='field'`, `scope_id=<field_name>` for `precision`, `recall`, `f1`, and counts `tp/fp/fn` if desired
        - global macro-avg metrics as unscoped metrics
      - verify `list_eval_metrics()` returns expected rows and that repeated upserts do not duplicate.
- Keep tests fully offline, no `.gsd/` reads.

Done when:
- `venv\\Scripts\\python.exe -m pytest tests/test_extraction_eval_metrics.py -q` passes.
- The test suite makes the metric definitions unambiguous for future slices (S04 UI, S03 retrieval/RAG metrics).

## Inputs

- `src/eval/extraction_metrics.py`
- `src/eval/repository.py`
- `src/db/schema.py`
- `tests/conftest.py`

## Expected Output

- `tests/test_extraction_eval_metrics.py`

## Verification

venv\\Scripts\\python.exe -m pytest tests/test_extraction_eval_metrics.py -q

## Observability Impact

Adds regression protection: failing metric definitions will be caught by pytest before dashboard/UI wiring.
