---
estimated_steps: 7
estimated_files: 5
skills_used: []
---

# T02: Persist mocked Gemini text extraction usage

Expected executor skills: tdd, verify-before-complete.

Why: The observation table is useful only if the live provider boundary and pipeline persist SDK usage metadata during real extraction calls. This task wires mocked Gemini usage metadata through the existing provider DTOs into the repository while preserving the no-raw-payload diagnostic boundary.

Do: Extend the provider DTO contract in `src/extraction/providers.py` with a small bounded usage metadata DTO, keeping `ProviderExtractionResult` backward compatible for existing fake providers. In `src/extraction/gemini.py`, extract SDK-like usage metadata from mocked responses using common Gemini fields such as `usage_metadata.prompt_token_count`, `candidates_token_count`, and `total_token_count`; do not store response text, request contents, page text, or JSON payload. Add deterministic estimated-cost calculation for Gemini 2.5 Flash using model/rate constants in code, returning NULL cost when token metadata is absent or model pricing is unknown. In `src/extraction/pipeline.py`, after provider output is normalized and the extraction record is persisted, insert one text-stage usage observation keyed by the effective run_id and doc_id with provider name/model/status/trace_id, latency if measured, token counts, and estimated cost. If provider output is malformed but converted into abstained fields, still persist a status that reflects the bounded outcome. Keep provider exceptions sanitized and do not introduce secrets or raw content into trace metadata.

Failure Modes (Q5): Missing usage metadata should not fail extraction and should persist either no observation or an observation with nullable token/cost fields, as defined by tests. Provider retry/exceptions remain governed by existing `ExtractionProviderError`; if an observation insert fails after successful extraction, the executor should decide whether to fail visibly or document a conservative rollback behavior in tests. Malformed Gemini JSON still follows the existing abstention path and may record usage from the response metadata.

Load Profile (Q6): Per extraction call adds one SQLite insert and constant-time metadata extraction. At 10x documents, SQLite write throughput is the first shared-resource concern; avoid per-field usage rows for the text stage.

Negative Tests (Q7): mocked response with complete usage metadata, mocked response without usage metadata, malformed JSON response with usage metadata, and assertions that observation rows do not contain prompt/page text/provider payload values.

Done when: mocked Gemini extraction/pipeline tests prove one bounded text usage observation is persisted for a run-specific document and existing extraction pipeline tests still pass.

## Inputs

- `src/extraction/providers.py`
- `src/extraction/gemini.py`
- `src/extraction/pipeline.py`
- `src/eval/repository.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_extraction_persistence.py`

## Expected Output

- `src/extraction/providers.py`
- `src/extraction/gemini.py`
- `src/extraction/pipeline.py`
- `tests/test_extraction_gemini_usage.py`
- `tests/test_extraction_pipeline.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_usage.py tests/test_extraction_pipeline.py tests/test_extraction_persistence.py

## Observability Impact

Connects provider-call telemetry to the new observation table while keeping trace metadata and exceptions bounded to run/doc/provider/status/error-class identifiers.
