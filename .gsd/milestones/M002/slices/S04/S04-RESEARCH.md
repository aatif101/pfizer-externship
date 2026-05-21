# S04 Research: Streamlit Chat User Loop

## Summary

S04 is a targeted integration slice, not a new RAG architecture slice. S01-S03 already provide the retrieval index, evidence gate, and `src.rag` answer contract; the missing piece is Streamlit-facing glue that preserves rerun state, builds/uses the answer provider lazily, and renders answered/abstained/provider-error outcomes clearly. The recommended implementation is to add a `src/dashboard/chat.py` module analogous to `src/dashboard/compliance.py`, then make `src/app.py` delegate the Chat tab to `render_chat_tab(get_settings().db_path)`.

The highest-risk behavior to prove first is the full UI loop state transition: seeded indexed SQLite corpus + fake provider + chat input => Streamlit state contains user and assistant turns, assistant answer is rendered with filename/page/snippet citations, and unrelated questions render abstention with no citations. Streamlit 1.56.0 includes `streamlit.testing.v1.AppTest`, but local dashboard tests already use a lightweight fake `st` object; either can work. For deterministic unit coverage, fake-`st` renderer tests are simpler because they can monkeypatch provider construction and `answer_question` directly without launching a separate Streamlit runtime.

## Active Requirements and Constraints

- R005: S04 owns the user-visible grounded Q&A loop. It must render cited answers from `AnswerResult.citations` and explicit abstentions from `AnswerStatus.ABSTAINED`.
- R008: UI diagnostics should expose bounded operational signals only: status, reason code, run ID, provider name, trace ID, top score, citation count, evidence reason, and error class. Do not render secrets, raw provider responses, full page text, full hashes, or image blobs.
- R009: verification should use `venv/Scripts/python.exe`, consistent with prior M002 proof.
- R010: provider credentials remain env-only/lazy. Streamlit startup/import must not require `GEMINI_API_KEY`; provider setup errors must be displayed safely and must not crash unrelated tabs.

## Prior Memory and Architectural Notes

Relevant project memories found:

- `MEM041` / `MEM038`: S04 should consume the service-owned RAG boundary. Retrieval evidence is authoritative, providers receive bounded snippets, and citations come from `RetrievalHit`, not model output.
- `MEM040`: import from public `src.rag` (`answer_question`, DTOs, `build_answer_provider`, `GeminiAnswerProvider`) rather than private prompt/parser helpers.
- `MEM021` / `MEM020` / `MEM022`: dashboard code should remain credential-free/provider-free at import time and should use adapter seams. Missing DB/table state should become deterministic UI states, not tracebacks.
- `MEM034` / `MEM036`: weak retrieval outcomes intentionally return no citation-ready hits; public diagnostics expose compact reason/top-score/hash-prefix style metadata only.

## Skill Discovery

Installed project/user skills directly relevant from `<available_skills>`:

- `observability`: relevant conceptually for safe diagnostics/failure modes. S04 should surface bounded status/reason diagnostics for agents/users without leaking sensitive payloads.
- `frontend-design` / `make-interfaces-feel-better`: available but likely overkill; this slice is primarily functional Streamlit integration, not visual redesign.
- `test` / `verify-before-complete`: relevant to executor closeout, especially because this slice must not claim completion without fresh pytest/Streamlit evidence.

External skill lookup for Streamlit was performed with `npx skills find "Streamlit"`. Promising skills (not installed):

- `streamlit/agent-skills@developing-with-streamlit` — 1.3K installs. Install command: `npx skills add streamlit/agent-skills@developing-with-streamlit`.
- `streamlit/streamlit@debugging-streamlit` — 354 installs. Install command: `npx skills add streamlit/streamlit@debugging-streamlit`.
- `streamlit/streamlit@checking-changes` — 98 installs. Install command: `npx skills add streamlit/streamlit@checking-changes`.

No install is required for S04; local code patterns and Streamlit testing APIs are sufficient.

## Implementation Landscape

### Existing UI entry point

- `src/app.py`
  - Imports `streamlit`, `get_settings`, `render_compliance_tab`, and `verify_langfuse_connection`.
  - Calls `st.set_page_config` at top level.
  - Guards Langfuse connection in `st.session_state.langfuse_ok` to avoid repeated auth checks on rerun.
  - Creates tabs: Compliance, Chat, Eval.
  - Compliance tab already delegates to `render_compliance_tab(get_settings().db_path)`.
  - Chat tab is currently a placeholder `st.info(...)` only.

### Existing dashboard pattern

- `src/dashboard/compliance.py`
  - Keeps display formatting and Streamlit rendering outside `src/app.py`.
  - Has pure-ish adapter functions (`load_compliance_rows`, `format_compliance_rows`) plus `render_compliance_tab`.
  - Handles missing DB/table as deterministic empty state.
  - Tests monkeypatch module-level `st` with `FakeStreamlit` in `tests/test_compliance_dashboard.py`.

Recommended S04 mirror:

- Add `src/dashboard/chat.py` with small pure helpers plus `render_chat_tab(db_path: str | None = None, provider_factory: Callable | None = None, answer_fn: Callable | None = None)` if injection is desired.
- Export `render_chat_tab` from `src/dashboard/__init__.py`.
- Replace Chat placeholder in `src/app.py` with `render_chat_tab(get_settings().db_path)`.

### Existing RAG contract

- `src/rag/__init__.py` exports the intended public contract.
- `src/rag/models.py` defines:
  - `AnswerStatus`: `ANSWERED`, `ABSTAINED`, `PROVIDER_ERROR`.
  - `AnswerReasonCode`: includes empty question, index missing/empty/stale, no match, below threshold, retrieval error, provider exception/config/blank/malformed.
  - `AnswerCitation`: `doc_id`, `filename`, zero-based `page_num`, one-indexed `display_page_num`, `snippet`, `score`.
  - `AnswerDiagnostics`: safe status metadata.
  - `AnswerResult`: `status`, `answer_text`, `citations`, `diagnostics`, `is_answered`.
- `src/rag/service.py::answer_question(db_path, question, provider=..., top_k=...)`:
  - Always runs retrieval first.
  - Does not call provider for weak evidence.
  - Returns abstention for weak/missing/empty/stale/retrieval-error evidence.
  - Returns provider-error for strong evidence but missing provider/provider failures.
  - Service owns citations from retrieval hits.
- `src/rag/providers.py::build_answer_provider(provider)`:
  - `None`/blank returns `None`.
  - `"gemini"` lazily imports/constructs `GeminiAnswerProvider`.
  - Missing Gemini credentials raise `AnswerConfigurationError` when trying to construct Gemini provider without key.

S04 should not reconstruct citations, query retriever internals, or trust model-provided citation text. It should render `AnswerResult` as returned.

### Retrieval/index status surfaces

- `src/retrieval/indexer.py::get_retrieval_index_status(db_path)` reports `MISSING`, `EMPTY`, `STALE`, or `BUILT` with counts and stale reason.
- `src/retrieval/cli.py` already prints compact status/build output and preflights source DB paths to avoid typo-created databases.
- Chat UI can optionally show index health using `get_retrieval_index_status`, but should not rebuild implicitly unless the planner/executor intentionally adds a button. Roadmap wording only requires setup/index errors and refresh actions to be explicit; S04 can point users to `python -m src.retrieval build --db-path ...` rather than building inside Streamlit.

## Natural Seams / Work Units

1. **Chat display/state adapter (`src/dashboard/chat.py`)**
   - Owns `st.session_state` keys for chat history and optional last diagnostics.
   - Initializes keys once (`chat_messages`, possibly `chat_provider_error`, `chat_last_diagnostics`).
   - Renders prior turns on every rerun using `st.chat_message`.
   - Accepts new question with `st.chat_input`.
   - Appends user turn then assistant turn.
   - Uses public `src.rag` imports only.

2. **Provider construction seam**
   - Avoid Gemini/provider construction on import or initial app load when possible.
   - On submit, construct a provider only when `get_settings().gemini_api_key` is present, or call `build_answer_provider("gemini")` and catch `AnswerConfigurationError` into a safe provider-error display.
   - Tests should inject fake provider/factory so no secrets/network are required.
   - If provider is absent and strong evidence exists, `answer_question(..., provider=None)` already returns a typed provider-error.

3. **Result rendering**
   - `ANSWERED`: show assistant answer text and citations. Citation display should include filename, `display_page_num`, short verbatim snippet, and optionally score rounded to 2-3 decimals.
   - `ABSTAINED`: show `result.answer_text` as an explicit refusal. Add a compact setup hint based on `diagnostics.reason_code` (e.g. index missing => run retrieval build; index empty => ingest/index documents; index stale => rebuild index; no match/below threshold => ask a document-grounded question).
   - `PROVIDER_ERROR`: show `result.answer_text` plus safe diagnostics/setup hint (e.g. configure Gemini key or retry). Do not show raw exceptions.
   - Diagnostics can be under an expander/caption, but keep bounded fields only.

4. **App wiring**
   - Update `src/app.py` to import `render_chat_tab` and call it in the Chat tab.
   - Keep `st.set_page_config` first Streamlit call.
   - Preserve existing Langfuse session guard and Compliance/Eval tab behavior.

5. **Tests**
   - Add `tests/test_chat_dashboard.py` for renderer/state behavior with fake `st` and fake answers.
   - Update/extend `tests/test_app.py` only if necessary for startup smoke.
   - Consider one AppTest-based smoke if desired; local probe confirmed `streamlit.testing.v1.AppTest` is available in Streamlit 1.56.0 and supports `chat_input[0].set_value(...).run()`.

## First Proof

Build the first failing/passing proof around the user loop, not around styling:

1. Seed a small SQLite DB with one ingested document/page and build the retrieval index (same helper style as `tests/test_answer_service.py`).
2. Inject a fake answer provider that returns deterministic answer text.
3. Render `render_chat_tab(tmp_db_path)` with fake Streamlit.
4. Simulate question submission (`"Acme supplier compliance approval"`).
5. Assert:
   - user turn persisted in session state;
   - assistant turn persisted and rendered;
   - status is answered;
   - citation includes `acme.pdf`, `Page 1` (from `display_page_num`), and the service-owned snippet;
   - no raw full page tail/hash/provider response appears.
6. Repeat with unrelated question (`"astronomy telescope nebula"`) and assert abstention text, no citations, and reason code `no_match` or `below_threshold` visible only as safe diagnostics.

This proof unblocks confidence that Streamlit reruns, state, citations, and abstention are wired before adding extra UI niceties.

## Verification Plan

Recommended targeted commands during/after S04:

```bash
venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py tests/test_answer_service.py tests/test_rag_contract.py tests/test_retriever.py
```

If an AppTest integration test is added:

```bash
venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py
```

Before slice completion, run a broader non-noisy regression consistent with S03 closeout:

```bash
venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_retrieval_cli.py tests/test_compliance_dashboard.py
```

Manual/demo smoke after implementation (optional, not for automated CI):

```bash
venv/Scripts/python.exe -m src.retrieval build --db-path compliance.db
venv/Scripts/python.exe -m streamlit run src/app.py
```

## Watch-outs and Constraints

- **Do not make `src/app.py` import-time secret-dependent.** `GeminiAnswerProvider` raises `AnswerConfigurationError` when constructed without a key; construct lazily and catch safely.
- **Do not let provider output own citations.** Render citations from `AnswerResult.citations` only.
- **Do not call private RAG helpers.** The public `src.rag` contract is locked by `tests/test_rag_contract.py`.
- **Be careful with Streamlit reruns.** Store serializable/DTO-like chat turns in `st.session_state`, not local variables. Avoid re-answering the last prompt on every rerun.
- **Keep setup errors explicit.** Missing/empty/stale index should tell the user/developer what to do (`python -m src.retrieval build --db-path ...`, ingest documents first, rebuild stale index).
- **Avoid raw leakage in UI.** Diagnostics are safe, but page text/provider/raw errors/full content hashes are not.
- **Do not auto-build the index implicitly unless deliberately planned.** S01 established repeatable CLI setup; implicit Streamlit rebuilds could hide stale/missing states and slow reruns.
- **Testing fake Streamlit needs context-manager support.** `st.chat_message(...)` returns a context manager; the fake object should implement this to capture markdown/error/info calls inside chat messages.

## Sources / Evidence Artifacts

- Memory query: `Streamlit Chat RAG UI citations abstention` returned MEM041, MEM038, MEM040, MEM021, MEM020, MEM034, MEM036.
- Code scan: `.gsd/exec/0238366f-6afb-48d2-b640-184e56377c92.stdout` summarized `src/app.py`, `src/rag/*`, retrieval models, and existing tests.
- Config/retrieval/dashboard scan: `.gsd/exec/ff953aa1-b4bf-4d4a-bbdf-f00cc8fdae8a.stdout` summarized config, indexer, retriever, compliance renderer, fixtures, and `pyproject.toml`.
- Streamlit testing probe: `.gsd/exec/21386eef-4145-4633-a14b-85fa0e57c370.stdout` confirmed Streamlit 1.56.0 and `streamlit.testing.v1.AppTest` availability.
- AppTest chat probe: `.gsd/exec/201984ca-7a65-41a9-a47f-ca73ef3cefd9.stdout` confirmed `chat_input[0].set_value(...).run()` works for chat input tests.
- Skill discovery: `.gsd/exec/5bd47215-04f8-4f1c-b989-48b4a721d91f.stdout` listed Streamlit skills.

## Recommendation

Implement S04 as a thin, tested dashboard integration layer over the existing service contract:

1. Add `src/dashboard/chat.py` with session-state initialization, result rendering helpers, safe setup hints, and injectable answer/provider seams for tests.
2. Wire `src/app.py` Chat tab to `render_chat_tab(get_settings().db_path)`.
3. Add deterministic tests using fake Streamlit/fake provider for answered, abstained, provider-error, missing/stale index messaging, and rerun persistence.
4. Keep all provider credentials lazy/environment-only and all diagnostics bounded.

This path minimizes architectural churn, directly satisfies the S04 user loop, and leaves S05 to add final operational/evaluation proof across CLI + service + UI.