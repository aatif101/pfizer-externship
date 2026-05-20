# S02: Hybrid Retriever and Evidence Gate — UAT

**Milestone:** M002
**Written:** 2026-05-20T21:35:37.141Z

# S02 UAT: Hybrid Retriever and Evidence Gate

## UAT Type
Automated developer/integration UAT over fixture SQLite data. No live provider, network, secrets, Streamlit UI, Gemini, Claude, Qdrant, bm25s, or sentence-transformers are required.

## Preconditions
1. The project virtual environment exists at `venv/Scripts/python.exe` and uses Python 3.11.
2. S01 retrieval index schema and fixture helpers are available.
3. The working tree contains the S02 retrieval contract in `src/retrieval/`.

## Steps
1. Build fixture SQLite documents/pages through the existing retrieval index fixture path.
2. Query the retrieval API with a supplier-document question expected to match a fixture page.
3. Inspect the returned evidence result.
4. Query with empty, whitespace-only, stopword-only, unrelated, and partial-overlap/below-threshold questions.
5. Simulate missing, empty, stale, FTS unavailable, and FTS-empty index states through tests.
6. Run the full regression command: `venv/Scripts/python.exe -m pytest tests/test_retriever.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py`.

## Expected Outcomes
1. Matching supplier-document questions return `strong_evidence` with at least one citation-ready hit.
2. Hits include stable `doc_id`, filename, 1-indexed display page number, numeric score, compact score components, and a short verbatim snippet focused on query terms.
3. Public DTOs and diagnostics do not expose raw full page text, image blobs, full content hashes, API keys, or provider responses.
4. Empty, missing, empty-index, stale-index, no-match, and below-threshold paths return deterministic weak evidence with explicit reason codes and no fabricated citations.
5. FTS5 is used when available, and lexical fallback still retrieves/scorers deterministically when FTS is unavailable or returns no candidates.
6. The regression command passes with all tests green.

## Edge Cases Covered
- Empty/whitespace/stopword-only questions.
- Missing retrieval index.
- Indexed corpus with zero pages.
- Stale source corpus relative to index metadata.
- Unrelated no-match queries.
- Partial-overlap queries below evidence threshold.
- FTS table missing or present but returning no candidates.
- SQL/FTS metacharacter-heavy questions.
- Non-positive `top_k` normalization and bounded result counts.
- Deterministic ordering and 1-indexed display page numbers.
- Sanitized `repr`/diagnostics that avoid full text/hash leakage.

## Not Proven By This UAT
- Live Gemini/Claude generation quality or provider failure handling.
- Streamlit Chat rendering and rerun behavior.
- Visual ColQwen/Qdrant retrieval.
- RAGAS or gold-set retrieval metrics beyond fixture-backed regression coverage.
- End-to-end user-facing chatbot flow, which remains for S03-S05.
