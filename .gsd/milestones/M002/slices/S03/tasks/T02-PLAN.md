---
estimated_steps: 12
estimated_files: 5
skills_used: []
---

# T02: Add lazy Gemini answer provider seam

---
skills_used:
  - tdd
  - observability
  - verify-before-complete
---
Why: S03 must provide a live Gemini path for configured demos while keeping imports, automated tests, and default app startup offline-safe and secret-free.

Do: Add `src/rag/gemini.py` mirroring the lazy/client-injection pattern from extraction. Implement `GeminiAnswerProvider` with constructor parameters for `api_key`, `model`, injected `client`, optional `client_factory`, and bounded `max_attempts`. Reuse `get_settings().gemini_api_key` and `gemini_model` only at construction time; importing `src.rag.gemini` must not require credentials or network. Build a prompt from the question and bounded evidence snippets only, instructing Gemini to answer concisely from supplied evidence and not invent facts. Call `client.models.generate_content(model=..., contents=..., config={"temperature": 0})`; parse plain `response.text`, strip simple fences if useful, reject blank text, and return `AnswerProviderResult` with provider name and trace id. Raise `AnswerConfigurationError` for missing credentials when no injected client/factory exists and `AnswerProviderError` for SDK failures with a sanitized message containing provider/model/run/error class only. Add or update a builder seam such as `build_answer_provider("gemini")` if useful for S04, while keeping fake providers easy to inject.

Failure Modes (Q5): missing key raises typed configuration error only on construction; optional google-genai import failures raise sanitized configuration errors; retryable timeouts/429/5xx retry boundedly; malformed/blank response raises typed provider error without raw response.

Load Profile (Q6): one Gemini call per strong-evidence question; 10x load first hits provider rate limits/cost, so no provider call may occur for weak evidence and retries must remain bounded.

Negative Tests (Q7): import without key, missing-key construction, fake-client success, retryable transient failure then success, nonretryable failure, blank response, trace id extraction, and assertion that API keys/raw response/full snippets are absent from error strings.

Done when: Gemini provider tests pass offline with fake clients, extraction Gemini provider regressions still pass, and package exports expose the live provider without making `import src.rag` credential-dependent.

## Inputs

- `src/rag/__init__.py`
- `src/rag/models.py`
- `src/rag/providers.py`
- `src/rag/service.py`
- `src/extraction/gemini.py`
- `src/extraction/providers.py`
- `src/config.py`
- `tests/test_extraction_provider_gemini.py`

## Expected Output

- `src/rag/gemini.py`
- `src/rag/providers.py`
- `src/rag/__init__.py`
- `src/config.py`
- `tests/test_answer_provider_gemini.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_answer_provider_gemini.py tests/test_answer_service.py tests/test_extraction_provider_gemini.py

## Observability Impact

Adds provider diagnostics for provider name, model, trace id, max attempts, run id, and sanitized error class while preserving the no-secrets/no-raw-response boundary required by R008/R010.
