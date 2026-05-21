# S03: Grounded Answer Service and Provider Seam — UAT

**Milestone:** M002
**Written:** 2026-05-20T23:07:26.225Z

## UAT: Grounded Answer Service and Provider Seam

**UAT Type:** Automated developer acceptance, offline deterministic service-level UAT.

### Preconditions

1. The project virtual environment exists at `venv/Scripts/python.exe`.
2. Fixture SQLite/index data used by the retriever tests is available in the repository.
3. No live Gemini credentials are required; fake providers/clients are used for acceptance.

### Steps

1. Run `venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_extraction_provider_gemini.py`.
2. Inspect the answer service cases for a corpus-backed fixture question.
3. Inspect the weak-evidence cases for blank, off-topic, missing, empty, and stale evidence.
4. Inspect provider-failure cases for exceptions and blank provider output.
5. Inspect Gemini provider seam cases for offline imports, missing-key behavior, injected fake client behavior, bounded retries, and sanitized errors.
6. Inspect rag contract tests for stable public exports and private prompt/helper internals.

### Expected Outcomes

1. The full command passes with all tests green.
2. Strong evidence returns `ANSWERED`, concise fake-provider answer text, and service-owned citations containing filename, 1-indexed page number, snippet, and score.
3. Weak or unavailable evidence returns `ABSTAINED`, includes safe diagnostics, has no citations, and does not call the provider.
4. Provider exceptions or blank provider answers return `PROVIDER_ERROR` with sanitized diagnostics and no fabricated citations.
5. Gemini answer provider modules import without credentials or network, construct only with explicit key/client configuration, and expose typed sanitized failures.
6. `src.rag` exposes only the stable DTO/service/provider surface intended for S04 and does not expose prompt/helper internals.

### Edge Cases Covered

- Blank user question.
- Off-topic question with weak retrieval evidence.
- Missing, empty, and stale retrieval/index states.
- Retrieval error mapping.
- Provider exception, retry exhaustion, non-retryable failure, and blank provider response.
- Prompt snippet bounding and redaction of raw page text, raw provider payloads, API-key-like content, and full hashes.

### Not Proven By This UAT

- Live Gemini network quality, cost, or latency with real credentials.
- Streamlit Chat tab rendering and rerun behavior; this is deferred to S04.
- End-to-end operational proof across CLI, UI, tracing, and evaluation hooks; this is deferred to S05.
