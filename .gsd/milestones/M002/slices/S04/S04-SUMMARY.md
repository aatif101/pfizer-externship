---
id: S04
parent: M002
milestone: M002
provides:
  - A user-visible Streamlit Chat tab that exercises the service-owned RAG answer path.
  - Deterministic fake-Streamlit tests for citations, abstention, provider setup failures, provider runtime errors, and rerun state.
  - App startup/wiring proof that the Chat tab is reachable without live provider credentials.
requires:
  - slice: S01
    provides: Repeatable retrieval index metadata and index state used by the RAG service path.
  - slice: S02
    provides: Hybrid text retriever result contract with document/page/snippet/score evidence and weak-evidence behavior.
  - slice: S03
    provides: Public answer service DTOs, evidence gating, fake provider support, and lazy Gemini provider seam consumed by the Chat renderer.
affects:
  - S05
key_files:
  - src/dashboard/chat.py
  - src/app.py
  - src/dashboard/__init__.py
  - tests/test_chat_dashboard.py
  - tests/test_app.py
key_decisions:
  - Use injectable `provider_factory` and `answer_fn` seams for offline UI tests while defaulting to lazy Gemini provider construction on submit.
  - Store only bounded assistant payloads, service-owned citation fields, and safe diagnostics in Streamlit session state.
  - Keep the Chat tab as a thin UI integration over `src.rag` instead of implementing retrieval/generation in Streamlit.
patterns_established:
  - Rerun-safe Streamlit Chat state uses stable session keys and replays existing turns without triggering old prompts.
  - Diagnostics are user-visible but bounded to status/reason/run/provider/trace/top-score/citation-count/evidence/error-class fields.
  - Provider setup and runtime failures are rendered as safe UI states, not import-time failures or raw exception dumps.
observability_surfaces:
  - Visible Chat diagnostics for answer status, reason code, run ID, provider name, trace ID, top score, citation count, evidence reason, and safe error class.
  - Provider setup/error rendering that distinguishes abstention from provider failures without leaking secrets.
drill_down_paths:
  - .gsd/milestones/M002/slices/S04/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S04/tasks/T02-SUMMARY.md
  - .gsd/milestones/M002/slices/S04/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-05-20T23:31:58.222Z
blocker_discovered: false
---

# S04: Streamlit Chat User Loop

**Delivered the real Streamlit Chat tab over the service-owned RAG contract with rerun-safe chat state, cited answers, abstentions, and safe provider/error diagnostics.**

## What Happened

S04 replaced the Chat placeholder with a dedicated dashboard module, `src/dashboard/chat.py`, that delegates to `src.rag` rather than duplicating retrieval or generation logic in the UI. The renderer initializes stable Streamlit session-state keys, replays prior user and assistant turns across reruns without re-answering old prompts, constructs the answer provider lazily only when a fresh prompt is submitted, and supports injectable `answer_fn`/`provider_factory` seams for deterministic offline tests. Answered results render `AnswerResult.answer_text` and service-owned citations only, including filename, 1-indexed page number, snippet, and bounded score display. Abstentions and provider/setup failures render safe user-actionable messages plus compact diagnostics for status, reason, run ID, provider, trace ID, top score, citation count, evidence reason, and safe error class without exposing raw provider payloads, raw exceptions, full page text, image blobs, content hashes, or secrets. The app entrypoint now imports Chat and Compliance renderers from the dashboard package and calls `render_chat_tab(get_settings().db_path)` from the Chat tab while preserving app startup safety and the Langfuse availability guard. Tests cover answered citations, unrelated abstention, provider configuration redaction, provider error safety, no repeated answer call on rerun, app startup/wiring, RAG service behavior, Gemini provider seam, retrieval, retrieval CLI, and existing compliance dashboard behavior.

## Verification

Fresh closeout verification used the required Python 3.11 virtual environment command through `gsd_exec`: `venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_retrieval_cli.py tests/test_compliance_dashboard.py`. It passed with exit code 0: 62 tests passed in 11.88s. Task-level evidence also passed: T01 focused Chat/service/contract suite with 18 passed, T02 Chat/app/compliance suite with 11 passed, and T03 full S04 regression proof with 62 passed plus a static fixture-safety check confirming no prohibited local artifact paths, network-client imports, or direct environment dependencies in the regression test set. Operational readiness: health signal is visible Chat diagnostics and app startup smoke; failure signals include abstention/provider setup/error diagnostics; recovery procedure is to build/refresh the retrieval index or configure provider credentials/environment and resubmit; monitoring gaps are deferred to S05 milestone-level operational proof/tracing.

## Requirements Advanced

- R005 — Adds the user-facing Chat loop for grounded Q&A with citations and safe abstention over the existing service contract.
- R008 — Adds bounded visible diagnostics for retrieval/generation outcomes and provider failures without secret leakage.
- R010 — Provider construction remains lazy and environment-only; tests verify safe redaction boundaries with no live secrets.

## Requirements Validated

None.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

T01 also wired `render_chat_tab` into `src/app.py` and exported it from `src/dashboard/__init__.py`; this was aligned with T02 and did not alter the slice goal.

## Known Limitations

The closeout proof is deterministic and offline; it does not prove a live Gemini call, visual browser interaction, or Langfuse trace ingestion. Missing/stale retrieval indexes still depend on S01-S02 indexing state and S05 will provide milestone-level operational proof.

## Follow-ups

S05 should run the final end-to-end operational proof across CLI indexing, retrieval, answer generation, Chat rendering, abstention, tracing hooks, and failure modes with fixture data and no live secrets.

## Files Created/Modified

- `src/dashboard/chat.py` — New Streamlit Chat renderer with session-state preservation, cited answer rendering, abstention/provider-error handling, and bounded diagnostics.
- `src/app.py` — Wired the Chat tab to `render_chat_tab(get_settings().db_path)` through the dashboard package while preserving startup safety.
- `src/dashboard/__init__.py` — Exports the Chat renderer alongside existing dashboard exports.
- `tests/test_chat_dashboard.py` — Adds deterministic fake-Streamlit tests for answered citations, abstention, redaction, provider errors, and rerun behavior.
- `tests/test_app.py` — Covers Streamlit app startup and Chat tab wiring.
