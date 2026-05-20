---
id: T01
parent: S03
milestone: M002
key_files:
  - src/rag/__init__.py
  - src/rag/models.py
  - src/rag/providers.py
  - src/rag/service.py
  - tests/test_answer_service.py
key_decisions:
  - Answer service treats S02 retrieval evidence as authoritative and owns citations rather than trusting provider-supplied citations.
  - Provider errors expose only safe status/reason/error-class diagnostics, never raw provider messages or responses.
duration: 
verification_result: mixed
completed_at: 2026-05-20T22:49:24.174Z
blocker_discovered: false
---

# T01: Added a grounded answer service contract that gates provider calls behind strong retrieval evidence, owns citations, and exposes safe answer diagnostics.

**Added a grounded answer service contract that gates provider calls behind strong retrieval evidence, owns citations, and exposes safe answer diagnostics.**

## What Happened

Created the src/rag package API by adding the service module and package exports on top of the existing answer DTOs and provider seam. The service now calls retrieve_evidence first, abstains without invoking a provider for weak evidence, passes only bounded RetrievalHit snippets to providers for strong evidence, derives AnswerCitation values exclusively from retrieval hits, and maps provider exceptions, blank answers, malformed results, and retrieval failures into safe AnswerResult statuses. Added deterministic fake-provider tests covering strong cited answers, abstention without provider calls, missing/stale/blank/off-topic evidence, provider failures, top_k citation bounding, run_id/trace/provider diagnostics propagation, and redaction of raw page tails, provider exception secrets, and full content hashes from public repr/diagnostics.

## Verification

Ran the task verification command `venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_retriever.py`. The first run exposed an over-strict test assertion that disallowed S02's intentionally safe hash-prefix-bearing run_id; after narrowing the assertion to the actual requirement of excluding full hashes and raw content, the full verification suite passed with 28 tests.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_retriever.py` | 1 | ❌ fail (redaction test over-constrained safe run_id hash prefix) | 3944ms |
| 2 | `venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_retriever.py` | 0 | ✅ pass (28 tests) | 6224ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/rag/__init__.py`
- `src/rag/models.py`
- `src/rag/providers.py`
- `src/rag/service.py`
- `tests/test_answer_service.py`
