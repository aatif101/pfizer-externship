---
estimated_steps: 12
estimated_files: 2
skills_used: []
---

# T01: Add provider-free retrieval eval metrics (recall@k and page-level citation accuracy) with gold query/target support

Why: S03 needs deterministic, provider-free retrieval metrics to satisfy R007 and to power the Streamlit Eval tab run history.

Do:
- Create `src/eval/retrieval_metrics.py`.
- Define deterministic helpers:
  - `compute_retrieval_recall_at_k(gold_targets_by_query, retrieved_hits_by_query, k)` returning recall@k at query-level and macro average.
  - `compute_page_level_citation_accuracy(gold_targets_by_query, cited_pages_by_query)` (initial definition: a citation is correct if any cited (doc_id,page_num) matches any gold target for that query).
- Keep evaluation boundaries consistent with M002 retrieval DTOs: treat retrieval evidence as authoritative, operate on (doc_id,page_num,score) tuples only; do not require raw page text.
- Define explicit behavior for empty gold sets and missing retrieved hits: return 0.0 metrics and per-query breakdowns without raising.
- Add docstrings describing metric definitions and limitations (page-level match, not span-level).

Done-when:
- Module exists, is importable, and can compute stable recall@5/10 + citation accuracy from in-memory dict inputs.
- Unit tests cover: perfect recall, partial recall, empty gold, extra retrieved hits, duplicate hits, and citation accuracy match/no-match.

## Inputs

- `src/eval/extraction_metrics.py`

## Expected Output

- `src/eval/retrieval_metrics.py`
- `tests/test_retrieval_eval_metrics.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_metrics.py -q

## Observability Impact

None at runtime; establishes deterministic metric definitions and tests that will be used by the eval runner.
