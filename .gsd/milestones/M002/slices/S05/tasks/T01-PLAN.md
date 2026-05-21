---
estimated_steps: 9
estimated_files: 1
skills_used: []
---

# T01: Add S05 end to end operational proof

Expected executor skills: tdd, verify-before-complete.

Why: S05 must prove the milestone's real composition path, not isolated unit contracts. The existing `tests/test_s05_end_to_end_proof.py` is an M001 extraction/compliance proof; preserve that useful coverage and append M002 proof rather than deleting it.

Do: Add deterministic M002 tests that seed a temporary SQLite DB with realistic supplier pages using `init_db`, `insert_document`, `insert_page`, and `mark_document_ingested`; run the real Typer retrieval CLI build command with `CliRunner`; call `answer_question()` with a fake `AnswerProvider`; and render `render_chat_tab()` through the fake Streamlit seam from `tests/test_chat_dashboard.py` or an equivalent local fake. Cover the happy path question, an unrelated question, and a provider failure/configuration error path. Assert production-owned citations contain filename, Page 1, bounded snippet, run ID, provider, trace ID, top score, and citation count. Assert weak evidence abstains with no provider call and no citations. Assert provider failures render safe diagnostics. Include planted forbidden values such as fake API-key text, raw provider payload text, full page tail text, and full content-hash-like strings, and assert they do not appear in CLI output, `repr(result)`, rendered Chat text, diagnostics, or exceptions.

Threat Surface Q3: user question text and page text are untrusted and can attempt prompt injection or leak secrets through diagnostics; tests must prove providers receive bounded snippets only and public outputs remain redacted.
Requirement Impact Q4: re-verifies R005 user-facing Chat loop, R008 visible bounded diagnostics, and R010 fake-provider/offline credential behavior without changing completed slice contracts.
Failure Modes Q5: DB/index missing, weak retrieval evidence, and provider exceptions must become typed abstention/provider-error states rather than crashes or leaked raw messages.
Load Profile Q6: fixture load is tiny, but the contract should not require network, browser, GPU, or live model calls; per operation is one local SQLite fixture, one CLI build, one retrieval/service call, and fake UI rendering.
Negative Tests Q7: unrelated question, provider setup/runtime error, planted secret strings, raw page-tail/full-hash redaction, no citation on abstention, and no provider call for weak evidence.

Done when: The S05 proof test demonstrates CLI indexing, retrieval, generation, Chat rendering, abstention, and provider failure over fixture data with no live secrets and preserves the existing M001 proof.

## Inputs

- `tests/test_s05_end_to_end_proof.py`
- `tests/test_chat_dashboard.py`
- `src/db/schema.py`
- `src/db/queries.py`
- `src/retrieval/cli.py`
- `src/retrieval/indexer.py`
- `src/retrieval/retriever.py`
- `src/rag/service.py`
- `src/rag/models.py`
- `src/rag/providers.py`
- `src/dashboard/chat.py`

## Expected Output

- `tests/test_s05_end_to_end_proof.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py tests/test_chat_dashboard.py tests/test_answer_service.py tests/test_retrieval_cli.py

## Observability Impact

Creates the milestone-level observable proof that CLI output, AnswerDiagnostics, Chat diagnostics, and redaction behavior remain inspectable and safe.
