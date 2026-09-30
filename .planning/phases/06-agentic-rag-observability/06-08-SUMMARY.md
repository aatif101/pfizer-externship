---
phase: 06-agentic-rag-observability
plan: 08
subsystem: dashboard
tags: [streamlit, chat, langgraph, langfuse, hitl, rag-03, obs-01, hitl-01, d-03]

requires:
  - phase: 06-01
    provides: answer_question_agentic LangGraph pipeline
  - phase: 06-03
    provides: trace_session, PHASE_TAGS, flush_traces
  - phase: 06-04
    provides: fail-closed Claude critic, generation spans
  - phase: 06-06
    provides: Review tab and traced HITL submit
provides:
  - Chat tab defaults to the agentic pipeline, with a session toggle back to the linear baseline (D-03)
  - Specific hints for retrieval_exhausted, critic_rejected and critic_error
  - Agentic diagnostics (pipeline, retrieval_rounds, regeneration_count, sub_query_count, critic_verdict, critic_score)
  - Each chat submit runs in trace_session(phase=PHASE_TAGS[pipeline], session_id, tags=('chat',)) and flushes afterwards
  - Human-verified live run on Windows (Task 2)
affects: [phase 7 benchmark]

actuals:
  tasks: 2
  commits: 3

key-files:
  modified:
    - src/dashboard/chat.py
    - tests/test_chat_dashboard.py
    - tests/test_dashboard_chat_tab.py

requirements-completed: [RAG-03, OBS-01, HITL-01]
---

# 06-08 Summary: Chat agentic default + live human verification

Task 1 (code) landed on WSL in 25d2c07 (failing tests) and c9101e7 (implementation). Task 2, the blocking human-verify checkpoint, was run live on Windows on 2026-09-30 against `compliance.db` (5 docs, 78 indexed pages). The Windows offline suite matched WSL: `pytest -q -m "not gpu"` gave 610 passed, 7 skipped, 0 failed.

## Live verification (Task 2)

Question used: "What is the expiry date and the manufacturing date of the Global Life Sciences Solutions Certificate of Quality?"

| # | Check | Result |
|---|-------|--------|
| 1 | Agentic chat, toggle on | PASS. Answered "Date of Manufacture: 20210126 Expiration Date: 20230126" with 5 citations (top: Example 3 p3, score 8.0). pipeline=agentic, retrieval_rounds=1, regenerations=0, sub_query_count=3, critic_verdict=supported, critic_score=1.0 |
| 2 | Off-corpus "What is the CEO's salary?" | PASS. Abstained with reason_code=retrieval_exhausted, retrieval_rounds=3, evidence_reason=no_match, plus the re-search hint |
| 3 | ANTHROPIC_API_KEY blank | PASS. Abstained with reason_code=critic_error, safe_error_class=CriticConfigurationError; the hint names ANTHROPIC_API_KEY and CRITIC_PROVIDER=gemini |
| 4 | Toggle off | PASS. pipeline=linear, same dates, 5 citations |
| 5 | Review tab | PASS. Queue of 17 (13 abstained, 4 low-confidence), each with its page image. Corrected Colder Products (144fc1ed53c972f0) expiry_date to 2028-12-19 on page 1. The queue dropped to 16, the extraction_reviews row was written, and compliance_records was updated with risk recomputed (green, compliant) |
| 6 | Langfuse | PASS. See traces below |

The phase2 tag was observed on both traces.

### Traces

- Chat (agentic, supported): https://us.cloud.langfuse.com/project/cmq8nr6ix03qdad0da7rb962d/traces/bb72531aa6282ae55ecfd152caeeedf0
  - Tags: agentic, chat, evidence, phase2, rag, retrieval
  - Root span rag.agentic, with children agent.decompose, agent.retrieve, agent.evaluate, agent.draft, agent.critique and agent.finalize
  - generation.aux (gemini-2.5-flash, 75/31 tokens), generation.draft (gemini-2.5-flash, 2150/26 tokens) and generation.critique (claude-sonnet-4-6, 2365/27 tokens). Input and output are masked on every generation
- Review: https://us.cloud.langfuse.com/project/cmq8nr6ix03qdad0da7rb962d/traces/0e947fd121632a748d4ec83616016062
  - Root span hitl.review, tags hitl, phase2, review

## Deviations and notes

- **sub_query_count was 3, not the 2 the handoff expected.** The vendor + document-type phrasing added a third sub-query. The answer was still correct and supported, so this is not treated as a failure.
- **The Colder correction is a demo value.** None of the queued documents prints an explicit expiry date. 2028-12-19 is derived from the stated 3-year shelf life and the 19-Dec-2025 release date (the manufacture date is redacted), and the reviewer note says so. The pre-verification DB was backed up locally.
- **Environment gotcha.** A Claude Code session exports `ANTHROPIC_API_KEY=""`, which pydantic-settings lets override `.env`, so the critic failed closed. The dashboard has to be started with the variable cleared. Separately, an org-level (non-workspace-scoped) Anthropic key returns a 400 that asks for an `anthropic-workspace-id` header, so a workspace-scoped key is required.

## Follow-ups (not blocking)

1. Agentic chat diagnostics show the Gemini response id as "Trace ID", not the Langfuse trace id, and `extraction_reviews.trace_id` is stored as NULL even though the hitl.review trace exists. The dashboard therefore can't link to its own traces.
2. When the critic fails, the generation.critique span's statusMessage carries the raw provider error body (for example the Anthropic 400 JSON). The provider boundary is meant to expose only the exception class name.
