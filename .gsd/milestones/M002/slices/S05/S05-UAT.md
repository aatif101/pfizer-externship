# S05: Operational Proof and Evaluation Hooks — UAT

**Milestone:** M002
**Written:** 2026-05-20T23:57:40.615Z

## UAT: Offline Retrieval and RAG Chatbot Operational Proof

**UAT Type:** Automated offline acceptance test over fixture SQLite data, fake answer providers, fake Streamlit seam, and Python 3.11 project virtual environment.

### Preconditions

1. Work from the project root on Windows.
2. Use the project virtual environment: `venv/Scripts/python.exe`.
3. No Gemini, Anthropic, Langfuse, Qdrant, GPU, browser, or network credentials are required.
4. Fixture SQLite databases are created in temporary test directories by the test suite.

### Steps

1. Run the final operational regression:
   `venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py tests/test_retrieval_cli.py tests/test_retriever.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_chat_dashboard.py tests/test_app.py tests/test_tracing.py`
2. Confirm the suite exits with code 0.
3. Confirm the S05 end-to-end proof builds a retrieval index through the real CLI from seeded SQLite pages.
4. Confirm a grounded supplier-document question returns a concise answer with filename/page/snippet citations.
5. Confirm an unrelated question safely abstains and does not fabricate citations or call the answer provider.
6. Confirm provider configuration/runtime failures surface as safe user-facing failures instead of crashes.
7. Confirm the Streamlit Chat seam renders answer, citations, abstention, and diagnostics states.
8. Confirm tracing tests show allowlisted metadata only and no-op behavior when Langfuse context is absent or failing.

### Expected Outcomes

- The regression reports all tests passing; closeout evidence reported 66 passed.
- The CLI indexing path, retrieval path, RAG service path, Chat rendering seam, and tracing hooks are exercised together.
- Public output surfaces do not expose API keys, raw provider payloads, raw full page text, image blobs, Docling JSON, or full content hashes.
- Weak or off-topic evidence produces deterministic abstention rather than hallucinated citations.
- Operational failures are diagnosable through pytest failures, CLI status output, `AnswerDiagnostics`, Chat diagnostics text, and bounded trace metadata.

### Edge Cases Covered

- Empty, missing, or stale retrieval-index states through CLI/retrieval regressions.
- Weak evidence and unrelated questions.
- Provider not configured, provider runtime exception, malformed/blank answer handling.
- Langfuse missing or context update failure.
- Chat rerender/user-facing diagnostics behavior under the fake Streamlit seam.

### Not Proven By This UAT

- Live Gemini answer quality, latency, or cost.
- Live Langfuse SaaS trace ingestion.
- Visual ColQwen/Qdrant multivector retrieval.
- Browser-based manual Streamlit interaction.
- Full RAGAS/gold-set evaluation metrics planned for later work.
