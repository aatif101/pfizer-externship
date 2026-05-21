---
id: T02
parent: S03
milestone: M002
key_files:
  - src/rag/gemini.py
  - src/rag/providers.py
  - src/rag/__init__.py
  - src/config.py
  - tests/test_answer_provider_gemini.py
key_decisions:
  - Keep `src/rag/providers.py` SDK-free and expose live Gemini through a lazy builder plus direct `src.rag.gemini` export.
  - Treat Gemini answer output as concise plain text and derive citations outside the provider, preserving the retrieval-owned citation boundary.
  - Sanitize provider and configuration failures to provider/model/run/error-class metadata only, excluding secrets, raw responses, and full snippets.
duration: 
verification_result: passed
completed_at: 2026-05-20T23:00:36.092Z
blocker_discovered: false
---

# T02: Added a lazy Gemini answer provider seam with offline fake-client tests, bounded retries, prompt-snippet limits, trace IDs, and sanitized provider errors.

**Added a lazy Gemini answer provider seam with offline fake-client tests, bounded retries, prompt-snippet limits, trace IDs, and sanitized provider errors.**

## What Happened

Implemented `src/rag/gemini.py` as the live Gemini answer adapter while keeping credentials, optional google-genai imports, and network client creation lazy. Refactored `src/rag/providers.py` back to the provider protocol/error DTO surface plus a lazy `build_answer_provider("gemini")` factory so fake providers remain easy to inject and importing the protocol module stays SDK-free. Updated package exports and config descriptions, then added `tests/test_answer_provider_gemini.py` covering offline import, missing-key construction, injected-client success, lazy client_factory behavior, retryable and nonretryable failures, retry exhaustion, blank responses, prompt snippet bounding, trace-id extraction, builder behavior, and optional SDK import failure sanitization.

## Verification

Ran the task's requested targeted verification command: `venv/Scripts/python.exe -m pytest tests/test_answer_provider_gemini.py tests/test_answer_service.py tests/test_extraction_provider_gemini.py`. The suite passed with 25 tests, confirming the new Gemini answer seam, existing answer service contract, and extraction Gemini provider regressions.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_answer_provider_gemini.py tests/test_answer_service.py tests/test_extraction_provider_gemini.py` | 0 | ✅ pass | 3886ms |

## Deviations

The prior T01 state already had a Gemini answer implementation embedded in `src/rag/providers.py`; this task refactored that implementation into the planned `src/rag/gemini.py` module instead of adding a completely new provider from scratch. The final provider follows the T02 plain-text response contract rather than the earlier JSON response parsing.

## Known Issues

None.

## Files Created/Modified

- `src/rag/gemini.py`
- `src/rag/providers.py`
- `src/rag/__init__.py`
- `src/config.py`
- `tests/test_answer_provider_gemini.py`
