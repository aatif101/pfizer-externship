---
id: T04
parent: S04
milestone: M004
key_files:
  - src/extraction/cli.py
  - tests/test_extraction_cli.py
key_decisions:
  - Kept visual fallback CLI wiring opt-in via `--visual-fallback`; default `extract` and `extract-all` runs do not construct a visual provider or change text-only compatibility.
  - Reused the selected text provider name for visual provider construction so the candidate run path stays simple and preserves existing `--provider gemini` behavior.
duration: 
verification_result: passed
completed_at: 2026-06-05T00:34:01.884Z
blocker_discovered: false
---

# T04: Added an explicit `--visual-fallback` CLI run mode that composes Gemini text extraction with the targeted Gemini visual fallback provider only when requested.

**Added an explicit `--visual-fallback` CLI run mode that composes Gemini text extraction with the targeted Gemini visual fallback provider only when requested.**

## What Happened

Updated `src/extraction/cli.py` so both `extract` and `extract-all` accept a `--visual-fallback` flag. Default command behavior remains text-only: the visual provider construction seam is not called unless the flag is present. When enabled, the CLI lazily constructs `GeminiSDFVisualFallbackProvider` alongside the existing Gemini text provider and passes it into the existing pipeline `visual_provider` parameter while preserving explicit `--run-id` propagation. Extended CLI tests with a fake visual provider and an image-backed document fixture to prove the flag invokes the visual stage for eligible missing fields and sends the same run ID to both text and visual providers without leaking extracted values in operator output.

## Verification

Ran the required Windows-native pytest gate through `gsd_exec runtime=node` spawning `venv/Scripts/python.exe`. The final gate passed: 39 tests covering CLI behavior, visual fallback pipeline behavior, Gemini visual provider behavior, extraction usage observations, and eval repository persistence all passed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest -q tests/test_extraction_cli.py tests/test_visual_fallback_pipeline.py tests/test_extraction_gemini_visual.py tests/test_extraction_usage_observations.py tests/test_eval_repository.py` | 0 | ✅ pass — 39 passed | 13341ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/extraction/cli.py`
- `tests/test_extraction_cli.py`
