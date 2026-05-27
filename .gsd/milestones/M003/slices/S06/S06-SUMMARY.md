---
id: S06
parent: M003
milestone: M003
provides:
  - A bounded SQLite observation contract for S07 Langfuse tracing instrumentation to populate.
  - Deterministic aggregation semantics for faithfulness/relevancy, citation, latency, tokens, and cost.
  - Eval tab formatting for persisted optional metric families without runtime credentials.
requires:
  - slice: S01
    provides: SQLite eval run and metric storage contracts.
  - slice: S02
    provides: Extraction metric computation and persistence baseline.
  - slice: S03
    provides: Retrieval recall/citation eval runner and persisted run history.
  - slice: S04
    provides: Read-only Eval tab over SQLite eval history.
  - slice: S05
    provides: Demo-ready dashboard layout and Eval tab presentation baseline.
affects:
  - S07
  - S08
key_files:
  - src/db/schema.py
  - src/eval/repository.py
  - src/eval/operational_metrics.py
  - src/eval/retrieval_eval_runner.py
  - src/dashboard/eval.py
  - tests/test_eval_db_schema.py
  - tests/test_eval_repository.py
  - tests/test_retrieval_eval_optional_metrics.py
  - tests/test_retrieval_eval_runner.py
  - tests/test_extraction_eval_metrics.py
  - tests/test_dashboard_eval_tab.py
key_decisions:
  - Persist optional RAG/eval observations as bounded identifiers, status, nullable numeric metrics, and citation coordinates only; tests forbid raw content and payload columns.
  - Emit no optional metric for empty, missing, or all-null source values rather than writing misleading zeroes.
  - Use deterministic linear-interpolated latency percentiles for provider- and SQLite-independent p50/p95 behavior.
  - Use source retrieval/index run ID, not the newly-created eval run ID, to load pre-existing bounded observations.
  - Keep Eval tab read-only using presentation-token metric formatting rather than importing aggregation or runner modules.
patterns_established:
  - Provider-free rag_eval_observations table as the bounded optional metric source for future RAG/eval traces.
  - Canonical optional evaluation metric namespace uses `rag.*` persisted eval_metric names.
  - Dashboard evaluation history remains persisted-row presentation only, not an evaluator execution surface.
observability_surfaces:
  - Persisted eval_runs and eval_metrics include optional RAG quality and operational metric rows when bounded observations exist.
  - Sanitized eval_runs.error_reason records malformed optional observation failures without raw payload leakage.
  - Tests cover absent optional services/storage as deterministic no-op behavior.
drill_down_paths:
  - .gsd/milestones/M003/slices/S06/tasks/T01-SUMMARY.md
  - .gsd/milestones/M003/slices/S06/tasks/T02-SUMMARY.md
  - .gsd/milestones/M003/slices/S06/tasks/T03-SUMMARY.md
  - .gsd/milestones/M003/slices/S06/tasks/T04-SUMMARY.md
  - .gsd/milestones/M003/slices/S06/tasks/T05-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-05-27T20:49:23.450Z
blocker_discovered: false
---

# S06: Complete R007 metric coverage

**Completed R007 evaluation metric coverage by adding bounded RAG/eval observation storage, deterministic optional metric aggregation, retrieval-eval persistence, and read-only dashboard formatting for quality, citation, latency, token, and cost metrics.**

## What Happened

S06 closed the R007 metric coverage gap without introducing live provider, RAGAS, Langfuse, or Streamlit-side computation requirements. T01 extended the SQLite evaluation schema with a bounded rag_eval_observations table and repository helpers that persist only safe identifiers, status, nullable numeric metrics, and citation coordinates, while tests forbid raw prompts, answers, snippets, provider payloads, image blobs, Docling JSON, secrets, and full hashes. T02 added pure aggregation helpers for optional RAG/eval operational and quality metrics, including deterministic latency average/p50/p95, cost totals/averages, token sums, and faithfulness/answer-relevancy averages. T03 wired those helpers into retrieval eval runs so pre-existing bounded observations for the source retrieval/index run are persisted as global rag.* eval_metrics alongside existing recall and citation metrics; absent optional storage remains a no-op and malformed numeric data is surfaced through sanitized eval_run failure state. T04 kept the Eval tab as a credential-free, read-only surface over persisted eval_runs/eval_metrics, adding clear formatting for percentages, milliseconds, USD cost, and integer token metrics without importing runners or providers. T05 reran the integrated R007 regression suite across schema, repository, optional metrics, runner integration, extraction metrics, and dashboard rendering.

## Verification

Closeout verification was rerun through gsd_exec runtime=node spawning the Windows project virtualenv command: venv/Scripts/python.exe -m pytest -q tests/test_eval_db_schema.py tests/test_eval_repository.py tests/test_retrieval_eval_optional_metrics.py tests/test_retrieval_eval_runner.py tests/test_extraction_eval_metrics.py tests/test_dashboard_eval_tab.py. Exit code 0; pytest reported 37 passed in 10.06s. Task-level verification also passed for schema/repository storage, optional metric aggregation, retrieval runner integration, dashboard formatting/import guards, and the integrated R007 proof. Operational readiness gate Q8: health signal is persisted eval_runs/eval_metrics plus tested rag.* metrics; failure signal is sanitized eval_runs.error_reason for malformed observations; recovery procedure is to correct bounded observation numeric data or run without optional observations, which deterministically omits optional metrics; monitoring gap remains live Langfuse tracing instrumentation and recorded dashboard UAT, both intentionally deferred to S07 and S08.

## Requirements Advanced

- R007 — Advanced from extraction F1/retrieval recall/citation coverage to include repeatable bounded faithfulness/relevancy, latency, token, and cost metric persistence and dashboard rendering under tests.
- R010 — Preserved and extended redaction boundaries by forbidding raw prompts, answers, snippets, provider payloads, secrets, images, Docling JSON, raw text, and full hashes from optional evaluation observation storage.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

S06 does not perform live RAGAS judging or Langfuse trace collection; it provides bounded storage and deterministic aggregation surfaces for those future observations. Full Langfuse tracing remains S07, and recorded dashboard UAT remains S08.

## Follow-ups

S07 should write bounded Langfuse/tracing observations into the S06 storage/metric contract without leaking secrets or raw content. S08 should record runtime Eval tab UAT evidence showing populated metrics, comparison behavior, and fresh-DB messaging.

## Files Created/Modified

- `src/db/schema.py` — Added idempotent bounded rag_eval_observations schema and indexes.
- `src/eval/repository.py` — Added RAGEvalObservationRow and insert/list helpers with nullable numeric normalization and malformed numeric rejection.
- `src/eval/operational_metrics.py` — Added pure deterministic optional metric aggregation for quality, latency, cost, and tokens.
- `src/eval/retrieval_eval_runner.py` — Loaded bounded observations for source runs and persisted optional rag.* metrics alongside retrieval/citation metrics.
- `src/dashboard/eval.py` — Formatted persisted optional RAG quality, latency, cost, and token metrics while keeping dashboard read-only.
- `tests/test_eval_db_schema.py` — Covered observation schema initialization, legacy upgrade, indexes, and forbidden raw columns.
- `tests/test_eval_repository.py` — Covered observation insertion, listing/filtering, nullable values, and malformed numeric handling.
- `tests/test_retrieval_eval_optional_metrics.py` — Covered deterministic aggregation, absent optional data, no-RAGAS import behavior, and runner optional metric persistence.
- `tests/test_retrieval_eval_runner.py` — Maintained retrieval eval runner regression coverage with optional metrics integration.
- `tests/test_dashboard_eval_tab.py` — Covered display formatting, comparison deltas, null values, missing-table safety, and provider/evaluator import guards.
