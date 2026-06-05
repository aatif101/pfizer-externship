# S03: Gemini extraction usage observations

**Goal:** Persist bounded Gemini extraction usage observations for text extraction calls and expose provider-free aggregate token and estimated-cost metrics keyed by extraction run identity, without storing raw prompts, page text, provider payloads, images, PDFs, secrets, or local confidential paths.
**Demo:** A mocked Gemini extraction persists bounded token and estimated-cost observations and exposes aggregate eval metrics without storing raw prompts or confidential data.

## Must-Haves

- `init_db()` creates an additive bounded `extraction_usage_observations` table and indexes it by extraction run, document, stage, and status.
- Repository helpers can insert and list multiple text extraction usage observations for the same run and document, reject malformed numeric values, and keep the schema free of forbidden raw/confidential columns.
- A mocked Gemini extraction response with SDK-like usage metadata results in exactly one bounded usage observation for the extraction run/document/stage/model.
- Extraction usage aggregation writes deterministic `eval_metrics` rows for cost, token, and latency families for a selected extraction run, and emits no misleading zero metrics for absent values.
- All verification uses Windows-native `venv/Scripts/python.exe -m pytest ...` commands only.

## Proof Level

- This slice proves: Contract and integration proof. No live Gemini runtime or human UAT required; tests use mocked provider/client responses and SQLite fixtures to exercise the repository, Gemini adapter, extraction pipeline, and eval metric boundary.

## Integration Closure

Consumes S01 run identity (`SDFExtractionRecord.run_id`, `extraction_runs`, `extraction_history`) and the existing Gemini extraction provider boundary. Introduces usage DTO extraction, SQLite persistence, and eval metric aggregation for text-stage calls. S04 still needs to reuse the same observation contract for visual fallback calls; S05 still needs real five-document comparison/UAT.

## Verification

- Adds a provider-free inspection surface for extraction usage: `extraction_usage_observations` rows keyed by run_id/doc_id/stage/model/status plus aggregate `eval_metrics` rows. Failure visibility is bounded to status and sanitized reason/error class; no raw prompts, page text, provider payloads, image bytes, PDFs, secrets, or local confidential paths are stored.

## Tasks

- [x] **T01: Add bounded extraction usage observation repository** `est:1h 15m`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/db/schema.py`, `src/eval/repository.py`, `tests/test_extraction_usage_observations.py`, `tests/test_eval_db_schema.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_usage_observations.py tests/test_eval_db_schema.py

- [x] **T02: Persist mocked Gemini text extraction usage** `est:1h 45m`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/extraction/providers.py`, `src/extraction/gemini.py`, `src/extraction/pipeline.py`, `tests/test_extraction_gemini_usage.py`, `tests/test_extraction_pipeline.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_usage.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py

- [x] **T03: Expose extraction usage aggregate eval metrics** `est:1h 15m`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `src/eval/operational_metrics.py`, `src/eval/extraction_usage_eval.py`, `src/eval/repository.py`, `tests/test_extraction_usage_eval_metrics.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_usage_eval_metrics.py tests/test_retrieval_eval_optional_metrics.py tests/test_eval_repository.py

## Files Likely Touched

- src/db/schema.py
- src/eval/repository.py
- tests/test_extraction_usage_observations.py
- tests/test_eval_db_schema.py
- src/extraction/providers.py
- src/extraction/gemini.py
- src/extraction/pipeline.py
- tests/test_extraction_gemini_usage.py
- tests/test_extraction_pipeline.py
- src/eval/operational_metrics.py
- src/eval/extraction_usage_eval.py
- tests/test_extraction_usage_eval_metrics.py
