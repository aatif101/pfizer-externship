---
estimated_steps: 5
estimated_files: 4
skills_used: []
---

# T03: Wire shared run identity into CLI and eval reads

Expected executor skills for task plan frontmatter: tdd, verify-before-complete.

Why: S02 and S05 need one extraction run to span multiple documents. The pipeline already accepts a `run_id`, but the CLI currently generates one run per document and the extraction eval repository reads only latest-write predictions.

Do: In `src/extraction/cli.py`, add optional `--run-id` to both `extract` and `extract-all`. Pass it through `_extract_one()` to `run_extraction()`. For `extract-all`, the same supplied run id must be used for every ingested document so `list_compliance_records_for_run(db_path, run_id)` can return all documents in that candidate/baseline run. Keep CLI output sanitized: echo run ids and counts only, not field values, page text, provider payloads, prompts, file paths, images, or secrets. Update CLI tests to assert an explicit run id reaches the fake provider and persisted history for both single-doc and batch commands.

In `src/eval/repository.py`, add `list_predicted_extractions_for_run(db_path, run_id)` returning rows with `doc_id`, `field_name`, `normalized_value`, and `review_state` from `extraction_history`, ordered by `doc_id` and `field_name`. Keep the existing latest `list_predicted_extractions()` behavior unchanged if it already exists. Add tests in `tests/test_eval_repository.py` or a focused extraction-history eval test that insert documents and run-scoped records through `upsert_extraction_record()`, then assert the helper reads only the selected run and does not fall back to latest rows.

Done when: Operators can intentionally create a shared baseline/candidate extraction run through the CLI, and evaluation code can compare predictions for a named run without latest-write ambiguity.

## Inputs

- `src/extraction/cli.py`
- `src/extraction/pipeline.py`
- `src/extraction/repository.py`
- `src/eval/repository.py`
- `tests/test_extraction_cli.py`
- `tests/test_eval_repository.py`
- `tests/test_extraction_persistence.py`

## Expected Output

- `src/extraction/cli.py`
- `src/eval/repository.py`
- `tests/test_extraction_cli.py`
- `tests/test_eval_repository.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_cli.py tests/test_eval_repository.py tests/test_extraction_persistence.py

## Observability Impact

Improves operator-visible diagnostics by allowing stable run IDs in CLI output and downstream DB summaries. Negative tests should cover empty/no-doc CLI behavior, provider failure preserving sanitized output, and selected-run eval reads ignoring overwritten latest rows.
