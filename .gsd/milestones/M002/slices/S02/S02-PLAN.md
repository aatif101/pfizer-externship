# S02: Hybrid Retriever and Evidence Gate

**Goal:** Implement a provider-free hybrid text retriever and deterministic evidence gate over the S01 SQLite retrieval index so fixture supplier-document questions return ranked citation-ready page evidence and unrelated or unsafe questions return weak-evidence reason codes.
**Demo:** After this, fixture questions retrieve expected supplier document pages with filename, 1-indexed page number, score, and verbatim snippet, while unrelated questions return a weak-evidence result.

## Must-Haves

- Built indexes can be queried through a retrieval service API without Gemini, Claude, Qdrant, bm25s, sentence-transformers, network, or secrets.
- A supplier-document fixture question returns the expected document page with stable doc_id, filename, 1-indexed display page number, numeric score, compact score diagnostics, and a short query-focused verbatim snippet.
- Empty, missing, empty-index, stale-index, no-match, and below-threshold scenarios return deterministic weak evidence with explicit reason codes and no fabricated citations.
- FTS5 is used when available and fallback lexical scoring works when FTS is unavailable or produces no candidates.
- Public DTOs, CLI/status regressions, and tests do not expose raw full page text, provider responses, API keys, or image blobs.
- Verification passes through the project Python 3.11 virtualenv using Windows-compatible `venv/Scripts/python.exe`.

## Proof Level

- This slice proves: Contract and integration proof: executable pytest coverage exercises the real SQLite source tables, S01 index build/status path, repository candidate access, hybrid scoring, snippet creation, evidence gating, and S01 CLI/index regressions. No human/UAT or live provider is required in this slice.

## Integration Closure

Consumes S01 persisted retrieval_index_runs, retrieval_index_pages, optional retrieval_index_page_fts, `get_retrieval_index_status()`, `normalize_index_text()`, and fixture ingestion/indexing helpers. Introduces the query-facing retrieval/evidence API and exports needed by S03. Streamlit Chat, model generation, provider seams, and final operational proof remain for S03-S05.

## Verification

- Adds diagnosable reason-coded retrieval outcomes (`strong_evidence`, `empty_question`, `index_missing`, `index_empty`, `index_stale`, `no_match`, `below_threshold`, and error/status variants as needed), score components, top score, query terms, run_id/content hash metadata, and bounded snippets. Failure inspection is by service result DTOs and pytest assertions; raw full page text and secrets must remain out of public diagnostics.

## Tasks

- [x] **T01: Implement hybrid retrieval happy path** `est:3h`
  Expected executor skills/frontmatter: tdd, api-design, verify-before-complete.
  - Files: `src/retrieval/models.py`, `src/retrieval/repository.py`, `src/retrieval/retriever.py`, `tests/test_retriever.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_retriever.py -k hybrid

- [x] **T02: Add deterministic evidence gate and weak-result reasons** `est:3h`
  Expected executor skills/frontmatter: tdd, api-design, verify-before-complete.
  - Files: `src/retrieval/models.py`, `src/retrieval/retriever.py`, `tests/test_retriever.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_retriever.py -k evidence

- [x] **T03: Export retrieval contract and prove safety regressions** `est:2h`
  Expected executor skills/frontmatter: tdd, verify-before-complete.
  - Files: `src/retrieval/__init__.py`, `src/retrieval/models.py`, `src/retrieval/retriever.py`, `tests/test_retriever.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_retriever.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py

## Files Likely Touched

- src/retrieval/models.py
- src/retrieval/repository.py
- src/retrieval/retriever.py
- tests/test_retriever.py
- src/retrieval/__init__.py
