# S03: Gemini extraction usage observations — UAT

**Milestone:** M004
**Written:** 2026-06-04T23:29:20.724Z

# S03: Gemini extraction usage observations — UAT

**Milestone:** M004
**Written:** 2026-06-04

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: The slice is a repository/provider/eval contract with no live UI or live Gemini dependency; mocked SDK-like Gemini responses and SQLite fixtures prove the observable behavior without exposing prompts, PDFs, images, page text, provider payloads, secrets, or local confidential paths.

## Preconditions

- The project virtual environment exists at `venv/Scripts/python.exe`.
- The S03 source and test files are present in the working tree.
- No live Gemini credentials or confidential SDF artifacts are required.

## Smoke Test

Run the S03 closeout pytest gates through a Windows-native Python interpreter. Expected result: all three targeted pytest commands pass and the usage observation/eval metric tests report no failures.

## Test Cases

### 1. Bounded observation persistence

1. Initialize a SQLite test database with `init_db()`.
2. Insert multiple extraction usage observations for the same `run_id` and `doc_id` with valid numeric telemetry.
3. List observations filtered by run, document, stage, and status.
4. **Expected:** The rows are returned with bounded metadata only, malformed numeric inputs are rejected, and the schema contains no raw prompt, page text, provider payload, image/PDF byte, secret, or local path columns.

### 2. Mocked Gemini text extraction usage

1. Run a mocked Gemini text extraction response containing SDK-like token usage metadata.
2. Persist the extraction record through the pipeline for a concrete extraction run and document.
3. Inspect usage observations for the run/document/stage/model.
4. **Expected:** Exactly one text-stage observation is persisted after the extraction run parent exists, token counts and known-model estimated cost are bounded numeric values, and absent or unknown model metadata leaves optional cost values null rather than zero-filled.

### 3. Extraction usage eval metrics

1. Seed bounded usage observations for a selected extraction run.
2. Run the provider-free extraction usage eval aggregation.
3. Query `eval_metrics` for the resulting eval run.
4. **Expected:** Deterministic extraction-prefixed cost, token, and latency metrics are written for present values only; missing optional values do not create misleading zero metrics.

## Edge Cases

### Absent optional usage values

1. Seed an observation with no cost or no token data.
2. Run aggregation.
3. **Expected:** The aggregation succeeds and omits that absent metric family instead of writing a zero that could be mistaken for real free usage.

### Malformed persisted numerics

1. Attempt to insert malformed numeric telemetry through the repository.
2. **Expected:** The repository rejects malformed values before DB persistence, preserving metric integrity.

## Failure Signals

- `tests/test_extraction_usage_observations.py` fails, indicating the observation schema or repository contract regressed.
- `tests/test_extraction_gemini_usage.py` fails, indicating Gemini usage metadata parsing or cost estimation regressed.
- `tests/test_extraction_pipeline.py` or `tests/test_extraction_persistence.py` fails, indicating pipeline usage persistence broke existing extraction behavior.
- `tests/test_extraction_usage_eval_metrics.py` fails, indicating aggregate metric naming, optional-value handling, or eval repository writes regressed.
- New columns or artifacts appear that contain raw prompts, page text, provider payloads, image/PDF bytes, secrets, or local confidential paths.

## Not Proven By This UAT

- Live Gemini API usage accounting or billing accuracy; this slice uses mocked SDK-like metadata only.
- Visual fallback usage accounting; S04 must reuse the observation contract for visual-stage calls.
- Real five-document cost comparison; S05 owns final real evaluation.

## Notes for Tester

Treat null optional metrics as intentional absence, not a failed zero. The authoritative proof is the targeted pytest suite plus schema inspection in the repository tests, not a dashboard workflow.
