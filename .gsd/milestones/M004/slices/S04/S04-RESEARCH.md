# S04 Research: Targeted visual fallback extraction

## Summary

S04 owns active requirement R014 and supports R013/R015/R016/R017. The slice should add a targeted, provider-seamed visual fallback after the existing text extraction normalization path, using stored `pages.image_blob` data only for fields that are missing/suspicious, then re-run normal validation/risk/persistence so latest-write compatibility and run history remain intact.

The highest-risk seam is arbitration: visual fallback must improve only eligible fields and must not replace good grounded text values. The safest approach is to keep the existing text provider call and `_normalize_fields()` logic authoritative for initial results, then call a separate visual provider only with an allowlist of eligible fields/pages, normalize those candidate payloads through the same `_normalize_field()` guard path, and merge replacements only when the current field is `ABSTAINED` or `NEEDS_REVIEW` and the visual candidate is non-abstained.

## Active Requirements and Constraints

- **R014 (owned by S04):** targeted visual fallback for abstained, suspicious, ungrounded, low-confidence, or missing fields using stored page images from local `compliance.db`.
- **R013 (validated, supports S04):** visual calls must reuse bounded extraction usage observations. Use a distinct stage such as `visual_fallback`; rows may contain run/doc/stage/provider/model/status/tokens/cost/latency/trace/error_reason only.
- **R016 (supports future S05 but constrains S04):** do not persist or log raw prompts, page text, provider payloads, images/PDFs, secrets, or confidential local paths. Visual prompt/image bytes must remain in-memory only.
- **R017 (constraint):** verification must be Windows-native. Use `gsd_exec runtime=node` spawning `venv/Scripts/python.exe -m pytest ...`; do not use `/bin/bash` or `runtime=bash`.

Prior memory findings reinforce this: live providers stay lazy/offline-safe; extraction provider DTOs are untrusted and normalized by the pipeline; S03 usage observations are bounded and nullable; S01 run history is additive and repository-owned.

## Existing Implementation Landscape

### Core extraction pipeline

- `src/extraction/pipeline.py:106` `extract_document()` loads text pages with `include_image_bytes=False`, calls a `SDFExtractionProvider`, normalizes exactly six fields, computes risk, persists through `upsert_extraction_record()`, and records one text usage observation.
- `src/extraction/pipeline.py:221` `_insert_text_usage_observation()` inserts S03 telemetry with stage `text_extraction`.
- `src/extraction/pipeline.py:275` `_normalize_fields()` / `_normalize_field()` convert provider DTOs into validated `ExtractedField`s. This is the key reusable validation seam: it already handles missing fields, no value, missing evidence, invalid page, invalid bbox, missing span, span mismatch, placeholder values, Delivery Date/Eff Date guard, Retest Date/Expiry guard, and low-confidence `NEEDS_REVIEW`.
- `src/extraction/pipeline.py:381` `_field_value_guard_reason()` contains suspicious-value guards that S04 should preserve for visual candidates.

### Provider protocol and Gemini adapter

- `src/extraction/providers.py` defines `ProviderFieldPayload`, `ProviderSourceEvidence`, `ProviderUsageMetadata`, and `ProviderExtractionResult`. The current `SDFExtractionProvider.extract_fields(document, pages, run_id)` protocol is text-page oriented, but `DocumentPage` already has optional `image_blob`.
- `src/extraction/gemini.py:47` `GeminiSDFExtractionProvider` is lazy/offline-safe and uses injected `client`/`client_factory` in tests.
- `src/extraction/gemini.py:74` `extract_fields()` calls `_build_contents()`, `_generate_content()`, `_extract_usage_metadata()`, `_parse_fields()` and returns existing DTOs.
- `src/extraction/gemini.py:117` `_generate_content()` currently sends `contents` as a text string and JSON response config.
- `src/extraction/gemini.py:151` `_build_contents()` includes all page text plus packet-labeling policy. S04 should avoid sending all image blobs; build a smaller visual prompt with only eligible fields and selected page images.
- Local installed `google-genai` supports image parts: `google.genai.types.Part.from_bytes(data=bytes, mime_type='image/png')`, `Part.from_text(text=...)`, and `Content(parts=[...], role=...)`. This was confirmed with `venv/Scripts/python.exe` via `gsd_exec`.

### Page images and DB access

- `src/db/schema.py` stores `pages.image_blob BLOB` and states it is 150 DPI PNG.
- `src/db/queries.py:30` `DocumentPage` already includes `image_blob: bytes | None`.
- `src/db/queries.py:107` `get_page_image()` returns a PIL image for dashboard detail only; avoid using PIL for provider calls unless needed.
- `src/db/queries.py:120` `load_document_pages(..., include_image_bytes=True)` can load ordered page rows with image bytes. The text extraction path currently passes `False`; S04 can load images only after eligibility is known.

### Persistence/run history/eval surfaces

- `src/extraction/repository.py:77` `upsert_extraction_record()` writes latest rows plus run history when `record.run_id` is present.
- `src/extraction/repository.py:132` `get_extraction_record_for_run()` reconstructs run-specific records.
- `src/extraction/repository.py:166` `list_compliance_records_for_run()` and `:172` `list_extraction_run_summaries()` power the S02 dashboard run selector.
- `src/eval/repository.py:72` `ExtractionUsageObservationRow` is the bounded S03 DTO.
- `src/eval/repository.py:400` `insert_extraction_usage_observation()` and `:450` `list_extraction_usage_observations()` support multiple rows per run/doc/stage.

### Tests/patterns to extend

- `tests/test_extraction_pipeline.py` has comprehensive fake-provider tests for normalization, trace safety, placeholder guards, span mismatch, low confidence, invalid page/bbox, and usage persistence. This is the best place for visual fallback orchestration tests.
- `tests/test_extraction_gemini_usage.py` has fake Gemini client/response helpers and bounded usage assertions. Extend or add a sibling file for visual Gemini behavior.
- `tests/test_extraction_usage_observations.py` validates the usage repository; likely no schema changes are needed.
- `tests/test_rasterizer.py` proves image blobs are PNGs and ingestion stores them.

## Recommended Architecture

### 1. Add a dedicated visual provider protocol, not a risky rewrite of text provider

Create a small protocol/DTO in `src/extraction/providers.py`, e.g.:

```python
@dataclass(frozen=True)
class VisualFallbackRequest:
    fields: tuple[SDFFieldName, ...]
    pages: tuple[DocumentPage, ...]  # image_blob populated for selected pages only
    reason_codes: dict[SDFFieldName, str]  # bounded strings, no raw values needed

class SDFVisualFallbackProvider(Protocol):
    def extract_visual_fields(
        self, *, document: DocumentMetadata, request: VisualFallbackRequest, run_id: str
    ) -> ProviderExtractionResult: ...
```

Reason: avoids changing every existing fake `SDFExtractionProvider`, keeps visual fallback optional, and gives planners/executors a clean mockable seam.

### 2. Pipeline flow

Suggested `extract_document()` additions:

1. Load text pages and run existing text extraction unchanged.
2. Normalize text fields via existing `_normalize_fields()`.
3. Determine eligible fields with a helper such as `_visual_fallback_eligible_fields(fields, low_confidence_threshold)`.
   - Eligible if `review_state == ABSTAINED`.
   - Eligible if `review_state == NEEDS_REVIEW` (low confidence).
   - This already covers missing provider fields, missing/ungrounded evidence, placeholder-blocked values, Delivery/Retest guard failures, and low confidence because all become `ABSTAINED` or `NEEDS_REVIEW`.
   - Do **not** include `PENDING` fields; this proves good grounded text values are preserved.
4. If no eligible fields or no visual provider configured: skip visual fallback and persist text result as today.
5. Load image bytes only then via `load_document_pages(db_path, doc_id, include_image_bytes=True)`.
6. Choose pages for fallback. Minimal safest option: pages referenced by eligible field evidence page numbers plus all pages for missing fields only if page count is small; for tests, selected pages can be deterministic. If all selected images missing, record a `visual_fallback` usage observation with `status='skipped'` and `error_reason='missing_page_images'`.
7. Call visual provider with bounded request. Measure latency.
8. Normalize visual payloads through `_normalize_fields()` or field-by-field `_normalize_field()` using pages with text + image bytes.
9. Merge visual replacements only for eligible current fields and only when candidate is better:
   - Replace `ABSTAINED` with any non-abstained valid visual field.
   - Replace `NEEDS_REVIEW` only with `PENDING` visual field, or with confidence >= threshold.
   - Never replace a `PENDING` current field.
10. Compute risk on merged record, persist once through existing repository, then insert visual usage observation after run exists.

### 3. Gemini visual implementation

Add a separate class such as `GeminiSDFVisualFallbackProvider` in `src/extraction/gemini.py`, or add an `extract_visual_fields()` method to `GeminiSDFExtractionProvider` while keeping text imports and credentials lazy.

Implementation notes:

- Build `contents` using `google.genai.types.Content/Part` when available:
  - `types.Part.from_text(text=prompt)`
  - `types.Part.from_bytes(data=page.image_blob, mime_type='image/png')`
- Use the same `response_mime_type='application/json'` and `temperature=0` config.
- Reuse `_extract_usage_metadata()`, `_response_text()`, `_parse_json_object()`, `_parse_fields()`, `_malformed_result()` where possible.
- Prompt should include only bounded field names, page numbers, document id/filename/run id, and instructions. Do not include full page text if the visual call is intended to be visual; optionally include tiny allowed context labels only if needed.
- The output JSON schema can match existing field payloads, so existing normalization/DTOs continue to work.

## Natural Seams / Suggested Task Breakdown

1. **Visual provider contract and eligibility helpers**
   - Files: `src/extraction/providers.py`, `src/extraction/pipeline.py`, tests in `tests/test_extraction_pipeline.py` or new `tests/test_visual_fallback_pipeline.py`.
   - Prove eligible set includes abstained/low-confidence fields and excludes `PENDING` fields.

2. **Pipeline orchestration and arbitration**
   - Files: `src/extraction/pipeline.py`.
   - Add optional `visual_provider` parameter to `extract_document()` and maybe CLI later if needed.
   - Prove fallback fills missing/abstained field, preserves good grounded field, skips when no images, and records no confidential values in diagnostics.

3. **Visual usage observations**
   - Files: `src/extraction/pipeline.py`, tests with `list_extraction_usage_observations()`.
   - Insert `stage='visual_fallback'` rows for complete/skipped/error/abstained outcomes after extraction run persistence exists. Ensure nullable tokens/cost and sanitized `error_reason`.

4. **Gemini visual provider**
   - Files: `src/extraction/gemini.py`, tests in `tests/test_extraction_gemini_visual.py`.
   - Use fake Gemini client to assert `generate_content()` receives image parts and never raw local paths. Validate usage metadata parsing and malformed output behavior.

5. **CLI wiring if required for S05 real run**
   - Files: `src/extraction/cli.py`, `tests/test_extraction_cli.py`.
   - Add opt-in flag such as `--visual-fallback/--no-visual-fallback` or provider option. Keep default behavior unchanged for existing tests.

## First Proof / Highest-Risk Test

The first proof should be provider-free and deterministic:

- Prepare a one-page doc with PNG `image_blob` and page text containing all normal values except make text provider omit or abstain `vendor_name`.
- Text fake provider returns good `doc_type`, dates, etc., but `vendor_name` missing/abstained or low-confidence.
- Visual fake provider receives only eligible `vendor_name` request and image bytes, returns valid `vendor_name` evidence.
- Assert stored record has visual-filled `vendor_name`, good text `expiry_date`/other fields preserved unchanged, run history row exists for the merged result, and usage observations include `text_extraction` plus `visual_fallback` rows.

This proves the core R014 contract without live Gemini.

## Verification Commands

Use Windows-native verification only through `gsd_exec runtime=node` or direct Windows venv path. Suggested gates:

```text
venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py tests/test_extraction_pipeline.py
venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_visual.py tests/test_extraction_gemini_usage.py
venv/Scripts/python.exe -m pytest -q tests/test_extraction_persistence.py tests/test_extraction_usage_observations.py tests/test_eval_repository.py
```

If CLI is touched, add:

```text
venv/Scripts/python.exe -m pytest -q tests/test_extraction_cli.py
```

## Skill Discovery

Installed relevant skills from the prompt:

- `observability` is relevant because S04 adds unattended provider-stage telemetry and must preserve bounded diagnostics. Apply its rule: make failure modes explicit and agent-diagnosable without leaking payloads.
- `api-design`/`design-an-interface` are relevant if choosing between extending the text provider protocol vs adding a new visual provider protocol; recommendation above favors a separate visual protocol.
- `security-review` is relevant before completion because this touches image bytes, provider prompts, external API calls, SQLite, and confidentiality constraints.

External skill search (`npx skills find`) for `google-genai`, `Pydantic`, and `SQLite` did not return usable results in this environment (process exited without output before timeout). No install recommendation.

## Open Design Question / Watch-out

Current `ExtractedField` requires non-abstained fields to have `evidence.verbatim_span`, and `_normalize_field()` requires that span to match stored `page_text`. This is good for no-hallucination, but it may prevent S04 from fixing true OCR/text-layer gaps where the value exists visually but not in text. The planner should decide whether S04 remains conservative (visual only accepts values with text-matching span) or introduces an explicit image-grounded evidence mode. The conservative path is lower-risk and testable now; image-only evidence is a larger schema/model/dashboard/eval decision.

## Sources / Evidence

- `memory_query`: MEM016, MEM085, MEM017, MEM083, MEM073, MEM079.
- `gsd_exec 9b107803-d9d4-4313-ba96-4db64f061123`: scanned image/page symbols and confirmed `load_document_pages`/dashboard image surfaces.
- `gsd_exec e34611d2-babb-4e70-8dbf-c0eff7904615` and `1690b8aa-94de-4635-b176-37532ea6c901`: confirmed installed `google-genai` image part APIs.
- `gsd_exec 94940d90-cb86-48e7-b312-90216a397c13`: collected key line numbers for planner targeting.
