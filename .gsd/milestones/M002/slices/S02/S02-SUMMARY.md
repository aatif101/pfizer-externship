---
id: S02
parent: M002
milestone: M002
provides:
  - S03 can call the stable retrieval/evidence API without providers or secrets.
  - S03 can rely on weak outcomes containing no citation-ready hits, preventing answer generation from inventing citations.
  - S04 can render filenames, 1-indexed page numbers, scores, and verbatim snippets for strong evidence and user-actionable weak reason codes for failures.
requires:
  - slice: S01
    provides: Consumed persisted retrieval index runs/pages, optional FTS table behavior, index status metadata, normalized index text, and fixture indexing helpers.
affects:
  - S03: Grounded Answer Service and Provider Seam
  - S04: Streamlit Chat User Loop
  - S05: Operational Proof and Evaluation Hooks
key_files:
  - src/retrieval/models.py
  - src/retrieval/retriever.py
  - src/retrieval/__init__.py
  - tests/test_retriever.py
key_decisions:
  - Raw page text remains confined to retriever-local internals; public DTOs expose bounded snippets only.
  - Weak evidence outcomes expose reason-coded diagnostics but return empty hits so downstream services cannot fabricate citations.
  - The public package contract exports service and DTO surfaces while keeping FTS/query/snippet helper internals out of `src.retrieval.__all__`.
  - Only a content hash prefix is exposed in public evidence diagnostics; full corpus hashes remain internal/status-level metadata.
patterns_established:
  - Provider-free retrieval/evidence seam suitable for deterministic tests and offline demos.
  - FTS5-first candidate access with deterministic lexical fallback for portability.
  - Reason-coded evidence gate as the no-hallucination boundary before answer generation.
  - Bounded diagnostics pattern: expose enough metadata to debug without exposing full page text, secrets, image blobs, or provider output.
observability_surfaces:
  - Evidence result DTOs expose reason_code, is_strong, top_score, query_terms, run_id, content_hash_prefix, score components, and bounded snippets.
  - Weak evidence states distinguish empty_question, index_missing, index_empty, index_stale, no_match, below_threshold, and status/error-style failures.
drill_down_paths:
  - .gsd/milestones/M002/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S02/tasks/T02-SUMMARY.md
  - .gsd/milestones/M002/slices/S02/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-05-20T21:35:37.140Z
blocker_discovered: false
---

# S02: Hybrid Retriever and Evidence Gate

**Implemented and verified a provider-free hybrid SQLite text retriever with deterministic evidence gating, citation-ready bounded snippets for strong matches, and explicit weak-evidence reason codes for unsafe or insufficient evidence states.**

## What Happened

S02 adds the first query-facing retrieval contract for M002 on top of the S01 SQLite retrieval index. The implementation introduces public retrieval DTOs for reason-coded outcomes, hits, score components, query terms, index run metadata, top score diagnostics, and safe content-hash prefixes. The hybrid retriever normalizes questions, extracts deterministic search terms, queries FTS5 when available with quoted parameterized MATCH terms, applies lexical coverage/phrase/proximity scoring, falls back to lexical scoring when FTS is unavailable or produces no candidates, and deterministically orders ties by score, filename, document ID, and page. Citation-ready hits include stable doc_id, filename, 1-indexed page number, score diagnostics, and short query-focused verbatim snippets without exposing full page text.

The evidence gate now forms the no-hallucination boundary for downstream S03. It checks retrieval index status before scoring, refuses missing, empty, stale, or error index states, applies top-score, query-term coverage, and hit-count thresholds, and returns weak outcomes with explicit reason codes rather than fabricated citations. Weak outcomes preserve enough bounded diagnostics for debugging, such as reason_code, top_score, query_terms, run_id, and content_hash_prefix, while intentionally returning no citation-ready hits. Package exports in src/retrieval/__init__.py expose the stable S02 contract for downstream services while keeping helper internals out of __all__.

Task work also added safety and regression coverage around public imports, FTS-missing and FTS-empty fallback, hostile SQL/FTS metacharacter queries, bounded top_k behavior, deterministic ordering, 1-indexed page numbers, sanitized repr/diagnostics, and S01 index repository/indexer/CLI compatibility.

## Verification

Closeout verification was run through the project Python 3.11 virtual environment using the closeout-safe verification surface. Command: `venv/Scripts/python.exe -m pytest tests/test_retriever.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py`. Result: exit code 0, `42 passed in 6.46s` (gsd_exec run df8732f4-84a9-415b-b0e6-522ce37d4d25). This covers the retriever/evidence gate contract plus S01 repository, indexer, and CLI regressions. Prior task-level verification also passed the focused hybrid subset, evidence subset, full retriever suite, and combined S01/S02 regression commands.

## Requirements Advanced

- R005 — Introduced the retrieval and deterministic abstention/evidence gate layer needed for grounded Q&A with page-level citations; full validation awaits answer generation and Chat UX in S03-S05.
- R008 — Added structured retrieval diagnostics and reason-coded failure surfaces that downstream tracing can attach to Langfuse without leaking raw text or secrets.
- R009 — Verified the slice through `venv/Scripts/python.exe`, preserving the Python 3.11 verification constraint.
- R010 — Public diagnostics and tests assert no provider responses, API keys, raw full page text, image blobs, or full content hashes are exposed.

## Requirements Validated

None.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

T02 added package-level exports in `src/retrieval/__init__.py` earlier than originally listed for that task so S03 can import the gate API directly. `src/retrieval/repository.py` did not require changes because S01 already exposed the needed safe index metadata and FTS availability; raw page text access remains retriever-internal.

## Known Limitations

This slice does not generate natural-language answers, call live LLM providers, render Streamlit Chat UI, run visual retrieval, or prove end-to-end chatbot UX. Evidence quality is fixture-tested with deterministic lexical/FTS scoring, not yet benchmarked against a gold-set retrieval metric.

## Follow-ups

S03 should consume `retrieve_evidence()`/`EvidenceGate` as the citation-safety boundary before any provider generation. S04 should render weak reason codes and citation snippets clearly in Streamlit. S05 should add operational proof across CLI, service, UI, failure modes, and evaluation hooks.

## Files Created/Modified

- `src/retrieval/models.py` — Added retrieval/evidence DTOs, reason codes, score components, and safe diagnostics fields.
- `src/retrieval/retriever.py` — Implemented HybridTextRetriever, lexical/FTS scoring, snippet creation, and EvidenceGate/retrieve_evidence service API.
- `src/retrieval/__init__.py` — Exported the stable public S02 retrieval contract for downstream slices.
- `tests/test_retriever.py` — Added hybrid retrieval, evidence gate, contract, fallback, ordering, and safety regression coverage.
