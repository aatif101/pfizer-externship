---
id: S01
parent: M004
milestone: M004
provides:
  - Run-scoped extraction and compliance history query functions.
  - Stable extraction run summary metadata for dashboard selectors.
  - Run-specific predicted extraction rows for eval comparison without latest-write ambiguity.
  - Latest-write repository compatibility preserved for existing dashboard and extraction code.
requires:
  []
affects:
  - S02
  - S03
  - S04
  - S05
key_files:
  - src/db/schema.py
  - src/extraction/repository.py
  - src/extraction/cli.py
  - src/eval/repository.py
  - tests/test_extraction_run_history_schema.py
  - tests/test_extraction_persistence.py
  - tests/test_extraction_cli.py
  - tests/test_eval_repository.py
key_decisions:
  - Preserved existing latest-write extraction and compliance tables unchanged, adding run-scoped history as additive tables only.
  - Kept run-history writes repository-owned and transactional with latest-write persistence when `record.run_id` is present.
  - Made eval selected-run predictions read strictly from `extraction_history` for an explicit run id with no latest-write fallback.
patterns_established:
  - Run identity is an explicit repository/eval/CLI contract, not inferred from latest-write state.
  - Compatibility APIs remain latest-write surfaces; run-scoped APIs are separate history surfaces.
  - History metadata is bounded and excludes raw prompts, page text, provider payloads, image bytes, secrets, PDFs, and confidential local artifact paths.
observability_surfaces:
  - Run summaries expose bounded status/count/timestamp/trace metadata for downstream selectors and diagnostics.
  - Sanitized repository exceptions and review/risk state are available without exposing confidential document content.
drill_down_paths:
  - .gsd/milestones/M004/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S01/tasks/T02-SUMMARY.md
  - .gsd/milestones/M004/slices/S01/tasks/T03-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-06-03T22:21:09.159Z
blocker_discovered: false
---

# S01: Run scoped extraction history

**Added run-scoped extraction and compliance history so baseline and candidate runs can coexist while latest-write repository behavior remains compatible.**

## What Happened

S01 introduced additive SQLite history for extraction runs, field-level extraction rows, and compliance rows without changing the existing latest-write `extractions` and `compliance_records` compatibility tables. Repository persistence now writes run history in the same transaction when `SDFExtractionRecord.run_id` is present, supports idempotent same-run/doc upserts, and exposes run-scoped reconstruction APIs for extraction records, compliance rows, and stable run summaries. CLI extraction commands can pass a shared explicit `--run-id` through single and batch execution, and eval repository reads can list predicted extraction rows for a selected run strictly from history, with no fallback to latest-write tables. The result gives downstream slices a reliable run selector/comparison substrate while keeping provider payloads, raw prompts, page text, images, PDFs, secrets, and confidential local artifacts out of schema outputs and diagnostics.

## Verification

Fresh closeout verification ran through `gsd_exec` runtime=node spawning Windows-native `venv\\Scripts\\python.exe` commands. All planned slice checks passed: `pytest -q tests/test_extraction_run_history_schema.py tests/test_db.py` passed 8 tests; `pytest -q tests/test_extraction_persistence.py tests/test_extraction_pipeline.py` passed 31 tests; `pytest -q tests/test_extraction_cli.py tests/test_eval_repository.py tests/test_extraction_persistence.py` passed 29 tests. These suites verify additive schema creation and idempotency, foreign-key enforcement, forbidden confidential columns absent from history tables, independent reconstruction of two run IDs for the same document, latest-write compatibility for existing repository reads, run-filtered compliance rows matching dashboard shape, stable run summaries, CLI run-id propagation, and eval selected-run prediction reads without latest fallback. Evidence: `.gsd/exec/0712d0ec-1619-4cbd-9db7-f155b778e736.stdout`.

## Requirements Advanced

- R012 — Provides stable run summary and run-scoped compliance repository surfaces required for the Compliance dashboard run selector.
- R015 — Provides run-specific predicted extraction rows so future real candidate comparisons can select baseline/candidate runs without latest-write ambiguity.
- R016 — Keeps run-history schema, diagnostics, and tests bounded to metadata and avoids storing raw prompts, page text, provider payloads, images, PDFs, secrets, or local confidential artifact paths.
- R017 — Closeout verification used only Windows-native `gsd_exec` runtime=node spawning `venv\\Scripts\\python.exe`; no `/bin/bash` or bash runtime was invoked.

## Requirements Validated

- R011 — Closeout tests prove two extraction runs for the same document can be persisted and queried independently while `get_extraction_record()` and `list_compliance_records()` latest-write compatibility remains intact.

## New Requirements Surfaced

- None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

This slice creates the run-history substrate only. It does not add the Streamlit run selector, usage/cost observations, visual fallback, or final real five-document comparison; those remain planned for S02-S05.

## Follow-ups

Proceed to S02 using `list_extraction_run_summaries()` and `list_compliance_records_for_run()` as the dashboard selector substrate. Proceed to S03 using explicit run identity as the reference key for bounded usage observations.

## Files Created/Modified

- `src/db/schema.py` — Added additive extraction run, extraction history, and compliance history schema while preserving latest-write tables.
- `src/extraction/repository.py` — Added transactional run-history persistence plus run-scoped extraction, compliance, and run-summary query APIs.
- `src/extraction/cli.py` — Wired explicit shared run identity through extraction CLI commands.
- `src/eval/repository.py` — Added selected-run prediction reads from extraction history without latest-write fallback.
- `tests/test_extraction_run_history_schema.py` — Added schema tests for run-history creation, idempotency, compatibility, bounded columns, and foreign-key enforcement.
- `tests/test_extraction_persistence.py` — Added repository tests for independent run reconstruction, latest compatibility, history idempotency, compliance rows, and run summaries.
- `tests/test_extraction_cli.py` — Added fake-provider CLI tests for explicit run-id propagation in single and batch commands.
- `tests/test_eval_repository.py` — Added eval repository tests for selected-run prediction reads.
