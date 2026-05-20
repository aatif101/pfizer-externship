---
id: T02
parent: S02
milestone: M002
key_files:
  - src/retrieval/models.py
  - src/retrieval/retriever.py
  - src/retrieval/__init__.py
  - tests/test_retriever.py
key_decisions:
  - Weak evidence outcomes expose diagnostics but intentionally return empty hits; top_score remains available so callers can inspect why evidence failed without receiving citation-ready snippets.
  - Only a content hash prefix is exposed from EvidenceGateResult public diagnostics; full corpus hashes remain in index/status internals.
duration: 
verification_result: passed
completed_at: 2026-05-20T21:31:17.937Z
blocker_discovered: false
---

# T02: Added a deterministic provider-free evidence gate that returns strong citation evidence only when status, score, and query coverage thresholds pass.

**Added a deterministic provider-free evidence gate that returns strong citation evidence only when status, score, and query coverage thresholds pass.**

## What Happened

Extended the retrieval DTO layer with EvidenceGateResult, including is_strong, reason_code, bounded hits, top_score, query_terms, run_id, and a safe content hash prefix. Added retrieve_evidence() and an EvidenceGate class over the existing HybridTextRetriever so downstream callers have a clear no-hallucination boundary. The gate checks get_retrieval_index_status() before scoring, refuses missing/empty/stale/error indexes, applies named top-score, query-term coverage, and hit-count thresholds, and returns weak outcomes with no fabricated hits. Existing HybridTextRetriever.retrieve() now returns the gate result shape while retaining backward-compatible reason/content_hash aliases for earlier callers. Added package exports for the gate API and DTOs. Expanded tests to cover strong supplier evidence plus empty/whitespace/stopword-only questions, missing index, empty indexed corpus, stale source corpus, unrelated no-match questions, and weak partial-overlap below-threshold questions.

## Verification

Ran the task-required evidence subset and full retriever regression tests. The evidence subset selected 7 tests and passed all weak/strong gate scenarios. The full retriever file passed all 14 tests, confirming existing hybrid retrieval behavior and DTO compatibility were preserved after the gate changes.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_retriever.py -k evidence` | 0 | ✅ pass (7 passed, 7 deselected) | 2482ms |
| 2 | `venv/Scripts/python.exe -m pytest tests/test_retriever.py` | 0 | ✅ pass (14 passed) | 3282ms |
| 3 | `venv/Scripts/python.exe -m pytest tests/test_retriever.py -k evidence && venv/Scripts/python.exe -m pytest tests/test_retriever.py` | 0 | ✅ pass (7 evidence tests, then 14 full retriever tests) | 5410ms |

## Deviations

Added src/retrieval/__init__.py exports for EvidenceGate, EvidenceGateResult, RetrievalResult, RetrievalEvidenceReason, RetrievalHit, and retrieve_evidence so downstream S03 callers can import the gate API from the retrieval package; this was a small integration-friendly addition beyond the three expected output files.

## Known Issues

None.

## Files Created/Modified

- `src/retrieval/models.py`
- `src/retrieval/retriever.py`
- `src/retrieval/__init__.py`
- `tests/test_retriever.py`
