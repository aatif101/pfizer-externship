---
id: S03
parent: M004
milestone: M004
provides:
  - Bounded extraction usage observation contract for downstream visual fallback calls.
  - Aggregate extraction usage eval metric names and source-run scoped aggregation.
  - Provider-free cost/token/latency inspection surface for real extraction comparisons.
requires:
  - slice: S01
    provides: Run-scoped extraction identity and history persistence used to key usage observations and source-run scoped eval aggregation.
affects:
  - S04 targeted visual fallback extraction must reuse the observation contract for visual-stage calls.
  - S05 real five document comparison should report extraction usage aggregate metrics alongside quality metrics.
key_files:
  - src/db/schema.py
  - src/eval/repository.py
  - src/extraction/providers.py
  - src/extraction/gemini.py
  - src/extraction/pipeline.py
  - src/eval/operational_metrics.py
  - src/eval/extraction_usage_eval.py
  - tests/test_extraction_usage_observations.py
  - tests/test_eval_db_schema.py
  - tests/test_extraction_gemini_usage.py
  - tests/test_extraction_pipeline.py
  - tests/test_extraction_persistence.py
  - tests/test_extraction_usage_eval_metrics.py
key_decisions:
  - Optional numeric telemetry remains nullable rather than defaulting absent token, cost, or latency values to zero.
  - Gemini 2.5 Flash estimated cost is computed only from known input/output token pricing and known model metadata.
  - Usage observation persistence occurs after extraction run persistence so the run identity parent exists before telemetry rows are inserted.
  - Extraction usage aggregation is provider-free and source-run scoped through existing eval_runs/eval_metrics patterns.
patterns_established:
  - Bounded extraction usage observations mirror the RAG observation repository pattern while using extraction-specific run, document, stage, model, and status dimensions.
  - Provider usage metadata is normalized into DTO fields at the provider boundary and persisted by the pipeline without storing raw prompts or provider payloads.
  - Operational eval metrics omit absent optional telemetry instead of zero-filling unknown values.
observability_surfaces:
  - SQLite `extraction_usage_observations` rows keyed by run_id, doc_id, stage, model, status, latency, tokens, estimated cost, and sanitized error reason.
  - Extraction-prefixed `eval_metrics` rows for aggregate token, cost, and latency families.
  - Targeted pytest gates serve as diagnostic commands for repository, provider, pipeline, and eval aggregation regressions.
drill_down_paths:
  - .gsd/milestones/M004/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S03/tasks/T02-SUMMARY.md
  - .gsd/milestones/M004/slices/S03/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-06-04T23:29:20.722Z
blocker_discovered: false
---

# S03: Gemini extraction usage observations

**Bounded Gemini extraction usage observations now persist for text extraction calls and aggregate into provider-free eval metrics keyed by extraction run.**

## What Happened

S03 added an additive `extraction_usage_observations` SQLite surface indexed by extraction run, document, stage, and status, with repository helpers that accept multiple observations per run/document while rejecting malformed numeric telemetry and avoiding forbidden raw/confidential columns. The Gemini extraction provider now parses SDK-like usage metadata into bounded usage DTO fields, estimates Gemini 2.5 Flash cost only when input/output token data is present for a known model, and leaves cost null for unknown or absent metadata. The extraction pipeline persists exactly one text-stage usage observation after extraction run persistence has created the parent run identity, preserving backwards compatibility for existing provider fakes and extraction persistence behavior. The eval layer now exposes a provider-free extraction usage eval runner that reads bounded observations for a selected source extraction run and writes deterministic global `eval_metrics` rows for latency, token, and cost families without emitting misleading zero metrics for absent optional values.

## Verification

Closeout verification used `gsd_exec` runtime=node only, spawning Windows-native `venv/Scripts/python.exe -m pytest` commands. It first confirmed the S03 plan, task summaries, touched source files, and test files exist, then ran all planned gates successfully: `venv/Scripts/python.exe -m pytest -q tests/test_extraction_usage_observations.py tests/test_eval_db_schema.py` passed; `venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_usage.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py` passed; `venv/Scripts/python.exe -m pytest -q tests/test_extraction_usage_eval_metrics.py tests/test_retrieval_eval_optional_metrics.py tests/test_eval_repository.py` passed. Evidence: gsd_exec 856b7422-a041-40c9-8447-77621f3eed7a exited 0 and reported S03 closeout verification passed.

## Requirements Advanced

- R013 — Implemented bounded Gemini extraction usage observation persistence and aggregate eval metrics for text extraction calls, establishing the contract S04 will reuse for visual calls.
- R017 — Closeout verification used Windows-native `venv/Scripts/python.exe -m pytest` commands through `gsd_exec` runtime=node and did not invoke `/bin/bash` or runtime=bash.

## Requirements Validated

- R013 — Validated by mocked Gemini usage metadata persistence and aggregate eval metric tests across all planned S03 gates; closeout evidence gsd_exec 856b7422-a041-40c9-8447-77621f3eed7a exited 0.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

No live Gemini billing validation was performed, visual fallback observations are not implemented until S04, and the final real five-document cost/quality comparison remains S05 scope.

## Follow-ups

S04 should reuse the same observation contract for visual fallback calls and choose distinct stage values so text and visual usage remain separable. S05 should include extraction usage metrics in the final real-corpus comparison.

## Files Created/Modified

- `src/db/schema.py` — Added the bounded extraction usage observation table and indexes.
- `src/eval/repository.py` — Added repository helpers for insertion/listing of usage observations and metric support.
- `src/extraction/providers.py` — Extended provider result DTOs with optional usage/provider model fields while preserving backward compatibility.
- `src/extraction/gemini.py` — Parsed SDK-like Gemini usage metadata and computed bounded estimated cost for known Gemini 2.5 Flash token usage.
- `src/extraction/pipeline.py` — Persisted one text extraction usage observation per run/document after extraction persistence.
- `src/eval/operational_metrics.py` — Added absent-safe extraction usage aggregation helpers and metric naming support.
- `src/eval/extraction_usage_eval.py` — Added provider-free source-run scoped extraction usage eval runner.
- `tests/test_extraction_usage_observations.py` — Covered schema, repository filters, malformed numeric rejection, and bounded-column guarantees.
- `tests/test_eval_db_schema.py` — Covered additive schema expectations for eval and usage observation tables.
- `tests/test_extraction_gemini_usage.py` — Covered mocked Gemini usage metadata parsing, null behavior, and estimated cost calculation.
- `tests/test_extraction_pipeline.py` — Covered pipeline observation persistence and existing extraction behavior.
- `tests/test_extraction_persistence.py` — Regression coverage for extraction persistence compatibility.
- `tests/test_extraction_usage_eval_metrics.py` — Covered aggregate extraction usage eval metrics and optional-value omission.
