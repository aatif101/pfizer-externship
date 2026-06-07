---
id: S04
parent: M004
milestone: M004
provides:
  - Targeted visual fallback stage that fills only eligible abstained/needs-review fields from stored page images.
  - Conservative merge arbitration preserving good PENDING text-grounded values.
  - Bounded visual_fallback usage observations for complete, skipped, and error paths.
  - Opt-in --visual-fallback CLI flag composing Gemini text + visual providers for candidate runs.
  - Gemini image-part visual provider with offline-testable fake part factory injection.
requires:
  - slice: S01
    provides: Run-scoped extraction history and stable run summary metadata
  - slice: S03
    provides: Bounded extraction usage observation contract and aggregate metric names
affects:
  - S05
key_files:
  - src/extraction/providers.py
  - src/extraction/pipeline.py
  - src/extraction/gemini.py
  - src/extraction/cli.py
  - tests/test_visual_fallback_pipeline.py
  - tests/test_extraction_gemini_visual.py
  - tests/test_extraction_gemini_usage.py
  - tests/test_extraction_cli.py
key_decisions:
  - Kept visual fallback behind a separate optional SDFVisualFallbackProvider protocol rather than modifying the existing text extraction provider.
  - Conservative merge arbitration: ABSTAINED → any valid non-abstained candidate; NEEDS_REVIEW → PENDING candidate only; PENDING text values are never replaced.
  - Bounded visual_fallback stage usage observations persist only sanitized reason/error codes — no raw prompts, page text, images, paths, or provider payloads.
  - Lazy Part import plus injectable fake part factory keeps all Gemini visual provider tests offline-safe and credential-free.
  - CLI opt-in via --visual-fallback flag; default extract and extract-all runs construct no visual provider and retain full text-only compatibility.
patterns_established:
  - Post-text, pre-persist visual fallback stage: activates only when provider is configured and eligible fields exist, then merges conservatively before persistence.
  - Eligibility expressed as bounded reason codes only (field_abstained, field_needs_review, skip variants) — no field values or spans in telemetry.
  - Fake part factory injection pattern for offline Gemini image-part tests without API credentials.
observability_surfaces:
  - list_extraction_usage_observations() returns visual_fallback stage rows with bounded status and sanitized reason codes (not_configured, no_eligible_fields, missing_page_images, provider error class).
  - Extraction run history via run-scoped repository surfaces which runs used visual fallback and their field-level outcomes.
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-06-07T23:07:44.749Z
blocker_discovered: false
---

# S04: Targeted visual fallback extraction

**Added targeted visual fallback extraction that fills only eligible missing/suspicious SDF fields from stored page images while preserving all good grounded text values and recording bounded usage observations.**

## What Happened

S04 delivered targeted visual fallback extraction across four tasks.

**T01** established the contract and eligibility layer. A new `SDFVisualFallbackProvider` protocol was added to `src/extraction/providers.py` alongside deterministic eligibility helpers in `src/extraction/pipeline.py`. Eligibility is expressed in bounded reason codes only (`field_abstained`, `field_needs_review`, skip codes) with no field values, spans, paths, or page text leaking into reason strings. 25 provider-free tests verified the contract.

**T02** wired fallback arbitration and visual observations into `extract_document()`. Visual fallback runs as a post-text, pre-persist pipeline stage that activates only when a provider is configured and eligible fields exist. Merge arbitration is conservative: ABSTAINED fields accept any valid non-abstained candidate; NEEDS_REVIEW fields accept only PENDING candidates; PENDING text-grounded fields are never replaced. Bounded `stage='visual_fallback'` usage observations persist complete, skipped, and error paths without raw prompts, page text, provider payloads, image bytes, or local paths. 48 tests covering pipeline, persistence, and usage observation suites passed.

**T03** implemented the Gemini image-part visual provider in `src/extraction/gemini.py`. A lazy `Part` import plus an injectable fake-part factory keeps all tests offline-safe and credential-free. The provider filters its output to the eligible request allowlist to preserve targeted fallback semantics and reuses the existing usage-metadata path. Malformed responses produce safe abstentions. 10 provider-specific tests passed.

**T04** exposed the opt-in path via `--visual-fallback` in `src/extraction/cli.py`. Default `extract` and `extract-all` runs construct no visual provider and retain full text-only compatibility. A 39-test gate covering CLI, pipeline, Gemini visual provider, usage observations, and eval repository all passed.

Final slice-level verification ran all 8 test files together (58 unique tests) in 18.99s with exit code 0.

## Verification

Ran `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py tests/test_extraction_usage_observations.py tests/test_extraction_gemini_visual.py tests/test_extraction_gemini_usage.py tests/test_extraction_cli.py tests/test_eval_repository.py` via `gsd_exec runtime=node` (exec id: 2539a210-c385-4bdc-9634-3a5e992e1106). Result: **58 passed in 18.99s**, exit code 0. No failures, no warnings. All Windows-native verification commands — no /bin/bash or runtime=bash used.

## Requirements Advanced

None.

## Requirements Validated

- R014 — Provider-free eligibility and merge arbitration tests in test_visual_fallback_pipeline.py plus integration tests with fake providers confirm visual fallback requests only abstained/needs-review fields, fills eligible fields from stored page images, preserves PENDING text values, and records bounded visual_fallback observations. gsd_exec 2539a210 passed all 58 S04 tests.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None. All four tasks completed without plan changes. T03 adjusted existing test_extraction_gemini_usage.py assertions to filter for text_extraction stage observations after T02 added separate visual_fallback observation rows — this was an expected test-scoping fix, not a plan deviation.

## Known Limitations

None.

## Follow-ups

S05: Real five-document comparison — run --visual-fallback candidate against local compliance.db, compare against text-baseline and packet-aware candidates, verify R015/R016/R017.

## Files Created/Modified

None.
