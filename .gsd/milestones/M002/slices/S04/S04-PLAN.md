# S04: Streamlit Chat User Loop

**Goal:** Deliver the Streamlit Chat user loop over the existing service-owned RAG contract: a compliance officer can ask a document-grounded question in the Chat tab, see a concise answer with service-owned filename/page/snippet citations, ask an unrelated question, and see a clear safe abstention or provider setup error without secrets or raw payload leakage.
**Demo:** After this, a compliance officer can open the Chat tab, ask a supplier-document question, see a concise answer with citations, ask an unrelated question, and see a clear abstention.

## Must-Haves

- Chat tab delegates to a dedicated dashboard module instead of placeholder text.
- Streamlit reruns preserve prior user and assistant turns without re-answering old prompts.
- Answered results render `AnswerResult.answer_text` plus citations from `AnswerResult.citations` only, including filename, 1-indexed page number, snippet, and bounded score display.
- Abstained and provider-error results render user-actionable safe messages and compact diagnostics for reason/status/run/provider/trace/top-score/citation-count/evidence/error class only.
- Provider construction is lazy and environment-only; missing Gemini credentials or provider setup failures do not break app import or unrelated tabs.
- Deterministic tests cover answered, unrelated abstention, provider-error/setup behavior, diagnostics redaction boundaries, and app startup/wiring with no live secrets.

## Proof Level

- This slice proves: Integration proof. Real Streamlit runtime smoke plus focused fake-Streamlit renderer tests exercise the local SQLite retrieval index, public `src.rag` service contract, Streamlit session-state behavior, and app entrypoint. No human/UAT and no live provider credentials are required.

## Integration Closure

Consumes the S03 public `src.rag` contract (`answer_question`, answer DTOs, provider factory/errors) and S01-S02 retrieval/index state through the service boundary. Introduces the S04 runtime wiring from `src/app.py` Chat tab to `src/dashboard/chat.py`. Leaves S05 to provide final milestone-level operational proof across CLI indexing, service, UI, tracing hooks, and evaluation surfaces.

## Verification

- The Chat UI exposes bounded operational diagnostics in the visible result or an expander/caption: answer status, reason code, run ID, provider name, trace ID, top score, citation count, evidence reason, and safe error class. It must not render secrets, raw provider responses, raw exceptions, full page text, image blobs, full snippets beyond citation snippets, or full content hashes.

## Tasks

- [x] **T01: Add Chat renderer and UI state tests** `est:2h`
  ---
  estimated_steps: 8
  estimated_files: 2
  skills_used:
    - tdd
    - observability
    - verify-before-complete
  ---
  - Files: `src/dashboard/chat.py`, `tests/test_chat_dashboard.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_answer_service.py tests/test_rag_contract.py

- [x] **T02: Wire Chat tab into app entrypoint** `est:45m`
  ---
  estimated_steps: 5
  estimated_files: 3
  skills_used:
    - verify-before-complete
  ---
  - Files: `src/app.py`, `src/dashboard/__init__.py`, `tests/test_app.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py tests/test_compliance_dashboard.py

- [x] **T03: Run S04 regression proof** `est:45m`
  ---
  estimated_steps: 4
  estimated_files: 1
  skills_used:
    - test
    - verify-before-complete
  ---
  - Files: `src/dashboard/chat.py`, `src/app.py`, `src/dashboard/__init__.py`, `tests/test_chat_dashboard.py`, `tests/test_app.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_retrieval_cli.py tests/test_compliance_dashboard.py

## Files Likely Touched

- src/dashboard/chat.py
- tests/test_chat_dashboard.py
- src/app.py
- src/dashboard/__init__.py
- tests/test_app.py
