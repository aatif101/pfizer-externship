# S01: Run scoped extraction history — UAT

**Milestone:** M004
**Written:** 2026-06-03T22:21:09.160Z

# S01: Run scoped extraction history — UAT

**Milestone:** M004
**Written:** 2026-06-03

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: This slice changes repository, schema, CLI, and eval read contracts; deterministic SQLite fixtures and fake-provider CLI tests prove the user-visible prerequisite without requiring live providers, confidential PDFs, or a running dashboard.

## Preconditions

- Work from the repository root on Windows.
- The project virtual environment exists at `venv\\Scripts\\python.exe`.
- No live Gemini, Claude, Qdrant, Streamlit, or confidential SDF artifacts are required.

## Smoke Test

Run `venv\\Scripts\\python.exe -m pytest -q tests/test_extraction_persistence.py` and confirm the suite passes. This confirms run history can coexist with latest-write extraction persistence.

## Test Cases

### 1. Two extraction runs for the same document remain independently queryable

1. Use the repository fixture tests to persist two `SDFExtractionRecord` instances for one `doc_id` with distinct `run_id` values.
2. Query each run with `get_extraction_record_for_run()`.
3. **Expected:** Each query reconstructs the fields and compliance state for only the selected run; rows from the other run do not leak into the result.

### 2. Latest-write compatibility still works

1. Persist multiple records for the same document through `upsert_extraction_record()`.
2. Query the existing compatibility APIs `get_extraction_record()` and `list_compliance_records()`.
3. **Expected:** Existing APIs return the newest compatibility rows in the same shape expected by prior extraction and dashboard code.

### 3. CLI can persist a shared explicit run identity

1. Run CLI tests that invoke single-document and batch extraction commands with an explicit `--run-id` using fake providers.
2. Inspect repository assertions made by the tests.
3. **Expected:** All generated extraction records share the requested run id and are persisted into run history without requiring live provider calls.

### 4. Eval reads selected-run predictions only

1. Persist extraction history rows for a selected run and separate latest-write rows.
2. Call the eval repository selected-run prediction read.
3. **Expected:** Predictions are read from `extraction_history` for the explicit run id and do not fall back to latest-write rows.

## Edge Cases

### Same run and document is upserted again

1. Persist the same `run_id` and `doc_id` combination more than once.
2. Query run history and row counts.
3. **Expected:** The upsert is idempotent for that run/document pair rather than creating duplicate semantic results.

### Missing or orphaned history parent rows

1. Exercise schema tests that attempt invalid history relationships.
2. **Expected:** SQLite foreign-key constraints reject orphaned history rows.

### Confidential data remains outside run metadata

1. Inspect schema/test assertions for history metadata columns.
2. **Expected:** Run/history tables expose bounded metadata only: run id, document counts, field counts, timestamps, status, trace id, review state, risk fields, and sanitized repository exceptions; they do not contain raw prompts, page text, provider payloads, image bytes, secrets, PDFs, or local confidential artifact paths.

## Failure Signals

- `get_extraction_record_for_run()` returns fields from the wrong run or falls back to latest-write rows.
- `get_extraction_record()` or `list_compliance_records()` changes shape or stops returning latest compatibility data.
- CLI tests show generated records missing the explicit shared run id.
- Eval selected-run reads return predictions when only latest-write rows exist.
- History schema adds columns that could store raw prompts, page text, provider payloads, image bytes, secrets, PDFs, or confidential local paths.

## Not Proven By This UAT

- Dashboard run selector UI behavior; that is deferred to S02.
- Gemini token/cost usage observations; that is deferred to S03.
- Targeted visual fallback behavior; that is deferred to S04.
- Final real five-document comparison against local confidential artifacts; that is deferred to S05.

## Notes for Tester

Use Windows-native commands only. The authoritative closeout evidence for this slice is `.gsd/exec/0712d0ec-1619-4cbd-9db7-f155b778e736.stdout`, which records all planned pytest suites passing without `/bin/bash` or `gsd_exec` bash runtime.
