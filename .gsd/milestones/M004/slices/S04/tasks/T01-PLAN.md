---
estimated_steps: 8
estimated_files: 3
skills_used: []
---

# T01: Add visual fallback contract and eligibility tests

skills_used: design-an-interface, tdd

Why: S04 needs a narrow, backward-compatible seam for image-based fallback before orchestration can call a provider. The contract must make field/page eligibility explicit and avoid changing existing `SDFExtractionProvider` fakes.

Do:
1. Add dedicated visual fallback DTOs/protocols in `src/extraction/providers.py`, including a request object with eligible field names, selected pages with `image_blob` populated, and bounded reason codes.
2. Add pipeline helper functions in `src/extraction/pipeline.py` that compute visual fallback eligibility from normalized `ExtractedField` objects: include `ABSTAINED` and `NEEDS_REVIEW`, exclude `PENDING`.
3. Add deterministic tests in new `tests/test_visual_fallback_pipeline.py` for eligibility reason codes, exclusion of good grounded fields, and no provider invocation when the eligible set is empty.
4. Keep all reason strings bounded and generic; do not include raw field values, spans, page text, image bytes, local paths, provider payloads, or prompts.

Done when: The new contract is importable, existing text provider protocol tests still pass, and eligibility tests prove only suspicious/missing fields enter fallback.

## Inputs

- `src/extraction/providers.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_pipeline.py`
- `.gsd/milestones/M004/slices/S04/S04-RESEARCH.md`

## Expected Output

- `src/extraction/providers.py`
- `src/extraction/pipeline.py`
- `tests/test_visual_fallback_pipeline.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py

## Observability Impact

Establishes bounded visual fallback reason codes that downstream usage observations can persist safely.
