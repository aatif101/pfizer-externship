---
estimated_steps: 24
estimated_files: 2
skills_used: []
---

# T01: Add Chat renderer and UI state tests

---
estimated_steps: 8
estimated_files: 2
skills_used:
  - tdd
  - observability
  - verify-before-complete
---

Why: The highest-risk part of S04 is not RAG logic; it is the Streamlit rerun/user loop boundary. This task creates the dashboard Chat module as a thin integration layer over the public `src.rag` service and proves state persistence, citations, abstention, provider-error display, and safe diagnostics with deterministic fake-Streamlit tests.

Do:
1. Add `src/dashboard/chat.py` and import only the public `src.rag` contract plus retrieval/index status helpers as needed; do not call private prompt/parser/retriever internals.
2. Implement `render_chat_tab(db_path: str | None = None, provider_factory: Callable | None = None, answer_fn: Callable | None = None)` or an equivalent injectable seam so tests can run without secrets/network.
3. Initialize stable `st.session_state` keys for chat messages and last diagnostics; render prior turns on every rerun; append a user turn and one assistant turn only when `st.chat_input` returns a new prompt.
4. Build a provider lazily on submit. Default behavior should use Gemini only when configured or attempt `build_answer_provider("gemini")` safely; catch `AnswerConfigurationError` and convert it into safe UI/provider-error behavior rather than crashing import or render.
5. Render `AnswerStatus.ANSWERED` with answer text and citations from `AnswerResult.citations` only: filename, `display_page_num`, citation snippet, and a rounded score. Never render provider-supplied citation metadata.
6. Render `AnswerStatus.ABSTAINED` with `result.answer_text`, no citations, and a compact hint based on reason code for missing/empty/stale/no-match/below-threshold states.
7. Render `AnswerStatus.PROVIDER_ERROR` with `result.answer_text`, safe setup/retry hint, and bounded diagnostics only.
8. Add `tests/test_chat_dashboard.py` with a fake `st` that supports `chat_message` as a context manager, `chat_input`, markdown/info/warning/error/caption/expander calls, and `session_state` mutation.
9. Tests should cover: answered question persists user+assistant turns and renders `acme-sdf.pdf`, `Page 1`, and a citation snippet; unrelated question abstains with no citations; provider/setup error is safe and no secret/raw exception/provider payload/full page tail/full hash appears; rerun without a new prompt does not call `answer_fn` again.

Done when: `src/dashboard/chat.py` exists, focused chat tests pass offline with fixture/fake providers, and renderer diagnostics are useful but bounded.

Threat Surface Q3: User questions are untrusted input reaching retrieval and possibly an API provider through `answer_question`; the UI must not echo raw provider failures, secrets, full page text, or hidden hashes. No auth or privilege boundary is introduced.

Failure Modes Q5: Missing DB/index, empty corpus, stale index, weak evidence, provider config failure, provider exception, and malformed provider result must become typed Chat messages rather than Streamlit tracebacks.

Load Profile Q6: One submit performs retrieval plus at most one provider call; reruns should be cheap and must not repeat provider calls for prior prompts. Chat history is session-local and can be bounded or kept modest for demo use.

Negative Tests Q7: Blank/off-topic prompt, missing/stale index diagnostics, provider exception/config failure, and rerun with no prompt should be covered without live credentials.

## Inputs

- `src/rag/__init__.py`
- `src/rag/models.py`
- `src/rag/service.py`
- `src/rag/providers.py`
- `src/retrieval/indexer.py`
- `tests/test_answer_service.py`
- `tests/test_compliance_dashboard.py`

## Expected Output

- `src/dashboard/chat.py`
- `tests/test_chat_dashboard.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_answer_service.py tests/test_rag_contract.py

## Observability Impact

Adds the user-facing Chat diagnostics surface for answer status, reason code, run ID, provider name, trace ID, top score, citation count, evidence reason, and safe error class while enforcing redaction of raw exceptions, secrets, provider responses, full page text, and full hashes.
