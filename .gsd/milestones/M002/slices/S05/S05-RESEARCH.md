# S05 Research: Operational Proof and Evaluation Hooks

## Scope and Depth

Targeted research. The retrieval, RAG service, and Chat UI surfaces already exist from S01-S04; S05 is primarily an integration/proof and observability-hardening slice. The main unknown is not API design, but whether one deterministic fixture path can prove CLI indexing, retrieval, generation, Streamlit rendering, abstention, provider failures, and tracing/diagnostic hooks without live secrets.

## Active Requirements

- **R005**: S05 should prove the user-facing Chat loop end-to-end over the existing service contract: SQLite pages -> retrieval index -> evidence gate -> answer provider -> service-owned citations -> Chat rendering.
- **R008**: S05 owns operational proof for visible/bounded diagnostics and should add/verify retrieval/generation tracing metadata if needed. Diagnostics must not include secrets, raw provider responses, image blobs, full page text, or full corpus hashes.
- **R010**: S05 must keep provider construction lazy/environment-only. Automated proof must use fake providers and explicitly verify no live Gemini/Langfuse secrets are required or leaked.

## Memory and Prior Architecture Notes

- M002 RAG boundary is service-owned: providers receive only bounded snippets, citations derive from `RetrievalHit`, and typed `AnswerResult` statuses/diagnostics are the public failure surface.
- Retrieval evidence gating is provider-free and deterministic: only `strong_evidence` with `is_strong=True` is citation-worthy; weak outcomes return no hits and expose safe reason/top-score/run/hash-prefix diagnostics.
- Text retrieval remains the M002 baseline; visual ColQwen/Qdrant is out of scope for this slice.
- Final hardening was intentionally deferred after index persistence, retrieval/evidence gating, answer generation, and Chat integration.

## Existing Implementation Landscape

### Retrieval/indexing

- `src/db/schema.py` defines `retrieval_index_runs`, `retrieval_index_pages`, and optional `retrieval_index_page_fts` FTS5 virtual table. `init_db()` also runs idempotent retrieval-table migration.
- `src/retrieval/indexer.py` builds provider-free text indexes from ingested `documents`/`pages`; empty corpus records an `empty` run; non-empty records `built`; status detects `missing`, `empty`, `stale`, and `built`.
- `src/retrieval/cli.py` exposes Typer commands `build` and `status`. It preflights database existence/schema so typo paths do not create empty DBs, emits single-line safe metadata, and exits 0/1/2 for built vs setup states/errors.
- `src/retrieval/retriever.py` implements deterministic FTS + lexical retrieval via `retrieve_evidence()` / `EvidenceGate`. It checks index status before scoring and returns citation-ready hits only for strong evidence.
- Existing tests: `tests/test_retrieval_cli.py`, `tests/test_retrieval_index_repository.py`, `tests/test_retrieval_indexer.py`, `tests/test_retriever.py` cover safe CLI output, stale/missing/empty states, snippet/hash redaction, fallback retrieval, and scoring.

### RAG answer service/provider seam

- `src/rag/service.py` is the no-hallucination boundary. It always retrieves first, never calls a provider for weak evidence, converts weak index/evidence states to `ABSTAINED`, converts provider failures to `PROVIDER_ERROR`, and derives citations from retrieval hits.
- `src/rag/models.py` exposes `AnswerStatus`, `AnswerReasonCode`, `AnswerCitation`, `AnswerDiagnostics`, and `AnswerResult` with only bounded metadata fields.
- `src/rag/providers.py` keeps provider construction lazy; `build_answer_provider('gemini')` imports the live adapter only on demand.
- `src/rag/gemini.py` is offline-safe on import and raises `AnswerConfigurationError` only at construction/call time if `GEMINI_API_KEY` is absent. It accepts injected clients/client factories for deterministic tests.
- Existing tests: `tests/test_answer_service.py`, `tests/test_answer_provider_gemini.py`, `tests/test_rag_contract.py` cover service-owned citations, weak abstention without provider calls, provider exception/blank/malformed mapping, import safety, and redaction.

### Streamlit Chat/UI

- `src/dashboard/chat.py` is a thin UI wrapper over `src.rag`. It stores rerun-safe chat state, builds providers only after `st.chat_input`, supports injectable `provider_factory` and `answer_fn`, renders citations from service payloads, and shows bounded diagnostics in an expander.
- `src/app.py` wires `render_chat_tab(get_settings().db_path)` in the Chat tab and keeps Langfuse connection status in sidebar session state.
- Existing tests: `tests/test_chat_dashboard.py` uses a fake Streamlit object to prove answered citation rendering, abstention rendering, provider setup redaction, provider runtime-error redaction, and no repeated answer call on rerun. `tests/test_app.py` only smoke-starts Streamlit; its import-spec check does not execute `src/app.py` but the Streamlit subprocess does exercise startup.

### Tracing/observability

- `src/tracing.py` pins Langfuse v3 import paths and `verify_langfuse_connection()` never raises. `tests/test_tracing.py` verifies version/import paths and non-raising connection checks.
- Current gap: retrieval/RAG modules do **not** currently have `@observe` spans or explicit trace metadata update hooks, even though `src/tracing.py` still documents retrieval as a major traced function. Only ingestion/DB writer use Langfuse decorators today.
- Existing UI diagnostics already expose status, reason, run ID, provider, trace ID, top score, citation count, evidence reason, and safe error class.

## Natural Seams / Candidate Work Units

1. **End-to-end fixture proof**
   - Target: add or replace M002-specific proof in `tests/test_s05_end_to_end_proof.py` (currently an M001 extraction/compliance final proof).
   - Build a SQLite fixture with two ingested docs/pages using `insert_document`, `insert_page`, `mark_document_ingested`, then call the Typer retrieval CLI `build`, `answer_question()` with a fake provider, and `render_chat_tab()` with fake Streamlit.
   - Prove: build output is safe and `built`; answered question has filename/Page 1/snippet citations; unrelated question abstains with no provider call/citations; provider failure renders safe diagnostics.

2. **Operational failure matrix**
   - Target: same S05 proof test or focused additions to `tests/test_answer_service.py` / `tests/test_chat_dashboard.py`.
   - Cover missing index, stale index, empty corpus, missing provider config, provider exception, and retrieval exception. Most are already unit-tested; S05 should assemble a single deterministic proof of the final user/demo contract.
   - Keep assertions on reason codes (`index_missing`, `index_stale`, `index_empty`, `no_match`, `provider_configuration_error`, `provider_exception`) and negative leak checks.

3. **Tracing/evaluation hooks**
   - Target likely `src/rag/service.py`, `src/retrieval/indexer.py`, `src/retrieval/retriever.py`, and tests.
   - Add no-op-safe Langfuse `@observe` decorators and/or small helper to update current trace with safe metadata only: run ID, status/reason, provider name, top score, citation count, indexed docs/pages, index status, not question text or page snippets.
   - Follow existing `src/pipeline/ingest.py` pattern: try importing `langfuse.decorators.observe/langfuse_context`, define no-op decorator if unavailable, and guard metadata update behind availability.
   - Tests should monkeypatch the local `langfuse_context`/availability or import modules with Langfuse absent if practical; do not require network/auth.

4. **Verification command/documentation hook**
   - Consider adding a tiny script/command only if necessary (e.g. `tests/test_s05_end_to_end_proof.py` may be enough). There is no current project script for `verify-m002`; pyproject only sets pytest defaults.
   - If adding a command, keep it deterministic and fake-provider-only; avoid live Gemini and browser dependencies.

## First Proof / Highest-Risk Unblocker

Start with the S05 end-to-end proof test. It should reveal whether the existing seams compose without changing production code:

1. Seed `tmp_db_path` with realistic supplier text including vendor, approval, expiry, and a distractor/off-topic page.
2. Run `CliRunner().invoke(src.retrieval.cli.app, ['build', '--db-path', tmp_db_path])` and assert exit 0 plus safe metadata/no raw text.
3. Use a fake answer provider that records `AnswerProviderRequest` and returns deterministic answer text/trace ID.
4. Call `answer_question()` for an answerable supplier question and assert:
   - provider called exactly once;
   - request evidence contains no `page_text` attribute;
   - result is `ANSWERED` with citation filename, `display_page_num == 1`, snippet containing source text, run ID, provider, trace ID, top score, and citation count;
   - result repr excludes a planted secret tail/full text/full content hash.
5. Call `answer_question()` for unrelated question and assert `ABSTAINED`, no citations, no provider call.
6. Render Chat with fake Streamlit and injected `answer_fn/provider_factory` and assert visible answer/citation/diagnostics plus abstention/provider-error rendering.

This single proof blocks least on new architecture and gives planners confidence before tracing changes.

## Evaluation Hooks Recommendation

For M002, do not introduce RAGAS or live LLM eval yet. The appropriate evaluation hook is a deterministic fixture contract that records/validates:

- retrieval strong/weak reason code;
- top score and citation count;
- expected cited `(filename, display_page_num)`;
- provider called/not called;
- answer status and sanitized diagnostics.

If a persistent evaluation artifact is needed, use the existing `evaluations` table later, but S05 should avoid expanding schema unless the planner explicitly needs it. The milestone roadmap asks for proof across operational outcomes, not a full evaluation subsystem.

## Verification Findings From Research

Focused current regression command passed:

```bash
venv/Scripts/python.exe -m pytest tests/test_retrieval_cli.py tests/test_retriever.py tests/test_answer_service.py tests/test_chat_dashboard.py tests/test_app.py tests/test_tracing.py
```

Result: **43 passed in 14.17s**.

Recommended S05 closeout command after implementation:

```bash
venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py tests/test_retrieval_cli.py tests/test_retriever.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_chat_dashboard.py tests/test_app.py tests/test_tracing.py
```

If tracing decorators are added, include a static safety check that `src/rag`/`src/retrieval` trace metadata keys do not include `page_text`, `snippet`, `question`, `api_key`, `secret`, `image_blob`, `docling_json`, or full content hashes.

## Constraints and Watch-outs

- Use Python 3.11 via `venv/Scripts/python.exe`; avoid global Python.
- Keep all automated proof offline: no live Gemini, no live Langfuse auth requirement, no network, no browser requirement.
- Do not assert exact floating scores too tightly; existing retriever scoring can vary with FTS5 availability. Assert status/reason and `top_score > 0` for strong evidence.
- FTS5 may be absent in some SQLite builds. Tests should still pass via lexical fallback; do not make proof depend on FTS-specific ordering beyond current deterministic sort.
- Do not leak planted secret strings through `repr(result)`, CLI output, Chat rendered text, diagnostics, exceptions, or trace metadata.
- `tests/test_s05_end_to_end_proof.py` currently covers M001 extraction/compliance, not M002. The planner should decide whether to preserve that test and add a new M002 test in the same file or rename/split; avoid deleting useful M001 coverage unless intentionally replacing with broader final proof.
- `src/app.py` imports Streamlit at top-level and starts tabs immediately under Streamlit execution. Keep app tests headless and time-bounded.

## Skill Discovery

Installed skills directly relevant from the prompt:

- `observability`: useful for R008; apply its principle of agent-first, bounded, actionable failure signals.
- `test` and `verify-before-complete`: useful for building and closing S05 with fresh evidence.
- `agent-browser`: potentially useful only for optional visual Streamlit verification; not required for deterministic S05.

External skill discovery (`npx skills find`) found these promising but **not installed** skills:

- Streamlit: `npx skills add streamlit/agent-skills@developing-with-streamlit` (1.3K installs), `npx skills add streamlit/streamlit@debugging-streamlit` (354 installs).
- Langfuse: `npx skills add langfuse/skills@langfuse` (4.7K installs), `npx skills add langfuse/skills@langfuse-observability` (214 installs).
- SQLite: `npx skills add martinholovsky/claude-skills-generator@sqlite-database-expert` (1.6K installs).
- Typer: `npx skills add vibe-motion/skills@claude-typer` (415 installs), `npx skills add narumiruna/agent-skills@python-cli-typer` (39 installs).
- Pytest: `npx skills add github/awesome-copilot@pytest-coverage` (10.4K installs), `npx skills add manutej/luxor-claude-marketplace@pytest-patterns` (360 installs).

Recommendation: no installation is necessary for this slice; local patterns and existing tests are sufficient. Langfuse skill could help only if S05 expands tracing beyond simple no-op-safe decorator hooks.

## Suggested Planner Decomposition

1. **T01: M002 end-to-end proof fixture** — add deterministic proof across CLI build, retrieval, answer service, Chat rendering, abstention, and provider failure using fake provider/Streamlit.
2. **T02: Trace/evaluation hook hardening** — add no-op-safe observability hooks for retrieval/index/answer boundaries with tests proving bounded metadata and no live Langfuse requirement.
3. **T03: Final operational regression** — run the full M002 proof suite, add any missing failure-mode assertions, and close S05 with evidence.
