---
id: T03
parent: S04
milestone: M004
key_files:
  - src/extraction/gemini.py
  - tests/test_extraction_gemini_visual.py
  - tests/test_extraction_gemini_usage.py
key_decisions:
  - Kept visual Gemini fallback as a separate provider class/path rather than modifying text extraction behavior.
  - Used lazy `Part` import plus injectable fake part factory so unit tests remain offline-safe and credential-free.
  - Filtered provider-returned visual fields to the eligible request allowlist to preserve targeted fallback semantics.
duration: 
verification_result: passed
completed_at: 2026-06-05T00:30:00.249Z
blocker_discovered: false
---

# T03: Implemented a lazy Gemini image-part visual fallback provider with bounded prompts, requested-field filtering, and usage metadata reuse.

**Implemented a lazy Gemini image-part visual fallback provider with bounded prompts, requested-field filtering, and usage metadata reuse.**

## What Happened

Added `GeminiSDFVisualFallbackProvider` in `src/extraction/gemini.py` as a separate visual fallback implementation while preserving the existing `GeminiSDFExtractionProvider.extract_fields()` text behavior. The visual path builds mixed Gemini contents from a bounded text prompt plus `Part.from_bytes(data=page.image_blob, mime_type="image/png")` image parts, imports the Google SDK Part type lazily, and supports a fake part factory for offline unit tests. The prompt includes only document/run identifiers, requested field names, selected page numbers, generic eligibility reason codes, and extraction instructions; it excludes raw page text, local paths, provider payloads, prompts in persisted outputs, PDFs, secrets, and image bytes. Visual responses reuse the existing retry, response text, JSON parsing, provider field parsing, malformed-result handling, usage metadata extraction, and Gemini Flash cost estimation helpers. Returned visual fields are filtered to the eligible request allowlist so unrequested fields cannot flow through the targeted fallback seam. Added `tests/test_extraction_gemini_visual.py` with fake Gemini client/response helpers proving image parts are constructed and sent, prompts are bounded to requested fields, unrequested fields are filtered, malformed JSON becomes safe requested-field abstentions with usage metadata, and provider errors are sanitized. Updated the legacy Gemini usage tests to query `stage="text_extraction"` explicitly because T02 introduced a separate visual fallback usage observation row even when visual fallback is skipped.

## Verification

Ran the task verification command via Windows-safe `gsd_exec` node spawning `venv/Scripts/python.exe`: `venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_visual.py tests/test_extraction_gemini_usage.py`, which passed 10 tests. Also ran the existing visual fallback pipeline guardrail suite `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py`, which passed 11 tests and confirmed the new provider changes did not break the S04 stage behavior.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_visual.py tests/test_extraction_gemini_usage.py` | 0 | ✅ pass (10 passed) | 4639ms |
| 2 | `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py` | 0 | ✅ pass (11 passed) | 4906ms |

## Deviations

Adjusted existing `tests/test_extraction_gemini_usage.py` assertions to filter for `text_extraction` observations, preserving their original text-usage intent after T02 added separate visual fallback observation rows.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/gemini.py`
- `tests/test_extraction_gemini_visual.py`
- `tests/test_extraction_gemini_usage.py`
