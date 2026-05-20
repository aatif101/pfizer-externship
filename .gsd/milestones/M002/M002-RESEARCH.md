# M002 Research: Retrieval and RAG Chatbot

**Research date:** 2026-05-20  
**Research lane:** milestone-level strategic research  
**Target reader:** roadmap planner for M002 slicing

## Executive Summary

M002 should be sliced around proving the grounded trust loop before adding retrieval sophistication. The existing codebase already has a strong M001 foundation: SQLite stores `documents` and 0-indexed `pages` with page text and images; extraction has typed provider seams, sanitized errors, exact-span validation, idempotent repository writes, Typer CLIs, and Streamlit dashboard adapter tests. The Chat tab is still only a placeholder in `src/app.py`, and there are no retrieval modules, retrieval/index tables, RAG provider interfaces, or Chat UI helpers yet.

The most important first proof is not dense retrieval or Gemini. It is: given realistic SQLite `pages.page_text`, build a repeatable index, retrieve page-level evidence, assemble short verbatim citations, and return either a grounded answer or an explicit abstention through a service contract that can be tested offline. Once that contract is stable, add Gemini as a live answer provider behind the same lazy/offline-safe pattern already used by `src/extraction/gemini.py`, then wire the service into the Streamlit Chat tab.

## Existing Codebase Findings

### Strong foundations to reuse

- `src/db/schema.py` initializes the core SQLite schema and already includes idempotent migration style for extraction columns. M002 should extend this pattern for retrieval/index metadata instead of creating ad hoc files or in-memory state only.
- `src/db/queries.py` provides parameterized helpers and typed DTOs:
  - `DocumentMetadata`
  - `DocumentPage`
  - `LoadedDocumentPages`
  - `load_document_pages(db_path, doc_id, include_image_bytes=False)`
  - `list_documents(db_path)`
- Existing page numbering convention is clear: persisted `pages.page_num` is 0-indexed; UI display converts to 1-indexed labels. Chat citations must follow this same convention internally and display `page_num + 1`.
- `src/extraction/providers.py`, `src/extraction/gemini.py`, and `src/extraction/pipeline.py` are the best pattern library for M002:
  - provider protocols live in a dependency-light module;
  - live provider construction is lazy and credential-gated;
  - tests inject fake clients/providers;
  - raw page text, raw provider output, and secrets are not logged;
  - malformed provider output is normalized into safe abstention/failure results.
- `src/extraction/cli.py` shows the desired Typer CLI style: import-safe module, `build_provider` seam, safe operator output, deterministic document ordering, and non-secret summaries.
- `src/dashboard/compliance.py` shows the right Streamlit architecture: UI renderer delegates to pure/load/format helpers that are independently tested with a fake `st` object.
- `tests/test_s05_end_to_end_proof.py` is the best model for M002 final proof: create a realistic PDF, ingest through the real pipeline, use a fake provider for deterministic behavior, assert persisted data and UI formatting. M002 needs an analogous final assembly proof from SQLite pages to chat answer/citations.

### Missing pieces

- `src/app.py` Chat tab is only an `st.info` placeholder.
- No retrieval package exists yet (`src/retrieval` or `src/rag`).
- No retrieval/index metadata tables exist in `src/db/schema.py`.
- `pyproject.toml` does not yet include M002 retrieval dependencies such as `bm25s`, `sentence-transformers`, `scikit-learn`, or a reranker package. The current venv confirms `bm25s`, `sentence_transformers`, `sklearn`, and `google.genai` are not importable, while `numpy`, `scipy`, and `streamlit` are present.
- There is no CLI for indexing pages.
- There is no answer-generation provider seam for chat; the only Gemini seam is extraction-specific.
- `src/tracing.py` has Langfuse v3 guardrails and notes retrieval in comments, but retrieval/generation trace events are not implemented yet.

## Technology/Dependency Findings

### Recommended baseline stack for M002

- **Sparse retrieval:** `bm25s` over page/chunk text. It matches the project stack recommendation and is a pragmatic local baseline with sparse-matrix performance. It is not currently installed.
- **Dense retrieval:** `sentence-transformers` with a small CPU-friendly embedding model such as `BAAI/bge-small-en-v1.5` or similar. The stack context recommends this class of model for Phase 1 text RAG. It is not currently installed.
- **Fusion/reranking:** Start with deterministic score fusion such as reciprocal-rank fusion or normalized score fusion before adding a cross-encoder. A cross-encoder reranker is useful but should not be the first risk unless recall/precision is poor.
- **Persistence:** Keep retrieval metadata in SQLite for M002. Avoid Qdrant/ColQwen in this milestone unless explicitly re-scoped; R006 should remain active/future or advisory for later visual retrieval.
- **Generation:** Mirror `GeminiSDFExtractionProvider` with a chat/generation provider for `gemini-2.5-flash`, but keep deterministic fake providers as the default automated proof path.

### Dependency caution

Adding `sentence-transformers` will pull a much heavier ML stack than the current local app. Plan a slice specifically for dependency/installation verification under `./venv/Scripts/python.exe`, because R009 says global Python 3.14 is not supported. If dependency weight becomes a blocker, the first retrieval slice can still prove the service/citation/abstention contract with BM25-only and a dense retriever interface stub, then add dense embeddings in the next slice.

## Boundary Contracts That Matter

### Retrieval index contract

A good M002 retrieval index boundary should answer:

- Which SQLite corpus snapshot was indexed?
- Which documents/pages/chunks are represented?
- Which retriever components were built (`bm25`, `dense`, or both)?
- Whether the index is missing or stale relative to current `documents`/`pages`.
- How to rebuild deterministically from CLI.

Suggested metadata shape:

- `retrieval_indexes` or `retrieval_index_runs`: `index_id`, `created_at`, `status`, `source_page_count`, `source_doc_count`, `config_json`, `error_reason`.
- `retrieval_chunks`: `chunk_id`, `doc_id`, `page_num`, `chunk_index`, `text`, `text_hash`, possibly `token_count`/`char_count`.
- Optional later: persisted dense vectors can be external files or BLOBs, but for M002 keep this simple unless tests require cross-process reuse of dense indexes.

### Retrieval result contract

Use a typed DTO independent of Streamlit and Gemini:

- `doc_id`
- `filename`
- `page_num` internal 0-indexed
- `page_label` or display helper for 1-indexed UI
- `chunk_text` or `page_text` excerpt source
- `snippet` that is verbatim and present in `page_text`
- `score`, `score_breakdown`, `retriever_sources`
- `text_hash`/`chunk_id` for diagnostics

The citation assembler should own snippet selection, not the LLM. The model can cite evidence IDs, but the service should render citations from trusted retrieval DTOs.

### RAG answer contract

Use a pure service result that the UI simply renders:

- `status`: `answered`, `abstained`, or `error`
- `answer`: concise answer or abstention message
- `citations`: tuple/list of citation DTOs; empty for weak evidence abstention
- `diagnostics`: non-secret metadata such as `retrieval_count`, `top_score`, `provider_name`, `trace_id`, `reason_code`

Abstention should happen before live generation if evidence is missing/weak/off-topic. Provider failures should become safe `error` results or typed exceptions, not fabricated answers.

### Provider contract

Create a generation-specific protocol rather than reusing extraction provider DTOs directly. It should accept a question plus curated evidence contexts and return either structured answer text or a typed provider failure. Tests should use a fake provider that intentionally tries malformed/unsupported outputs to prove the service enforces citations itself.

## Strategic Slice Ordering

### Slice 1: SQLite corpus and index metadata foundation

**Goal:** Build a repeatable indexing command over existing SQLite pages without involving Gemini or Streamlit.

Recommended scope:
- Add retrieval metadata/chunk tables via `src/db/schema.py` migration style.
- Add query helpers to list indexable pages with document filenames and non-empty page text.
- Add text normalization/chunking and snippet utilities.
- Add Typer CLI command such as `python -m src.retrieval.cli build-index --db-path ...`.
- Tests: empty corpus, no page text, deterministic chunk rows, missing/stale index status.

Why first: it removes ambiguity around persistence and gives later slices a stable corpus boundary.

### Slice 2: Deterministic retriever and citation assembly

**Goal:** Prove page/chunk retrieval and citation evidence without generation.

Recommended scope:
- Implement BM25-first retrieval; add dense interface if dependency is ready, but do not block on dense initially.
- Return typed retrieval result DTOs with filename/page/snippet.
- Implement evidence gating thresholds and off-topic/no-hit abstention logic.
- Tests: query retrieves expected page, citations are 1-indexed in display, snippets are short/verbatim, weak query abstains.

Why second: this is the highest trust risk. If retrieval/citation fails, generation only hides the problem.

### Slice 3: RAG service with fake provider and strict abstention

**Goal:** Prove the service-level answer contract offline.

Recommended scope:
- Add `src/rag` or `src/chat` service modules with provider protocol, fake provider tests, and answer result DTOs.
- Enforce no answer when evidence gate fails.
- Ensure citations are assembled from retrieval results, not invented by provider output.
- Tests: normal answer, off-topic abstention, provider malformed output, provider failure, no secret/page-text leakage in diagnostics.

Why third: it creates the contract the Streamlit UI and live Gemini provider can share.

### Slice 4: Gemini live generation provider

**Goal:** Add optional live answer generation without making tests or imports require credentials.

Recommended scope:
- Mirror `src/extraction/gemini.py`: lazy client creation, `GEMINI_API_KEY` config, model setting, JSON or structured output, temperature 0, bounded retry.
- Consider adding a separate setting such as `rag_gemini_model` only if extraction and chat need to diverge; otherwise reuse `gemini_model` initially.
- Tests with fake Gemini client: valid response, malformed response, retryable failures, missing credentials safe failure.

Why fourth: this is important for the demo, but deterministic grounding should be proven first.

### Slice 5: Streamlit Chat tab integration

**Goal:** Make the user-visible loop work in `src/app.py` while keeping logic testable.

Recommended scope:
- Create `src/dashboard/chat.py` analogous to `src/dashboard/compliance.py`.
- Use `st.chat_input`, `st.chat_message`, session-state history, and clear index/corpus status messages.
- Render answer and citations with filename, Page N, and snippet.
- Surface missing index/empty corpus/missing credentials distinctly.
- Tests with fake Streamlit and fake service; app smoke test should continue to pass without credentials.

Why fifth: the UI should be a thin renderer over a stable service, not the place where retrieval and provider decisions live.

### Slice 6: Final integrated proof and calibration

**Goal:** Prove the full path from realistic PDF ingestion to Chat answer/citations and abstention.

Recommended scope:
- Add M002 equivalent of `test_s05_end_to_end_proof.py`.
- Create or reuse a realistic text PDF, ingest it, build retrieval index, ask a supported question, assert cited answer with filename/page/snippet.
- Ask an unsupported/off-topic question and assert explicit abstention with no fabricated citations.
- Run via `./venv/Scripts/python.exe -m pytest`.

Why last: it validates the user-visible acceptance criteria without requiring live Gemini.

## Requirement Assessment

### Table stakes for M002

- **R005** is the primary contract and should be fully validated by M002: grounded natural-language Q&A, page-level citations, and abstention.
- **R008** should be partially advanced: retrieval/generation operations should expose non-secret diagnostics and optional Langfuse metadata, but Langfuse must remain non-fatal.
- **R009** is a hard constraint: all verification should use the project Python 3.11 venv, especially after adding ML dependencies.
- **R010** is a hard constraint: Gemini credentials must remain out of Git, and tests/imports must not require secrets.

### Likely omission/candidate requirement

Candidate requirement for user approval, not silently binding: **Persist and validate retrieval index state**. The milestone context already calls for persisted index metadata, but `.gsd/REQUIREMENTS.md` does not have a dedicated requirement for repeatable indexing/staleness visibility. This could remain under R005, but a launchability/operability requirement would make it easier to validate.

Suggested wording if promoted: “Provide a repeatable local retrieval-index build/refresh flow that records index status and clearly reports missing or stale indexes before chat answers are generated.”

### Overbuilt risk

- Treating **R006 visual retrieval** as mandatory for M002 would overbuild the milestone and delay the grounded text RAG loop. Keep R006 active/future unless planning explicitly splits a later visual retrieval slice.
- Full RAGAS metrics and dashboard evaluation belong to **R007/M003**. M002 should include smoke metrics/tests for retrieval/citation correctness, not a full evaluation platform.

## Failure Modes That Should Shape Planning

- **Stale/missing index:** Chat could answer from outdated corpus or crash. Build staleness checks early.
- **Empty page text:** Docling may produce weak text for scanned/stamped docs. Retrieval should fail safe with a clear abstention/setup message.
- **Snippet drift:** If snippets are generated by the LLM or post-processed loosely, citations may not be verbatim. Keep snippet extraction deterministic and verify snippet substring against page text.
- **Score threshold miscalibration:** Too strict means every query abstains; too loose means hallucination risk. Start with deterministic tests and expose thresholds/config in diagnostics.
- **Heavy dense dependencies:** `sentence-transformers` may slow install/startup and complicate Windows local dev. Slice dependency verification separately.
- **Provider output hallucinated citations:** Do not trust provider citations; citations should be derived from retrieval evidence IDs.
- **Streamlit reruns/history:** Store chat history and service initialization in `st.session_state`; avoid expensive index rebuilds on every rerun.
- **Secret/document text leakage:** CLI and diagnostics should follow extraction CLI patterns: print doc IDs, counts, reason codes, provider names, trace IDs, not page text or raw responses.

## Skill Discovery Notes

Installed relevant skills from `<available_skills>`:
- `api-design` may help if the RAG service/provider contracts need a formal interface review.
- `observability` is relevant for retrieval/generation diagnostics and Langfuse-safe metadata.
- `decompose-into-slices` is relevant for roadmap planning after this research.
- `write-docs` could help later for README/demo instructions.

External skill search results (do not install automatically):
- Streamlit: promising `streamlit/agent-skills@developing-with-streamlit` (about 1.3K installs). Install command: `npx skills add streamlit/agent-skills@developing-with-streamlit`.
- SQLite: broad `martinholovsky/claude-skills-generator@sqlite database expert` (about 1.6K installs), but relevance is generic. Install command: `npx skills add martinholovsky/claude-skills-generator@sqlite-database-expert`.
- `bm25s`: no skills found.
- `sentence-transformers`: `davila7/claude-code-templates@sentence-transformers` (about 363 installs) and `orchestra-research/ai-research-skills@sentence-transformers` (about 214 installs). These may be useful if dense retrieval implementation stalls, but are not essential for the first BM25/service slices.
- Gemini API: `google/skills@gemini-api` (about 4.3K installs) and `google-gemini/gemini-skills@gemini-interactions-api` (about 3.7K installs). Install command examples: `npx skills add google/skills@gemini-api`, `npx skills add google-gemini/gemini-skills@gemini-interactions-api`.

## Concrete Recommendations for the Roadmap Planner

1. Do not start with Streamlit UI or Gemini. Start with persisted corpus/index metadata and deterministic retrieval/citation proof.
2. Keep all page numbers internal 0-indexed and convert only at display/citation rendering.
3. Introduce a `src/retrieval` package and a `src/rag` or `src/chat` service package rather than putting logic in `src/app.py`.
4. Use the extraction provider pattern almost verbatim for Gemini chat generation: lazy credential checks, fake clients in tests, sanitized errors.
5. Make the final slice prove both supported answer and unsupported abstention from a realistic ingested SQLite corpus.
6. Treat dense embeddings and reranking as quality improvements after BM25/citation/abstention are working; if dependencies are heavy, do not let them block the core trust loop.
7. Keep R006 visual retrieval out of the baseline implementation unless the user explicitly re-scopes M002.
