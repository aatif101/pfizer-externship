---
id: T02
parent: S04
milestone: M004
key_files:
  - src/extraction/pipeline.py
  - tests/test_visual_fallback_pipeline.py
key_decisions:
  - Visual fallback is implemented as a post-text, pre-persist stage that only loads image bytes when configured and eligible fields exist.
  - Visual candidates use the existing text-grounded normalization and span guard path before merge arbitration.
  - Merge arbitration upgrades ABSTAINED fields with valid non-abstained candidates and upgrades NEEDS_REVIEW only with PENDING candidates; PENDING text fields are never replaced.
  - Visual fallback observations persist only bounded stage telemetry and sanitized reason/error codes.
duration: 
verification_result: passed
completed_at: 2026-06-05T00:25:33.323Z
blocker_discovered: false
---

# T02: Wired targeted visual fallback into the extraction pipeline with conservative merge arbitration and bounded visual-stage usage observations.

**Wired targeted visual fallback into the extraction pipeline with conservative merge arbitration and bounded visual-stage usage observations.**

## What Happened

Extended `extract_document()` with an optional `visual_provider` parameter while preserving text extraction as the primary path. The pipeline now normalizes text fields first, plans visual fallback only for abstained or needs-review fields, reloads stored page image bytes only when a visual provider is configured and eligible fields exist, normalizes visual candidates through the same grounded field validation guards, and merges only safe improvements. Merged records are persisted through the existing extraction repository so latest rows and run-scoped history stay compatible. Added visual_fallback usage observations for skipped, complete, abstained, and provider-error outcomes with sanitized reason codes/error classes and bounded token/latency/cost/model/trace metadata only. Extended `tests/test_visual_fallback_pipeline.py` with provider-free integration tests covering abstained-field fill, good text preservation, missing-image skip, visual telemetry, provider exception safety, and non-stronger candidate abstention.

## Verification

Ran the task verification suite with Windows-native Python via `gsd_exec` node spawning `venv/Scripts/python.exe`. All targeted visual fallback, extraction pipeline, extraction persistence, and extraction usage observation tests passed: 48 passed in 15.57s.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py tests/test_extraction_usage_observations.py` | 0 | ✅ pass | 17147ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/pipeline.py`
- `tests/test_visual_fallback_pipeline.py`
