# S05: Operational Proof and Evaluation Hooks

**Goal:** Prove the Retrieval and RAG Chatbot milestone as an offline, deterministic operational assembly: fixture SQLite pages can be indexed by the real CLI, retrieved through the service-owned evidence gate, answered or safely abstained through the RAG service, rendered in the Streamlit Chat seam, and diagnosed through bounded tracing and failure metadata without live secrets.
**Demo:** After this, a single verification run proves indexing, retrieval, answer generation, Chat rendering, abstention, and operational failures with fixture data and no live secrets.

## Must-Haves

- Owned requirements: R005, R008, R010. Supporting coverage: R007 retrieval/citation proof where it intersects the text-RAG baseline. Success requires: (1) a deterministic S05 test proving CLI build -> retrieval -> answer service -> Chat rendering over fixture data with fake providers only; (2) negative proof for unrelated questions, missing/stale/empty index or provider failures where final assembly can observe them; (3) no live Gemini or Langfuse credentials required; (4) all visible diagnostics, reprs, trace metadata, CLI output, and Chat output exclude API keys, raw provider payloads, full page text, image blobs, docling JSON, and full content hashes; (5) final M002 regression command passes from the project virtual environment.

## Proof Level

- This slice proves: Final-assembly operational proof. Real runtime required: yes for local Python, SQLite, Typer CLI, pytest, and fake Streamlit seams. Human/UAT required: no. The proof must exercise production entrypoints where practical while staying offline and deterministic.

## Integration Closure

Consumes completed S01 SQLite index persistence and CLI status, S02 retrieval and evidence gate, S03 answer service/provider seam, and S04 Chat renderer. This slice introduces no new user workflow beyond final proof and bounded trace metadata. When complete, nothing remains before M002 is usable end-to-end for the offline fixture/demo path; live Gemini and visual ColQwen/Qdrant remain intentionally outside M002 proof.

## Verification

- Adds or verifies bounded operational diagnostics at the index, retrieval, answer, and Chat layers. Future agents should inspect pytest failure messages, retrieval CLI status output, AnswerDiagnostics, Chat diagnostics expander text, and safe Langfuse metadata hooks. Redaction boundary: no secrets, raw provider responses, raw full page text, image blobs, docling JSON, or full corpus hashes in observable surfaces.

## Tasks

- [x] **T01: Add S05 end to end operational proof** `est:2h`
  Expected executor skills: tdd, verify-before-complete.
  - Files: `tests/test_s05_end_to_end_proof.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py tests/test_chat_dashboard.py tests/test_answer_service.py tests/test_retrieval_cli.py

- [x] **T02: Add bounded trace metadata hooks** `est:2h`
  Expected executor skills: observability, tdd, verify-before-complete.
  - Files: `src/retrieval/indexer.py`, `src/retrieval/retriever.py`, `src/rag/service.py`, `tests/test_tracing.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_tracing.py tests/test_retriever.py tests/test_answer_service.py tests/test_retrieval_cli.py

- [x] **T03: Run final M002 operational regression** `est:45m`
  Expected executor skills: test, verify-before-complete.
  - Verify: venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py tests/test_retrieval_cli.py tests/test_retriever.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_chat_dashboard.py tests/test_app.py tests/test_tracing.py

## Files Likely Touched

- tests/test_s05_end_to_end_proof.py
- src/retrieval/indexer.py
- src/retrieval/retriever.py
- src/rag/service.py
- tests/test_tracing.py
