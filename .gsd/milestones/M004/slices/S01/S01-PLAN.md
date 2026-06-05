# S01: Run scoped extraction history

**Goal:** Add additive run-scoped extraction and compliance history so two runs for the same document can be persisted and queried independently while existing latest-write extraction repository behavior remains unchanged.
**Demo:** A test can persist two extraction runs for the same document and query both independently while existing latest-write repository behavior still works.

## Must-Haves

- R011 primary proof: a test persists two `SDFExtractionRecord` values for the same `doc_id` with different `run_id` values and can reconstruct each run independently.
- Latest-write compatibility remains intact: `get_extraction_record()` and `list_compliance_records()` still return the newest compatibility rows and existing extraction persistence tests continue to pass.
- Run selector prerequisites exist for S02: repository exposes stable run summaries and run-scoped compliance rows without importing providers, dashboard code, or confidential artifacts.
- Future comparison prerequisite exists for S05: run-specific predicted extraction rows can be listed without reading latest-write tables.
- R016/R017 constraints hold: no raw prompts, page text, provider payloads, images, secrets, PDFs, or local DB artifacts are added to schema outputs, diagnostics, tests, or plans; verification commands are Windows-native.

## Proof Level

- This slice proves: Contract and integration proof. Real runtime required: no live provider required; tests use deterministic SQLite fixtures and fake providers only. Human/UAT required: no. Verification class: repository and CLI integration tests using `venv/Scripts/python.exe -m pytest`.

## Integration Closure

Upstream surfaces consumed: `src/db/schema.py`, `src/extraction/models.py`, `src/extraction/pipeline.py`, existing extraction repository tests, CLI fake-provider tests, and eval repository patterns. New wiring introduced: `upsert_extraction_record()` writes history in the same transaction as current latest rows when `record.run_id` is present; CLI commands can pass an explicit shared `--run-id`; eval repository can read predictions for a selected extraction run. Remaining milestone work: S02 dashboard selector, S03 usage observations, S04 visual fallback, and S05 real five-document comparison.

## Verification

- Adds DB inspection surfaces for extraction run state: `extraction_runs`, `extraction_history`, `compliance_record_history`, `list_extraction_run_summaries()`, `get_extraction_record_for_run()`, and `list_compliance_records_for_run()`. Failure visibility is bounded to run id, document count, field count, timestamps, status, trace id, review state, risk fields, and sanitized repository exceptions; no raw document text, image bytes, provider payloads, prompts, secrets, or local confidential artifact paths are surfaced.

## Tasks

- [x] **T01: Add additive run history schema** `est:1h`
  Expected executor skills for task plan frontmatter: tdd, verify-before-complete.
  - Files: `src/db/schema.py`, `tests/test_extraction_run_history_schema.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_run_history_schema.py tests/test_db.py

- [x] **T02: Persist and query extraction run history** `est:2h`
  Expected executor skills for task plan frontmatter: tdd, verify-before-complete.
  - Files: `src/extraction/repository.py`, `tests/test_extraction_persistence.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_persistence.py tests/test_extraction_pipeline.py

- [x] **T03: Wire shared run identity into CLI and eval reads** `est:1.5h`
  Expected executor skills for task plan frontmatter: tdd, verify-before-complete.
  - Files: `src/extraction/cli.py`, `src/eval/repository.py`, `tests/test_extraction_cli.py`, `tests/test_eval_repository.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_cli.py tests/test_eval_repository.py tests/test_extraction_persistence.py

## Files Likely Touched

- src/db/schema.py
- tests/test_extraction_run_history_schema.py
- src/extraction/repository.py
- tests/test_extraction_persistence.py
- src/extraction/cli.py
- src/eval/repository.py
- tests/test_extraction_cli.py
- tests/test_eval_repository.py
