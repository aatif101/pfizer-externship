---
estimated_steps: 9
estimated_files: 4
skills_used: []
---

# T03: Export retrieval contract and prove safety regressions

Expected executor skills/frontmatter: tdd, verify-before-complete.

Why: S03 should be able to import one stable provider-free API, and S02 must prove it did not regress S01's indexing/CLI safety or accidentally add heavyweight dependencies/secrets surfaces.

Do: Export the public S02 DTOs and service from `src/retrieval/__init__.py` without exporting raw page-text helpers. Add final contract tests in `tests/test_retriever.py` covering public imports, deterministic ordering/tie-breakers, fallback behavior when FTS is unavailable or returns no rows if feasible, query metacharacter safety, snippet length bounds, 1-indexed display page numbers, score/reason-code stability, and sanitized repr/diagnostics. Run S01 regression tests for repository, indexer, and CLI so table access and status behavior remain intact. Avoid adding dependencies to `pyproject.toml`; if a dependency is truly necessary, justify it in code comments and tests, but the expected path is no dependency change.

Threat Surface (Q3): public imports and repr/loggable DTOs become surfaces later UI/generation code may display. Ensure DTO reprs contain bounded snippets and metadata only, never API keys, provider responses, image blobs, or full page text.

Requirement Impact (Q4): re-verifies R005 and supporting R008-R010 plus S01's safe-output contract. Decisions D012-D015 should remain valid. No roadmap reassessment is expected unless tests reveal S02 cannot meet the fixture contract.

Failure Modes (Q5): if optional FTS setup is absent, fallback tests should still pass; if a query contains SQL/FTS syntax, retrieval should return a weak/no-match result or safe hits, not an exception.

Load Profile (Q6): final tests should keep fixture corpora small but assert top_k bounds so future larger corpora do not accidentally return unbounded hit lists or snippets.

Negative Tests (Q7): SQL-like filenames/page text from existing S01 tests, SQL/FTS-like query strings, overly broad questions, top_k zero/negative or normalization boundary if supported, and stale index after source mutation.

Done when: The final S02 verification command passes and confirms public imports, positive retrieval, weak evidence, fallback, metacharacter safety, snippet bounds, and S01 regression coverage through the project venv.

## Inputs

- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/retriever.py`
- `tests/test_retriever.py`
- `tests/test_retrieval_index_repository.py`
- `tests/test_retrieval_indexer.py`
- `tests/test_retrieval_cli.py`
- `pyproject.toml`

## Expected Output

- `src/retrieval/__init__.py`
- `src/retrieval/models.py`
- `src/retrieval/retriever.py`
- `tests/test_retriever.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_retriever.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py

## Observability Impact

Hardens the public inspection contract by proving exports and repr-like diagnostics stay bounded and sanitized while preserving S01 CLI/status surfaces.
