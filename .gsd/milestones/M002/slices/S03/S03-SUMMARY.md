---
id: S03
parent: M002
milestone: M002
provides:
  - Stable `src.rag` service API for S04 Streamlit Chat integration.
  - Lazy Gemini answer provider path for configured demos.
  - Deterministic offline acceptance tests proving answer, abstention, provider-error, and contract behavior.
requires:
  - slice: S02
    provides: Consumed `retrieve_evidence`, `EvidenceGateResult`, `RetrievalHit`, and retrieval reason/status semantics.
affects:
  - S04
  - S05
key_files:
  - src/rag/__init__.py
  - src/rag/models.py
  - src/rag/providers.py
  - src/rag/service.py
  - src/rag/gemini.py
  - src/config.py
  - tests/test_answer_service.py
  - tests/test_answer_provider_gemini.py
  - tests/test_rag_contract.py
key_decisions:
  - Answer service owns citations and derives them exclusively from retrieval hits.
  - Providers receive only bounded snippets and return answer text, not trusted citation metadata.
  - Gemini answer provider construction and SDK import are lazy so default tests/app imports remain offline-safe.
  - Provider and configuration failures surface as typed sanitized diagnostics, not raw exception payloads or responses.
  - `src.rag.__all__` is the S04-facing package contract; prompt/parser/helper internals stay private.
patterns_established:
  - Service-first RAG orchestration: retrieve and gate evidence before invoking any generation provider.
  - Safe result statuses for abstention, retrieval failure, provider failure, and answered paths.
  - Offline fake-provider and fake-client tests for all automated verification.
  - Diagnostics boundary that is useful for UI/ops while excluding secrets and raw corpus/provider payloads.
observability_surfaces:
  - AnswerDiagnostics includes status/reason, run_id, provider name, trace_id, top_score, citation_count, evidence reason, and safe error class.
  - Typed AnswerStatus values distinguish answered, abstained, retrieval-error, and provider-error outcomes for downstream UI and operational proof.
drill_down_paths:
  - .gsd/milestones/M002/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S03/tasks/T02-SUMMARY.md
  - .gsd/milestones/M002/slices/S03/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-05-20T23:07:26.224Z
blocker_discovered: false
---

# S03: Grounded Answer Service and Provider Seam

**Added a deterministic grounded answer service with service-owned citations, safe abstention/provider-error states, and an offline-safe lazy Gemini answer provider seam.**

## What Happened

S03 completes the RAG answer boundary needed before the Streamlit Chat UI. The slice added the `src.rag` package contract with public answer DTOs, diagnostics, provider protocol/errors, `answer_question`, a lazy `build_answer_provider` factory, and `GeminiAnswerProvider`. The service first calls the S02 retrieval evidence gate, treats retrieval as authoritative, and only invokes a generation provider when evidence is strong. For answered questions, citations are attached by the service from `RetrievalHit` filename, 1-indexed page number, snippet, and score; provider output is treated only as answer text and is never trusted for citations. Weak, blank, missing, empty, stale, retrieval-error, provider-exception, and blank-provider-answer paths resolve to typed statuses rather than fabricated citations or crashes.

The Gemini answer adapter was implemented behind an offline-safe seam: imports do not require credentials or the SDK, client construction is lazy unless an injected fake client is supplied, calls use deterministic low-temperature settings, retries are bounded, and failures are converted into sanitized typed errors. Public package contract tests now lock the S04-facing API and keep prompt/helper internals private. Diagnostics expose status, reason, run_id, provider name, trace_id, top_score, citation_count, evidence reason, and safe error class while excluding raw provider responses, API keys, full snippets/page text, image blobs, and full hashes.

Gate coverage: Q3 threat surface is mitigated by using the existing parameterized retriever, bounding snippets before provider calls, owning citations in the service, and sanitizing provider/config failures. Q4 requirement impact advances R005, supports R008 diagnostics, preserves R009 venv verification, and supports R010 secret/data minimization. Operational readiness is represented by typed answer statuses and diagnostics for weak evidence, retrieval errors, stale/missing index states, provider failures, and blank provider answers; recovery is to rebuild/refresh the retrieval index, configure credentials only when using the live Gemini provider, or retry after transient provider failures.

## Verification

Slice-level verification was run through the required closeout-safe surface using `gsd_exec`.

Command: `venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_extraction_provider_gemini.py`

Result: exit code 0, `51 passed in 5.41s`.

Evidence artifact: `.gsd/exec/9250d71d-40d9-45ce-8345-2da79164f430.stdout`.

This proves: strong fixture questions return `AnswerStatus.ANSWERED` with fake-provider text and service-owned citations; off-topic/blank/missing/empty/stale evidence abstains with zero provider calls; provider exceptions and blank provider answers produce safe provider-error statuses without fabricated citations; Gemini answer provider imports offline, constructs only with a key or injected client, uses bounded retries and deterministic settings, and sanitizes failures; the public `src.rag` exports are stable for S04; S02 retriever behavior and existing extraction Gemini provider behavior did not regress.

## Requirements Advanced

- R005 — Implemented the service-level grounded Q&A contract with cited answers and deterministic abstention/provider-error outcomes.
- R008 — Added bounded answer diagnostics suitable for downstream tracing and failure visibility without leaking secrets.
- R009 — Verified the slice through the Python 3.11 project venv command path.
- R010 — Kept provider credentials environment-only/lazy and tested redaction of secrets, raw provider responses, full snippets, and full hashes.

## Requirements Validated

None.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

T01 initially exposed an over-strict redaction assertion that was corrected before task completion. T02 refactored a prior embedded Gemini answer implementation from `src/rag/providers.py` into the planned `src/rag/gemini.py` module instead of adding it entirely from scratch. Final slice behavior matches the plan.

## Known Limitations

Live Gemini behavior is available behind the seam but not exercised with real credentials or network during S03. Streamlit Chat integration and final operational/evaluation proof remain for S04 and S05.

## Follow-ups

S04 should consume the stable `src.rag` API for the Chat tab, render citations/abstentions/provider errors clearly, and preserve Streamlit rerun state. S05 should add final operational proof across CLI indexing, retrieval, answer generation, Chat rendering, tracing hooks, and failure modes.

## Files Created/Modified

- `src/rag/__init__.py` — Exposes the stable public RAG answer DTO, service, provider, and Gemini seam exports.
- `src/rag/models.py` — Defines answer statuses, citations, diagnostics, and result DTOs.
- `src/rag/providers.py` — Defines provider protocol/errors and lazy answer provider factory.
- `src/rag/service.py` — Orchestrates retrieval evidence gating, provider invocation, service-owned citations, and safe statuses.
- `src/rag/gemini.py` — Implements lazy Gemini answer provider adapter with bounded retries and sanitized failures.
- `src/config.py` — Adds configuration descriptions needed by the answer provider seam.
- `tests/test_answer_service.py` — Covers answer service citations, abstentions, diagnostics, and provider failure handling.
- `tests/test_answer_provider_gemini.py` — Covers offline-safe Gemini provider construction, fake-client success, retry/error behavior, and sanitization.
- `tests/test_rag_contract.py` — Locks the public RAG package contract and hidden internals.
