---
estimated_steps: 9
estimated_files: 3
skills_used: []
---

# T02: Add deterministic evidence gate and weak-result reasons

Expected executor skills/frontmatter: tdd, api-design, verify-before-complete.

Why: The milestone's no-hallucination guarantee depends on refusing weak or off-topic retrieval before any generator exists. This task wraps the positive retriever in an evidence gate that S03 can call safely.

Do: Extend `src/retrieval/retriever.py` with a `retrieve_evidence(db_path, question, top_k=5, ...)` function or `EvidenceGate` class that first calls `get_retrieval_index_status(db_path)` and only scores when the index status is `BUILT`. Add immutable safe DTOs for the gate result if they were not fully added in T01: `EvidenceGateResult` with `is_strong`, `reason_code`, `hits`, `top_score`, `query_terms`, `run_id`, and optional content hash prefix; `RetrievalHit` should remain citation-ready and safe to repr. Implement explicit thresholds such as minimum top score, minimum query-term coverage, and optionally minimum hit count; keep constants named and testable. Return weak results for empty/stopword-only questions, missing index, empty index, stale index, no matches, and below-threshold matches. Do not fabricate hits for weak outcomes.

Threat Surface (Q3): adversarial or off-topic user questions may try to force citations. The gate must base `is_strong` only on measured retrieval score/coverage/status and must return deterministic weak evidence when thresholds are not met.

Requirement Impact (Q4): owns R005 abstention/retrieval proof and supports R008-R010. Re-verify no downstream generation assumptions are introduced; provider-free remains mandatory.

Failure Modes (Q5): missing database/schema/status errors should return or raise only typed/sanitized failures according to the existing S01 status contract; stale indexes must not be queried as if fresh; empty corpus must not produce hits.

Load Profile (Q6): evidence evaluation should be O(top_k) after retrieval and add trivial CPU overhead. It should not perform provider calls, network calls, or image/blob reads.

Negative Tests (Q7): empty string, whitespace-only string, stopword-only question, unrelated topic, mutated source page text after build (stale), missing retrieval index before build, empty indexed corpus, and weak partial-overlap query all return weak reason codes with empty or non-strong hits according to the contract.

Done when: `retrieve_evidence()` (or equivalent exported gate API) returns `strong_evidence` for fixture supplier-document questions and deterministic weak reason codes for off-topic, empty, missing, empty, stale, and below-threshold scenarios.

## Inputs

- `src/retrieval/models.py`
- `src/retrieval/retriever.py`
- `src/retrieval/indexer.py`
- `tests/test_retriever.py`

## Expected Output

- `src/retrieval/models.py`
- `src/retrieval/retriever.py`
- `tests/test_retriever.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_retriever.py -k evidence

## Observability Impact

Adds typed reason codes, `is_strong`, `top_score`, query terms, and index run metadata to every evidence decision so later answer generation and Streamlit Chat can show safe abstentions and diagnostics.
