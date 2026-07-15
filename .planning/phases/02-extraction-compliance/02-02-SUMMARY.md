---
phase: "02-extraction-compliance"
plan: "02"
slug: durable-extraction-run-lifecycle
status: complete
completed: 2026-07-15
requirements:
  - EXTRACT-01
---

# Phase 2 Plan 02 — Durable Extraction Run Lifecycle Summary

## Outcome

Every single-document or batch extraction now has one durable, manifest-bound
run with explicit per-document state. Completed work is skipped on resume,
failed or interrupted work is retried deterministically, incompatible run reuse
is rejected before provider construction, and terminal status comes only from
SQL-derived child truth.

## What changed

- Added additive run provenance/count columns plus
  `extraction_run_documents(run_id, doc_id)` with pending, running, completed,
  and failed states, bounded attempt counts, trace IDs, safe reason codes, and
  timestamps.
- Added idempotent guarded migrations for legacy extraction runs and usage-model
  columns. Historical field/compliance rows conservatively backfill completed
  child rows and aggregate counts without rebuilding or rewriting source data.
- Defined the deterministic content-free manifest as
  `sha256(corpus_version + "\x1f" + "\x1e".join(sorted(unique_doc_ids)))`.
  Resume validates the exact document set, provider, requested model, corpus
  version, expected count, and child set before any mutation.
- Added transactional lifecycle APIs to begin/resume, list candidates, claim an
  attempt, record completed/failed outcomes, finalize, load strict completed
  runs, and persist bounded response-resolved model provenance.
- Removed per-record managed-run finalization. Latest/history/compliance writes
  remain atomic and idempotent; legacy direct callers retain an implicit
  compatible lifecycle without gaining authority over managed child state.
- Updated both CLI commands with one generated-or-explicit run ID, a bounded
  `--corpus-version`, begin-before-provider construction, deterministic resume
  order, durable construction/runtime failures, completed-child skipping, and
  SQL-derived terminal summaries and exit codes.
- Preserved interruption truth: `KeyboardInterrupt`, `SystemExit`, and unexpected
  base exceptions leave the in-flight child and parent running for a later
  exact-identity resume.
- Sanitized CLI exception boundaries and stored failure reasons so raw provider
  messages, secrets, document text, paths, payloads, and image bytes are not
  printed or persisted.
- Preserved backward construction compatibility for the dashboard's legacy
  `ExtractionRunSummary` shape while repository-loaded summaries populate all new
  count/provenance fields.

## State transitions and terminal truth

- `pending | running | failed -> running` claims exactly one attempt.
- `running -> completed | failed` records one bounded terminal outcome.
- Completed children are immutable and excluded from resume candidates.
- All children completed -> parent `completed`.
- Completed/failed terminal mix -> parent `partial`.
- All children failed -> parent `failed`.
- Any pending/running or unaccounted child -> parent `running` with null
  `completed_at`.

## Verification evidence

- Complete lifecycle/schema/CLI plan gate:
  `venv\Scripts\python.exe -m pytest tests\test_extraction_models.py tests\test_extraction_schema.py tests\test_extraction_run_history_schema.py tests\test_extraction_persistence.py tests\test_extraction_cli.py tests\test_eval_db_schema.py -q --tb=short`
  — **72 passed** in 19.60s.
- Dashboard and persistence compatibility slice — **47 passed** in 11.43s.
- CLI/schema/eval compatibility slice — **38 passed** in 14.58s.
- Full Windows repository regression:
  `venv\Scripts\python.exe -m pytest tests -q --tb=short`
  — **479 passed, 8 skipped** in 175.99s.

The eight skips are explicit GPU/optional-integration cases. The 14 warnings are
upstream Torch JIT deprecations from real ingestion coverage.

## Deviations resolved during review

Initial CLI integration populated `resolved_model` from the provider's requested
configuration before any Gemini response existed. That fabricated provenance was
removed; the field remains null until response-backed integration records an
actual resolved identity. Review also found that making every expanded summary
field mandatory broke existing dashboard callers. New fields now have safe
defaults while SQL-returned summaries remain fully populated.

## Remaining scope

Plan 03 owns response-backed usage/run provenance, exact literal evidence
grounding, conservative visual review, deterministic risk boundaries, complete
run-only evaluation, and the full Phase 2 quality gate.
