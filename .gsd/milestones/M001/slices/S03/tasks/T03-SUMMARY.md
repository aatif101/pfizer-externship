---
id: T03
parent: S03
milestone: M001
key_files:
  - pyproject.toml
  - src/config.py
  - src/extraction/providers.py
  - src/extraction/gemini.py
  - src/extraction/pipeline.py
  - tests/test_extraction_provider_gemini.py
  - tests/test_extraction_pipeline.py
key_decisions:
  - Gemini provider construction is lazy and credential-checked at provider instantiation/call boundaries so tests and app imports stay offline-safe.
  - Malformed Gemini output is represented as deterministic six-field abstention payloads rather than leaking raw response text or crashing the pipeline.
  - Retry exhaustion reports sanitized provider/model/run/doc/error-class diagnostics only, preserving redaction boundaries for API keys and page text.
duration: ""
verification_result: passed
completed_at: 2026-05-20T17:29:48.252Z
blocker_discovered: false
---

# T03: Added an offline-safe Gemini SDF extraction adapter with typed sanitized provider failures, bounded retries, and deterministic abstentions for malformed output.

**Added an offline-safe Gemini SDF extraction adapter with typed sanitized provider failures, bounded retries, and deterministic abstentions for malformed output.**

## What Happened

Added `google-genai` as an optional live-provider dependency and extended settings with `gemini_api_key`, `gemini_model`, and `extraction_low_confidence_threshold` defaults that do not require credentials during import. Implemented `src/extraction/gemini.py` as a lazy Gemini provider conforming to the T02 provider protocol: it builds a structured six-field JSON prompt with 0-indexed page references and short verbatim spans, calls `models.generate_content` only when extraction is invoked, parses JSON-compatible provider output into typed provider DTOs, and turns malformed shape/JSON into six deterministic abstention payloads. Added typed provider/config/validation errors in `src/extraction/providers.py`; missing `GEMINI_API_KEY` raises `ExtractionConfigurationError`, retryable 408/429/5xx/timeout-style failures use bounded tenacity retries, and exhausted provider failures are wrapped in sanitized `ExtractionProviderError` messages that expose provider/model/run/doc/error class without API keys, page text, raw model response, or image blobs. Updated pipeline handling to preserve provider diagnostics, apply the configurable low-confidence threshold as needs-review state, and continue validating source spans/pages before persistence. Added mocked Gemini tests for missing credentials, structured parsing, malformed JSON abstentions, bounded retry wrapping/redaction, low-confidence review state, and span mismatch grounding.

## Verification

Re-ran the task verification command after the artifact failure: `venv/Scripts/python.exe -m pytest tests/test_app.py tests/test_extraction_pipeline.py tests/test_extraction_provider_gemini.py -q`. It passed offline with 16 tests, confirming app import remains credential-free and Gemini/pipeline failure paths are deterministic without network access. Prior full-regression evidence for this implementation also passed (`venv/Scripts/python.exe -m pytest -q`, 36 passed at the T03 point), and later S03 closeout regression passed with 65 tests after T04.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_app.py tests/test_extraction_pipeline.py tests/test_extraction_provider_gemini.py -q` | 0 | ✅ pass (16 passed) | 8699ms |

## Deviations

None.

## Known Issues

Default pytest emits existing third-party deprecation warnings from installed dependencies during full regression; no task-specific failures remain.

## Files Created/Modified

- `pyproject.toml`
- `src/config.py`
- `src/extraction/providers.py`
- `src/extraction/gemini.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_provider_gemini.py`
- `tests/test_extraction_pipeline.py`
