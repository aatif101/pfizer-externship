# S04: Targeted visual fallback extraction

**Goal:** Add targeted visual fallback extraction that uses stored page images only for missing or suspicious fields, preserves good grounded text extraction values, records bounded visual usage observations, and exposes an opt-in path for the final real comparison slice.
**Demo:** A suspicious-field extraction can invoke visual fallback on stored page images, fill only eligible missing or suspicious fields, and preserve good grounded text values.

## Must-Haves

- R014: Provider-free tests prove visual fallback is requested only for eligible abstained or needs-review fields and never for already PENDING grounded fields.
- R014: Pipeline tests prove visual fallback can fill an eligible missing/suspicious field from stored page images while preserving good text-derived values and run-history persistence.
- R013/R016: Visual fallback records bounded `stage='visual_fallback'` usage observations for complete, skipped, and provider-error paths without raw prompts, page text, provider payloads, image bytes, PDFs, secrets, or local confidential paths.
- R014/R016: Gemini visual-provider tests prove image bytes are sent as SDK image parts, output is parsed through existing DTOs, malformed responses produce safe abstentions, and no local paths are included.
- R015/S05 readiness: CLI or composition wiring can opt into Gemini visual fallback for a candidate run without changing default text-only behavior.
- R017: Verification uses Windows-native `venv/Scripts/python.exe -m pytest ...` commands, preferably via `gsd_exec runtime=node` when recording evidence; no `/bin/bash` or `runtime=bash`.

## Proof Level

- This slice proves: Contract plus integration proof. The slice must exercise the real extraction pipeline with fake providers and stored in-DB image blobs, plus Gemini adapter behavior with a fake SDK client. Live Gemini/API runtime and real five-document UAT are explicitly deferred to S05.

## Integration Closure

Consumes S01 run-scoped history from `src/extraction/repository.py` and S03 bounded usage observations from `src/eval/repository.py`. Introduces optional visual-provider wiring in the extraction pipeline and CLI so S05 can run a visual-fallback candidate against the local five-document corpus. Keeps roadmap unchanged because S01-S03 provide the expected upstream surfaces and S05 remains the correct final real-corpus comparison slice.

## Verification

- Adds a separable `visual_fallback` extraction usage stage with bounded statuses such as complete, skipped, abstained, or error and sanitized reason codes like `not_configured`, `no_eligible_fields`, `missing_page_images`, or provider error classes. Future agents can inspect visual behavior through `list_extraction_usage_observations()` and extraction run history without accessing prompts, page text, provider payloads, images, PDFs, secrets, or local paths.

## Tasks

- [x] **T01: Add visual fallback contract and eligibility tests** `est:1h`
  skills_used: design-an-interface, tdd
  - Files: `src/extraction/providers.py`, `src/extraction/pipeline.py`, `tests/test_visual_fallback_pipeline.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py

- [ ] **T02: Wire pipeline fallback arbitration and visual observations** `est:2h`
  skills_used: tdd, observability, security-review
  - Files: `src/extraction/pipeline.py`, `tests/test_visual_fallback_pipeline.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py tests/test_extraction_usage_observations.py

- [ ] **T03: Implement Gemini image-part visual fallback provider** `est:2h`
  skills_used: api-design, tdd, security-review
  - Files: `src/extraction/gemini.py`, `tests/test_extraction_gemini_visual.py`, `tests/test_extraction_gemini_usage.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_visual.py tests/test_extraction_gemini_usage.py

- [ ] **T04: Expose opt-in visual fallback wiring for extraction runs** `est:1h`
  skills_used: api-design, tdd, verify-before-complete
  - Files: `src/extraction/cli.py`, `tests/test_extraction_cli.py`
  - Verify: venv/Scripts/python.exe -m pytest -q tests/test_extraction_cli.py tests/test_visual_fallback_pipeline.py tests/test_extraction_gemini_visual.py tests/test_extraction_usage_observations.py tests/test_eval_repository.py

## Files Likely Touched

- src/extraction/providers.py
- src/extraction/pipeline.py
- tests/test_visual_fallback_pipeline.py
- src/extraction/gemini.py
- tests/test_extraction_gemini_visual.py
- tests/test_extraction_gemini_usage.py
- src/extraction/cli.py
- tests/test_extraction_cli.py
