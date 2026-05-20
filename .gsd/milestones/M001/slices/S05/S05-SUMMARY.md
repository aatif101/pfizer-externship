---
id: S05
parent: M001
milestone: M001
provides:
  - Realistic offline PDF ingestion to extraction to risk persistence to dashboard adapter proof.
  - Explicit M001 boundary map and requirement-scope clarification.
  - Fresh full regression evidence for M001 validation.
requires:
  []
affects:
  - M001
key_files:
  - tests/test_s05_end_to_end_proof.py
  - .gsd/milestones/M001/M001-ROADMAP.md
  - .gsd/milestones/M001/M001-VALIDATION.md
key_decisions:
  - Use deterministic generated PDF proof rather than the existing sample fixture because the existing fixture persists empty page text.
  - Keep live Gemini/Langfuse optional for S05 proof; the validation gap is integration evidence, not live model accuracy.
  - Treat R005/R006/R007 as future M002/M003 scope and R008 as partial in M001 with broader tracing later.
patterns_established:
  - Use runtime-generated minimal text PDFs for deterministic Docling integration proof when static fixtures do not preserve page text.
  - Keep final-assembly proof offline and credential-free by using the provider protocol seam with grounded exact spans.
observability_surfaces:
  - S05 pytest proof acts as a repeatable inspection surface for the ingestion-to-dashboard chain.
  - Compliance rows continue to persist run_id and trace_id metadata for dashboard inspection.
  - Validation docs now state missing-credential and redaction boundaries for future agents.
drill_down_paths:
  - .gsd/milestones/M001/slices/S05/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S05/tasks/T02-SUMMARY.md
  - .gsd/milestones/M001/slices/S05/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-05-20T19:27:17.489Z
blocker_discovered: false
---

# S05: Validation remediation boundary and end to end proof

**S05 closed M001 validation remediation with a realistic offline end-to-end proof, boundary map, requirement scope clarification, and full regression pass.**

## What Happened

S05 remediated the M001 validation blockers. A new deterministic pytest generates a realistic one-page Supplier Declaration Form PDF, ingests it through the real Docling ingestion path, verifies persisted page text and image output, runs the real extraction pipeline with a credential-free fake provider citing exact spans, persists six field rows plus one compliance row, verifies amber risk and 732-day age metadata, and checks dashboard-facing formatting including Page 1 source labeling and 90% aggregate confidence. The roadmap boundary map now documents S01-S05 producer/consumer contracts, and validation notes now clarify that R005/R006/R007 are future milestone scope while R008 is only partially covered by M001. Fresh closeout verification passed targeted S05, focused regression, and the full 72-test suite.

## Verification

Fresh closeout verification passed: targeted S05 proof test passed, focused ingestion/extraction/dashboard/app regression passed, and full pytest suite passed with 72 tests.

## Requirements Advanced

- R008 — Clarified M001's partial observability boundary: missing credentials remain non-fatal, diagnostics are sanitized, and run/trace metadata is persisted; broader tracing remains future work.
- R009 — All closeout verification used the Python 3.11 project venv command path.
- R010 — S05 proof remained offline and credential-free with no local tokens or provider secrets committed.

## Requirements Validated

- R002 — S05 final-assembly proof ingests a realistic PDF and verifies six grounded extraction fields persisted with source evidence.
- R003 — S05 final-assembly proof verifies persisted amber risk and age_days == 732 from extracted date fields.
- R004 — S05 final-assembly proof verifies dashboard adapter formatting for the persisted compliance row, including vendor, source page label, source span, and confidence display.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

S05 proves the baseline offline final-assembly path with a fake grounded provider, not live Gemini extraction quality, visual retrieval, chatbot Q&A, or production-scale evaluation. The Streamlit UI itself was not manually driven in a browser; S04/S05 automated tests verify the SQLite-backed dashboard adapter/render contract.

## Follow-ups

Later milestones should implement R005 natural-language Q&A, R006 visual ColQwen/Qdrant retrieval, R007 evaluation metrics, and deeper R008 Langfuse tracing across retrieval/generation/evaluation. Docling legacy VLM option deprecation warnings can be addressed in a future dependency/ingestion cleanup slice.

## Files Created/Modified

- `tests/test_s05_end_to_end_proof.py` — Added deterministic realistic SDF PDF final-assembly proof covering ingestion, extraction, persistence, risk, and dashboard adapter formatting.
- `.gsd/milestones/M001/M001-ROADMAP.md` — Filled the M001 boundary map with S01-S05 producer/consumer contracts and requirement scope boundaries.
- `.gsd/milestones/M001/M001-VALIDATION.md` — Added S05 remediation scope update clarifying M001 coverage and future requirement scope.
