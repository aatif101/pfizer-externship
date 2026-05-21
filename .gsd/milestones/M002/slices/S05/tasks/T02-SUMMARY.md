---
id: T02
parent: S05
milestone: M002
key_files:
  - src/retrieval/indexer.py
  - src/retrieval/retriever.py
  - src/rag/service.py
  - tests/test_tracing.py
key_decisions:
  - Trace metadata is allowlisted per boundary and intentionally excludes question text, snippets, raw page text, provider payloads, secrets, image blobs, Docling JSON, and full content hashes.
  - Langfuse/context failures are swallowed at hook boundaries so indexing, retrieval, and answer behavior remains offline/no-op safe.
duration: 
verification_result: passed
completed_at: 2026-05-20T23:51:04.625Z
blocker_discovered: false
---

# T02: Added no-op-safe, allowlisted Langfuse metadata hooks around retrieval indexing, evidence retrieval, and RAG answer generation.

**Added no-op-safe, allowlisted Langfuse metadata hooks around retrieval indexing, evidence retrieval, and RAG answer generation.**

## What Happened

Implemented guarded Langfuse `observe` imports and defensive metadata-update helpers in `src/retrieval/indexer.py`, `src/retrieval/retriever.py`, and `src/rag/service.py`. The new hooks decorate `build_retrieval_index()`, `retrieve_evidence()`, and `answer_question()` with searchable span names, and emit only compact operational metadata such as boundary, status/reason, run ID, provider name, trace ID, top score, citation count, counts, and sanitized error class. The answer service now updates trace metadata on answered, abstained, provider-error, malformed-result, blank-answer, and retrieval-exception paths without changing public DTOs. Added focused tests in `tests/test_tracing.py` that monkeypatch module-local Langfuse contexts to verify bounded metadata, no-op behavior when Langfuse is absent, resilience when context updates raise, and safe provider-exception metadata.

## Verification

Ran the focused offline verification suite required by the task: `venv/Scripts/python.exe -m pytest tests/test_tracing.py tests/test_retriever.py tests/test_answer_service.py tests/test_retrieval_cli.py`. It passed with 42 tests, covering tracing hooks plus retrieval, answer-service, and CLI regressions without live credentials.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_tracing.py tests/test_retriever.py tests/test_answer_service.py tests/test_retrieval_cli.py` | 0 | ✅ pass (42 tests passed) | 9651ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/retrieval/indexer.py`
- `src/retrieval/retriever.py`
- `src/rag/service.py`
- `tests/test_tracing.py`
