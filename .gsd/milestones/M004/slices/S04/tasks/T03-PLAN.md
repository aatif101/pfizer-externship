---
estimated_steps: 9
estimated_files: 3
skills_used: []
---

# T03: Implement Gemini image-part visual fallback provider

skills_used: api-design, tdd, security-review

Why: S05 needs a real provider implementation that can send local stored page images to Gemini while preserving lazy/offline-safe imports and the bounded S03 usage metadata contract.

Do:
1. Implement `GeminiSDFVisualFallbackProvider` in `src/extraction/gemini.py`, or add an `extract_visual_fields()` implementation that satisfies the new visual protocol while keeping the existing text extraction provider behavior unchanged.
2. Build Gemini request contents from a bounded text prompt plus `google.genai.types.Part.from_bytes(data=page.image_blob, mime_type='image/png')` for selected pages. Include only bounded identifiers, field names, page numbers, and instructions; exclude raw page text, local filesystem paths, prompts in persisted outputs, PDFs, secrets, and provider payload logging.
3. Reuse existing Gemini helpers where appropriate for response generation, JSON parsing, field payload parsing, malformed-result handling, usage metadata extraction, and estimated cost calculation.
4. Add new `tests/test_extraction_gemini_visual.py` with fake Gemini client/response helpers proving image parts are sent, only requested fields are prompted, malformed JSON becomes a safe provider result, usage metadata is populated, and local paths/raw page text are not embedded in request contents.
5. Keep all Google SDK imports lazy/offline-safe so unit tests with fake clients do not require live credentials.

Done when: Gemini visual provider tests prove SDK image-part construction and bounded metadata behavior, while existing Gemini text usage tests remain green.

## Inputs

- `src/extraction/gemini.py`
- `src/extraction/providers.py`
- `src/db/queries.py`
- `tests/test_extraction_gemini_usage.py`

## Expected Output

- `src/extraction/gemini.py`
- `tests/test_extraction_gemini_visual.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_visual.py tests/test_extraction_gemini_usage.py

## Observability Impact

Reuses provider usage metadata so visual Gemini calls contribute bounded token, latency, cost, trace, provider, model, and status data without exposing confidential request contents.
