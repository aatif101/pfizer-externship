---
estimated_steps: 28
estimated_files: 2
skills_used: []
---

# T01: Implement extraction F1 metric computation with normalization and SQLite data access

Why:
- M003 needs credible, repeatable extraction quality metrics. Field-level F1 is the simplest evaluator-friendly baseline, but it must be deterministic and robust to missing values.

Do:
- Add a new evaluation module under `src/eval/extraction_metrics.py` (or similar) implementing:
  - `normalize_extracted_value(field_name: str, value: str | None) -> str | None` with deterministic rules:
    - `None` stays `None`
    - trim whitespace; collapse internal whitespace to single spaces
    - casefold (lower) for general string fields
    - for date-like fields (manufacturing/effective/revision/expiry), attempt best-effort parsing into ISO `YYYY-MM-DD` (using `python-dateutil` if available) and fall back to cleaned string when parsing fails
  - `compute_extraction_field_scores(gold_rows, pred_rows) -> {field_name: {tp, fp, fn, precision, recall, f1}}` using exact match on normalized values.
    - Treat ABSTAIN / missing prediction as `None`.
    - Only evaluate fields that exist in gold labels for a given doc_id.
    - Define the classification rules per (doc_id, field_name):
      - If gold_norm is not None and pred_norm equals gold_norm => TP
      - If gold_norm is not None and pred_norm is None => FN
      - If gold_norm is not None and pred_norm is not None but differs => FP+FN (counts as both: a wrong answer and a missed correct answer)
      - If gold_norm is None (should be rare) skip (do not count)
  - `compute_macro_averages(per_field_scores)` computing macro-avg precision/recall/f1 across fields with at least one gold instance.
- Extend `src/eval/repository.py` with minimal additional read helpers needed for this slice (still provider-free, parameterized SQL):
  - `list_predicted_extractions(db_path: str) -> list[dict]` returning `doc_id, field_name, normalized_value, review_state` from `extractions`.
- Keep responsibilities clean:
  - repository reads SQLite and returns rows
  - metrics module normalizes + computes counts/scores
  - persistence uses existing `create_eval_run`, `upsert_eval_metric`, `mark_eval_run_complete/error`.

Done when:
- A single pure function can compute per-field TP/FP/FN + precision/recall/F1 from provided row lists.
- The metric computation is deterministic and documented in docstrings (no reliance on dict ordering).
- No LLM/provider imports are introduced in `src/eval/*`.

## Inputs

- `src/eval/repository.py`
- `src/db/schema.py`
- `src/extraction/repository.py`

## Expected Output

- `src/eval/extraction_metrics.py`
- `src/eval/repository.py`

## Verification

venv\\Scripts\\python.exe -m pytest tests/test_extraction_eval_metrics.py -q

## Observability Impact

None (offline metric computation only; persistence uses existing eval_runs/eval_metrics tables).
