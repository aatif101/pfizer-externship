---
estimated_steps: 11
estimated_files: 2
skills_used: []
---

# T02: Wire pipeline fallback arbitration and visual observations

skills_used: tdd, observability, security-review

Why: The core R014 behavior lives in the extraction pipeline: run text extraction first, call visual fallback only for eligible fields with stored page images, merge only improvements, persist once, and record bounded visual-stage telemetry after the extraction run exists.

Do:
1. Extend `extract_document()` in `src/extraction/pipeline.py` with an optional `visual_provider` parameter and keep default behavior unchanged when it is omitted.
2. After text normalization, select eligible fields, load pages with `include_image_bytes=True` only when fallback is configured and eligible fields exist, and pass selected image-bearing pages to the visual provider.
3. Normalize visual provider results through the existing field normalization/guard path so the conservative text-grounded evidence contract remains intact.
4. Merge only eligible fields: replace `ABSTAINED` with valid non-abstained candidates, replace `NEEDS_REVIEW` only with a stronger valid candidate, and never replace current `PENDING` text fields.
5. Persist the merged `SDFExtractionRecord` via existing repository behavior so latest-write and run-scoped history remain compatible.
6. Insert one bounded `visual_fallback` usage observation for complete, skipped, abstained, and provider-error paths. Persist only provider/model/status/trace/latency/tokens/cost/sanitized error reason; never persist prompts, page text, image bytes, provider payloads, PDFs, secrets, or local paths.
7. Add/extend tests in `tests/test_visual_fallback_pipeline.py` for: fills an abstained field from an image-backed page; preserves good text fields; skips with no images; records visual usage observations; provider exceptions do not overwrite text result and produce sanitized diagnostics.

Done when: Provider-free tests prove the fallback improves only eligible fields, preserves good text values, writes run history for the merged result, and exposes bounded visual telemetry for success and failure paths.

## Inputs

- `src/extraction/pipeline.py`
- `src/extraction/providers.py`
- `src/db/queries.py`
- `src/extraction/repository.py`
- `src/eval/repository.py`
- `tests/test_visual_fallback_pipeline.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_extraction_persistence.py`
- `tests/test_extraction_usage_observations.py`

## Expected Output

- `src/extraction/pipeline.py`
- `tests/test_visual_fallback_pipeline.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py tests/test_extraction_usage_observations.py

## Observability Impact

Adds the runtime `visual_fallback` usage-observation stage and sanitized skip/error reasons that future agents can inspect per run/document.
