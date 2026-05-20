# S03: Grounded Answer Service and Provider Seam

**Goal:** Add a grounded answer service and provider seam on top of the S02 retrieval evidence gate so callers can ask one API for a cited answer or safe abstention, with offline deterministic tests and a lazy Gemini implementation available when configured.
**Demo:** After this, tests can ask corpus-backed and off-topic questions through one service API and receive either a concise cited answer from a fake provider or a safe abstention, with a lazy Gemini provider available when configured.

## Must-Haves

- Threat Surface (Q3): user questions are untrusted input that reach SQLite retrieval and optional live provider calls; the service must use the existing parameterized retriever, pass providers only bounded snippets, never trust provider-supplied citations, and sanitize provider/configuration failures without secrets or raw responses.
- Requirement Impact (Q4): owns R005 answer-level grounded Q&A contract; supports R008 structured diagnostics; preserves R009 Python 3.11 venv verification; supports R010 by keeping secrets/provider responses/full page text/image blobs/full hashes out of public DTOs, reprs, errors, and tests. Re-verify S02 retrieval regressions and extraction Gemini provider regressions when adding the new Gemini seam. Decision D016 applies: service-owned citations, pre-provider abstention, and provider failures represented as safe result status values.
- Done when: (1) strong fixture questions return AnswerStatus.ANSWERED with fake-provider text and service-owned filename/page/snippet/score citations; (2) off-topic, blank, missing, empty, and stale evidence return AnswerStatus.ABSTAINED with zero provider calls; (3) provider exception or blank answer returns AnswerStatus.PROVIDER_ERROR with sanitized diagnostics and citations not fabricated; (4) Gemini answer provider imports without credentials, constructs only with a key or injected fake client, uses temperature 0, retries boundedly, and exposes only sanitized typed failures; (5) public rag exports expose stable DTO/service/provider surfaces and not prompt/helper internals.
- Slice verification command: `venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_extraction_provider_gemini.py`.

## Proof Level

- This slice proves: Contract and integration proof. Real runtime required: no for default verification; all tests must be offline and deterministic with fake providers/clients. Human/UAT required: no. The proof exercises the real SQLite retrieval/index path plus the new answer service and Gemini adapter seam without live secrets or network.

## Integration Closure

Upstream consumed: `src.retrieval.retrieve_evidence`, `EvidenceGateResult`, `RetrievalHit`, `RetrievalEvidenceReason`, fixture SQLite helpers in `tests/test_retriever.py`, and lazy provider/error patterns in `src/extraction/providers.py` and `src/extraction/gemini.py`. New wiring introduced: `src/rag` package with DTOs, provider protocol, answer orchestration service, lazy Gemini provider, and public exports for S04. Remaining after S03: Streamlit Chat UI rendering and final operational/evaluation proof in S04/S05.

## Verification

- Adds bounded diagnostics at the answer boundary: status, reason code, run_id, provider name, trace_id, top_score, citation_count, evidence reason, and safe error class. Failure visibility is through typed AnswerStatus/AnswerDiagnostics values and sanitized provider errors; diagnostics must exclude raw provider responses, full page text, image blobs, API keys, and full content hashes.

## Tasks

- [x] **T01: Implement service-owned cited answer contract** `est:2h`
  ---
  skills_used:
    - tdd
    - observability
    - verify-before-complete
  ---
  Why: S03 needs the no-hallucination answer boundary before any live provider variability. The service must make the deterministic S02 evidence gate authoritative, attach citations itself, and expose enough diagnostics for S04/S05 without leaking raw corpus content.
  - Files: `src/rag/__init__.py`, `src/rag/models.py`, `src/rag/providers.py`, `src/rag/service.py`, `tests/test_answer_service.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_retriever.py

- [ ] **T02: Add lazy Gemini answer provider seam** `est:2h`
  ---
  skills_used:
    - tdd
    - observability
    - verify-before-complete
  ---
  Why: S03 must provide a live Gemini path for configured demos while keeping imports, automated tests, and default app startup offline-safe and secret-free.
  - Files: `src/rag/gemini.py`, `src/rag/providers.py`, `src/rag/__init__.py`, `src/config.py`, `tests/test_answer_provider_gemini.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_answer_provider_gemini.py tests/test_answer_service.py tests/test_extraction_provider_gemini.py

- [ ] **T03: Lock rag package contract and slice regression proof** `est:1h`
  ---
  skills_used:
    - tdd
    - verify-before-complete
  ---
  Why: S04 should consume a stable service API without relying on internals, and S03 closeout must prove the new package did not regress S02 retrieval or extraction provider behavior.
  - Files: `tests/test_rag_contract.py`, `tests/test_answer_service.py`, `tests/test_answer_provider_gemini.py`, `src/rag/__init__.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_extraction_provider_gemini.py

## Files Likely Touched

- src/rag/__init__.py
- src/rag/models.py
- src/rag/providers.py
- src/rag/service.py
- tests/test_answer_service.py
- src/rag/gemini.py
- src/config.py
- tests/test_answer_provider_gemini.py
- tests/test_rag_contract.py
