---
estimated_steps: 25
estimated_files: 7
skills_used: []
---

# T03: Add Gemini adapter and robust provider failure handling

---
estimated_steps: 9
estimated_files: 6
skills_used:
  - tdd
  - observability
  - security-review
  - verify-before-complete
---

Why: S03 needs a real Gemini-primary extraction seam, but default tests and app startup must remain non-fatal without API credentials or network access.

Do:
1. Add `google-genai` to `pyproject.toml` using the project stack recommendation, without making test import paths require credentials.
2. Add non-required settings in `src/config.py`: `gemini_api_key`, `gemini_model` defaulting to `gemini-2.5-flash`, and `extraction_low_confidence_threshold` defaulting to `0.75` unless tests justify a different named default.
3. Implement `src/extraction/gemini.py` or a provider class in `src/extraction/providers.py` that conforms to the protocol from T02.
4. Prompt/request structured six-field output with 0-indexed page references and short verbatim spans; still validate everything in the pipeline with Pydantic and source-span grounding.
5. Add typed errors such as `ExtractionConfigurationError`, `ExtractionProviderError`, and `ExtractionValidationError` where useful. Missing `GEMINI_API_KEY` should produce a clear typed configuration error caught by CLI/pipeline callers, not crash Streamlit imports.
6. Use low-count `tenacity` retry behavior for transient 429/503/timeouts around live provider calls. Tests should mock retryable failures rather than sleep or call the network.
7. Ensure malformed provider output can produce a model-compatible failure/abstention record when appropriate, with non-secret reason text and no raw response/page text in logs.
8. Add mocked provider/Gemini tests for missing credentials, malformed JSON/shape, retryable error wrapping, low confidence review state, and span mismatch handling.

Threat Surface (Q3): Sends supplier document text/images to an external API when live provider is used. Never log API keys, full page text, raw model responses, or image blobs. Treat provider output as untrusted.
Requirement Impact (Q4): Advances R002 and R008; supports R003/R004 by feeding pipeline persistence. Re-verify config import, Streamlit smoke, and default pytest without credentials.
Failure Modes (Q5): Missing credentials => typed config error. 429/503/timeout => bounded retry then provider error. Malformed response => validation failure or abstention record. Bad source citations => needs-review/abstention.
Load Profile (Q6): Provider calls are rate-limited and cost-bearing; at 10x load Gemini quota/cost is first breakpoint. Keep batch extraction sequential or explicitly bounded; no hidden parallel fan-out.
Negative Tests (Q7): No `GEMINI_API_KEY`, malformed provider response, invalid JSON-compatible bbox, retryable provider exception, low confidence, and span mismatch.

Done when the Gemini adapter exists behind the provider protocol, default tests remain offline, and all provider failure paths are deterministic and observable.

## Inputs

- `pyproject.toml`
- `src/config.py`
- `src/extraction/providers.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_pipeline.py`

## Expected Output

- `pyproject.toml`
- `src/config.py`
- `src/extraction/providers.py`
- `src/extraction/gemini.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_provider_gemini.py`
- `tests/test_extraction_pipeline.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_app.py tests/test_extraction_pipeline.py tests/test_extraction_provider_gemini.py -q

## Observability Impact

Adds typed provider/config errors and bounded retry diagnostics; preserves optional Langfuse behavior and redaction boundaries for secrets/page content.
