---
id: T01
parent: S04
milestone: M002
key_files:
  - src/dashboard/chat.py
  - tests/test_chat_dashboard.py
  - src/app.py
  - src/dashboard/__init__.py
key_decisions:
  - Use injectable `provider_factory` and `answer_fn` seams for offline UI tests while defaulting to lazy Gemini provider construction on submit.
  - Store only bounded assistant payloads, service-owned citation fields, and safe diagnostics in Streamlit session state.
duration: 
verification_result: passed
completed_at: 2026-05-20T23:27:12.149Z
blocker_discovered: false
---

# T01: Added the Streamlit Chat renderer with safe diagnostics, service-owned citations, and offline rerun-state tests.

**Added the Streamlit Chat renderer with safe diagnostics, service-owned citations, and offline rerun-state tests.**

## What Happened

Created `src/dashboard/chat.py` as a thin Streamlit integration layer over the public `src.rag` contract. The renderer initializes stable session-state keys, replays prior chat turns on rerun, builds the answer provider lazily only when a fresh prompt is submitted, catches provider setup failures safely, renders answered citations from `AnswerResult.citations` only, renders abstention/provider-error hints by reason code, and exposes bounded diagnostics for answer status, reason code, run ID, provider, trace ID, top score, citation count, evidence reason, and safe error class. Added deterministic fake-Streamlit tests in `tests/test_chat_dashboard.py` covering answered citations, no-match abstention without citations, provider configuration redaction, provider error safety, and no repeat answer call on rerun without a new prompt. Also wired the new renderer into the existing Chat tab in `src/app.py` and exported it from `src/dashboard/__init__.py` so the user loop is reachable from the Streamlit app.

## Verification

Ran the required focused verification command: `venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_answer_service.py tests/test_rag_contract.py`. The first run exposed unsafe UI copy containing the phrase `raw provider payload`; I changed the copy to neutral bounded-diagnostics language. The final required verification passed with 18 tests passing, including the new chat dashboard tests and existing RAG service/contract tests.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_answer_service.py tests/test_rag_contract.py` | 0 | ✅ pass — 18 passed | 4266ms |

## Deviations

In addition to the two planned output files, wired `render_chat_tab` into `src/app.py` and exported it from `src/dashboard/__init__.py` so the Chat tab no longer shows the placeholder.

## Known Issues

None.

## Files Created/Modified

- `src/dashboard/chat.py`
- `tests/test_chat_dashboard.py`
- `src/app.py`
- `src/dashboard/__init__.py`
