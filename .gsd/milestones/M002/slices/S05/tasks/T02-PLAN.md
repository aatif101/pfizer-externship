---
estimated_steps: 9
estimated_files: 4
skills_used: []
---

# T02: Add bounded trace metadata hooks

Expected executor skills: observability, tdd, verify-before-complete.

Why: S04 exposes user-visible diagnostics, but research found retrieval/RAG modules do not yet have explicit trace metadata hooks even though `src/tracing.py` documents retrieval as a major traced function. S05 should harden observability without introducing network/auth requirements or broad schema changes.

Do: Add no-op-safe Langfuse observation and metadata hooks around the retrieval/index/answer boundaries. Follow the `src/pipeline/ingest.py` pattern: guarded import of `langfuse.decorators.observe` and `langfuse_context`, a no-op decorator fallback when unavailable, and defensive metadata update helpers that never raise. Decorate or wrap `build_retrieval_index()`, `retrieve_evidence()`, and `answer_question()` with names that make traces searchable. Attach only safe metadata: index status, indexed doc/page counts, run ID, provider name, answer status, reason code, top score, citation count, evidence reason, and trace ID if already provided. Do not include question text, raw snippets, raw page text, provider payloads, API key names/values, image blobs, docling JSON, or full content hashes. Add tests in `tests/test_tracing.py` or focused existing tests that monkeypatch module-local context/update hooks and prove metadata keys/values are bounded, Langfuse absence is no-op-safe, and service/retrieval behavior still works without credentials.

Threat Surface Q3: trace backends are an external observability surface; metadata can accidentally become durable secret or PHI leakage. The hook must whitelist fields instead of logging arbitrary objects.
Requirement Impact Q4: supports R008 diagnostics and R010 secret boundaries; must not alter the R005 answer/chat result contract or existing DTO shapes unless tests are updated for backward compatibility.
Failure Modes Q5: Langfuse import absence, auth absence, context update exception, retrieval exception, and provider exception must not crash indexing, retrieval, service, or Chat flows.
Load Profile Q6: metadata updates are constant-size per index/retrieval/answer call; at 10x query volume, the first concern is trace volume/cost, so keep metadata compact and avoid page/snippet payloads.
Negative Tests Q7: monkeypatched context failure, absent Langfuse module path if practical, provider exception path, weak evidence path, and static forbidden-key assertions for `question`, `snippet`, `page_text`, `api_key`, `secret`, `image_blob`, `docling_json`, and full `content_hash`.

Done when: Retrieval/index/answer boundaries produce no-op-safe traces with only whitelisted metadata and all existing service/retrieval tests continue to pass offline.

## Inputs

- `src/tracing.py`
- `src/pipeline/ingest.py`
- `src/retrieval/indexer.py`
- `src/retrieval/retriever.py`
- `src/rag/service.py`
- `src/rag/models.py`
- `src/rag/providers.py`
- `tests/test_tracing.py`
- `tests/test_retriever.py`
- `tests/test_answer_service.py`
- `tests/test_retrieval_cli.py`

## Expected Output

- `src/retrieval/indexer.py`
- `src/retrieval/retriever.py`
- `src/rag/service.py`
- `tests/test_tracing.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_tracing.py tests/test_retriever.py tests/test_answer_service.py tests/test_retrieval_cli.py

## Observability Impact

Adds compact Langfuse-compatible spans/metadata at the operational boundaries while preserving offline no-op behavior and redaction guarantees.
