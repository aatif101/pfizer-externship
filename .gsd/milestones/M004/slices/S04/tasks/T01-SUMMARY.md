---
id: T01
parent: S04
milestone: M004
key_files:
  - src/extraction/providers.py
  - src/extraction/pipeline.py
  - tests/test_visual_fallback_pipeline.py
key_decisions:
  - Kept visual fallback behind a separate optional `SDFVisualFallbackProvider` protocol instead of modifying the existing text extraction provider protocol.
  - Represented eligibility with bounded generic reason codes only (`field_abstained`, `field_needs_review`, skip codes), excluding field values, spans, prompts, provider payloads, paths, page text, and image bytes from reason strings.
duration: 
verification_result: passed
completed_at: 2026-06-05T00:20:53.223Z
blocker_discovered: false
---

# T01: Added a targeted visual fallback provider contract and deterministic eligibility/request-planning helpers for suspicious SDF fields.

**Added a targeted visual fallback provider contract and deterministic eligibility/request-planning helpers for suspicious SDF fields.**

## What Happened

Implemented a separate optional visual fallback seam in `src/extraction/providers.py` so existing `SDFExtractionProvider` fakes and adapters remain unchanged. Added bounded visual DTOs for eligible field names, selected image-backed pages, generic reason codes, skip/ready request plans, and provider invocation outcomes. Added pure helper functions in `src/extraction/pipeline.py` to compute visual fallback eligibility from normalized `ExtractedField` objects, build sanitized request plans, and avoid provider calls when no eligible fields, images, or configured visual provider are available. Created `tests/test_visual_fallback_pipeline.py` with deterministic coverage for ABSTAINED and NEEDS_REVIEW eligibility, PENDING exclusion, bounded reason codes, image-backed page selection, skip reason codes, and no provider invocation on an empty eligible set.

## Verification

Ran the task verification command via Windows-native `venv/Scripts/python.exe` spawned from `gsd_exec runtime=node`: `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py`. The suite passed with 25 tests.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py` | 0 | ✅ pass (25 passed) | 10755ms |

## Deviations

None.

## Known Issues

Visual fallback is not yet orchestrated into `extract_document()` persistence/usage observations; that remains for later S04 tasks as planned.

## Files Created/Modified

- `src/extraction/providers.py`
- `src/extraction/pipeline.py`
- `tests/test_visual_fallback_pipeline.py`
