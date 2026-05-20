# S03: Baseline extraction pipeline

**Goal:** Running baseline extraction against ingested sample document pages produces strict six-field SDF extraction records with source page/span evidence or explicit abstentions, conservative compliance risk metadata, run/trace metadata, and dashboard-ready compliance rows in SQLite without requiring Langfuse credentials for success.
**Demo:** Running extraction against sample PDFs produces structured metadata rows with page/source evidence or explicit abstentions.

## Must-Haves

- `SDFExtractionRecord` persists and reconstructs document-level `risk_reason` and `age_days` in addition to existing risk/status metadata.
- Pure risk tests cover expired, missing/ambiguous dates, green, amber, and red age thresholds with injectable `today`.
- A fake-provider pipeline integration test seeds a temp SQLite DB with realistic page text, runs extraction for one doc, and asserts six extraction rows plus one populated `compliance_records` row with source evidence, run metadata, risk fields, and deterministic dashboard values.
- Provider failure tests cover missing Gemini credentials, malformed provider output, missing source spans, low confidence, missing pages/page text, and abstention synthesis without live network calls.
- CLI tests or executable invocations cover `extract` and `extract-all` entrypoints against a temp/demo DB with mocked provider behavior.
- Full regression remains green with `venv/Scripts/python.exe -m pytest -q`.

## Proof Level

- This slice proves: Integration proof. Default verification must be deterministic and offline using fake/mocked providers. A live Gemini smoke path may be added, but it must be opt-in and skipped without `GEMINI_API_KEY`. Human/UAT is not required for S03.

## Integration Closure

Consumes the S02 extraction model/repository contract and Phase 1 `documents`/`pages` SQLite store. Introduces runtime extraction orchestration, provider abstraction, Gemini adapter, risk computation, CLI entrypoints, and persistence of risk/run metadata. Leaves Streamlit Compliance tab rendering and source-page UI links to S04.

## Verification

- Extraction runs should expose non-secret run IDs, optional trace IDs, document IDs, page counts, provider/error classes, review/abstention states, and persisted compliance rows. Logs/traces must not include API keys, full page text, provider raw responses, or image blobs. Missing Langfuse credentials must be non-fatal.

## Tasks

- [x] **T01: Compute and persist document risk metadata** `est:1h 30m`
  ---
  estimated_steps: 7
  estimated_files: 4
  skills_used:
    - tdd
    - verify-before-complete
  ---
  - Files: `src/extraction/models.py`, `src/extraction/repository.py`, `src/extraction/risk.py`, `tests/test_extraction_risk.py`, `tests/test_extraction_persistence.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_persistence.py tests/test_extraction_risk.py -q

- [x] **T02: Load ingested pages and prove fake-provider pipeline persistence** `est:2h`
  ---
  estimated_steps: 8
  estimated_files: 5
  skills_used:
    - tdd
    - observability
    - verify-before-complete
  ---
  - Files: `src/db/queries.py`, `src/extraction/providers.py`, `src/extraction/pipeline.py`, `tests/test_extraction_pipeline.py`, `src/extraction/__init__.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_extraction_risk.py tests/test_extraction_pipeline.py -q

- [x] **T03: Add Gemini adapter and robust provider failure handling** `est:2h`
  ---
  estimated_steps: 9
  estimated_files: 6
  skills_used:
    - tdd
    - observability
    - security-review
    - verify-before-complete
  ---
  - Files: `pyproject.toml`, `src/config.py`, `src/extraction/providers.py`, `src/extraction/gemini.py`, `src/extraction/pipeline.py`, `tests/test_extraction_provider_gemini.py`, `tests/test_extraction_pipeline.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_app.py tests/test_extraction_pipeline.py tests/test_extraction_provider_gemini.py -q

- [x] **T04: Wire extraction CLI and final regression proof** `est:1h 30m`
  ---
  estimated_steps: 8
  estimated_files: 4
  skills_used:
    - tdd
    - observability
    - verify-before-complete
  ---
  - Files: `src/extraction/cli.py`, `src/extraction/pipeline.py`, `src/extraction/providers.py`, `tests/test_extraction_cli.py`, `tests/test_extraction_pipeline.py`
  - Verify: venv/Scripts/python.exe -m pytest -q

## Files Likely Touched

- src/extraction/models.py
- src/extraction/repository.py
- src/extraction/risk.py
- tests/test_extraction_risk.py
- tests/test_extraction_persistence.py
- src/db/queries.py
- src/extraction/providers.py
- src/extraction/pipeline.py
- tests/test_extraction_pipeline.py
- src/extraction/__init__.py
- pyproject.toml
- src/config.py
- src/extraction/gemini.py
- tests/test_extraction_provider_gemini.py
- src/extraction/cli.py
- tests/test_extraction_cli.py
