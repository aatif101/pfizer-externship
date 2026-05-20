---
estimated_steps: 9
estimated_files: 4
skills_used: []
---

# T01: Implement hybrid retrieval happy path

Expected executor skills/frontmatter: tdd, api-design, verify-before-complete.

Why: S03 and S04 need a stable retrieval contract that turns S01's persisted SQLite page index into citation-ready evidence without exposing raw full page text or introducing model/provider dependencies. This first task should make the positive retrieval path work end-to-end on fixture data.

Do: Add query-facing retrieval DTOs to `src/retrieval/models.py` and create `src/retrieval/retriever.py` with a `HybridTextRetriever` or equivalent API. Normalize questions consistently with S01 text normalization, extract deterministic search terms with a small stopword set, use SQLite FTS5 BM25 candidates when `retrieval_index_page_fts` exists, and fall back to lexical scoring over current indexed pages joined to `pages.page_text` when FTS is unavailable or has no hits. Convert FTS/rank information into positive deterministic scores, add token coverage and phrase/proximity bonuses, tie-break by filename/doc_id/page, and generate 180-240 character query-focused snippets around matched terms. Keep raw page text confined inside repository/retriever internals; public hit DTOs may expose only short snippets, identifiers, filenames, page numbers, scores, and compact score components.

Threat Surface (Q3): the question string is untrusted user input that reaches SQLite FTS and fallback scoring. Use parameterized SQL for joins and sanitize/quote FTS terms so SQL/FTS metacharacters cannot alter queries. No auth or secrets are introduced.

Requirement Impact (Q4): owns R005 and supports R008, R009, R010. Re-verify S01 index repository/indexer behavior because this task reads the same tables and optional FTS rows. Decisions D012-D015 remain aligned.

Failure Modes (Q5): if FTS is unavailable or malformed, fall back to lexical scoring rather than crashing; if indexed page text is absent, use the existing persisted snippet only as a last-resort snippet anchor with a low/zero score; if the database cannot be opened, leave typed safe failure handling to T02.

Load Profile (Q6): shared resource is a local SQLite connection. Per query should use bounded candidate limits and avoid loading unbounded corpus text when FTS returns enough candidates; fallback all-page scoring is acceptable for demo fixtures but should be deterministic and simple.

Negative Tests (Q7): include query punctuation/FTS metacharacters, stopword-heavy questions, and repeated terms; assert no SQL error and no full page text appears in returned diagnostics.

Done when: A fixture database can be initialized, populated with two or more pages, indexed through S01, and queried so the expected supplier document page ranks first with filename, doc_id, display page number 1, positive score, score components, and a compact verbatim snippet containing the queried supplier/compliance term.

## Inputs

- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/retrieval/indexer.py`
- `src/db/schema.py`
- `tests/test_retrieval_indexer.py`
- `tests/test_s05_end_to_end_proof.py`

## Expected Output

- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/retrieval/retriever.py`
- `tests/test_retriever.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_retriever.py -k hybrid

## Observability Impact

Introduces score components and bounded snippet evidence on retrieval hits so future failures can distinguish FTS rank, lexical coverage, phrase bonus, and fallback behavior without logging raw full pages.
