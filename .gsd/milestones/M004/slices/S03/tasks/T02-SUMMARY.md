---
id: T02
parent: S03
milestone: M004
key_files:
  - src/extraction/providers.py
  - src/extraction/gemini.py
  - src/extraction/pipeline.py
  - tests/test_extraction_gemini_usage.py
key_decisions:
  - Kept ProviderExtractionResult backward compatible by adding optional usage/provider model fields with defaults rather than changing fake provider constructors.
  - Persisted exactly one text_extraction observation per run/doc after extraction persistence creates the extraction_run parent, surfacing SQLite observation failures visibly rather than silently dropping telemetry.
  - Computed Gemini 2.5 Flash estimated cost only from known input/output token pricing and returned null cost for unknown models or absent token metadata.
duration: 
verification_result: passed
completed_at: 2026-06-03T22:47:06.063Z
blocker_discovered: false
---

# T02: Persisted bounded Gemini text extraction usage observations through the provider and pipeline surfaces.

**Persisted bounded Gemini text extraction usage observations through the provider and pipeline surfaces.**

## What Happened

Extended the extraction provider DTO contract with an optional ProviderUsageMetadata object plus optional provider_model and usage_metadata fields on ProviderExtractionResult, preserving backward compatibility for existing fake providers. Gemini now extracts SDK-like usage metadata from usage_metadata.prompt_token_count, candidates_token_count, and total_token_count for object or dict metadata, attaches the configured model, and computes deterministic Gemini 2.5 Flash estimated cost from bounded token counts while returning null cost for unknown model pricing or absent usage. The extraction pipeline now measures provider-call latency, normalizes and persists extraction records first, then inserts a single text_extraction usage observation keyed by run_id and doc_id with provider/model/status/trace_id/latency/tokens/cost. Observation status is bounded to complete, needs_review, or abstained, with sanitized error_reason values for non-complete outcomes. Added focused mocked Gemini usage tests for complete metadata, absent metadata, unknown-model null cost, malformed JSON with usage metadata, and negative assertions that usage rows do not contain prompt text, page text, raw provider payload fragments, secrets, or local confidential paths.

## Verification

Ran the task verification command via Windows-safe gsd_exec node wrapper: venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_usage.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py. The final run passed all 36 tests, covering provider usage parsing, pipeline observation persistence, missing metadata null behavior, malformed JSON abstention telemetry, and existing extraction pipeline/persistence behavior.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_usage.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py` | 0 | ✅ pass | 15506ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/providers.py`
- `src/extraction/gemini.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_gemini_usage.py`
