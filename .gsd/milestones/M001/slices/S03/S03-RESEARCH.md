# S03 Research: Baseline extraction pipeline

## Summary

S03 is a targeted/deep integration slice: the typed extraction contract and SQLite persistence are already in place from S02, but there is no runtime extraction path, no Gemini dependency/configuration, and no compliance risk computation yet. The highest-leverage path is to add a small extraction pipeline under `src/extraction/` that reads existing ingested document pages from SQLite, calls a Gemini-primary provider behind a testable interface, normalizes/validates source-backed fields into `SDFExtractionRecord`, computes conservative risk, and persists through `src.extraction.repository.upsert_extraction_record`.

Active requirements owned/supported by this slice:

- **R002**: owns production of the six required SDF fields with source evidence or abstentions.
- **R003**: owns first real risk/review computation and persistence into existing nullable compliance columns.
- **R008**: owns non-fatal trace/run metadata around extraction; missing Langfuse credentials must not block extraction.
- **R004**: supports S04 by populating dashboard-ready compliance rows, but S04 owns Streamlit rendering.

Prior memory confirms the main constraints: `src.extraction.repository` is the persistence boundary; the model requires exactly six enum fields; non-abstained fields require page+verbatim span; abstained fields require an explicit reason; compliance rows are deterministically listed from `compliance_records`; and risk policy is conservative oldest lifecycle date with expired documents red.

## Recommendation

Implement S03 in four seams:

1. **Document/page read seam**: add repository/query helper(s) to fetch an ingested document and its pages (`page_num`, `page_text`, optionally `image_blob`) by `doc_id`. Keep SQL parameterized and avoid logging page text.
2. **Risk seam**: add `src/extraction/risk.py` with pure functions and tests for green/amber/red/needs-review. Extend `SDFExtractionRecord` and repository persistence to carry `risk_reason` and `age_days`, because the table already has columns but `_upsert_compliance_record()` currently writes `None` for both.
3. **Provider seam**: add a Gemini adapter (`src/extraction/gemini.py` or `providers.py`) that returns a provider-neutral raw payload. Tests should use a fake provider; routine tests must not require live credentials.
4. **Pipeline/CLI seam**: add `src/extraction/pipeline.py` to orchestrate page loading -> provider call -> validation/source-span grounding -> risk -> upsert. Expose a Typer command for extracting one doc or all ingested docs, likely in a new `src/extraction/cli.py` or by expanding `src/pipeline/__main__.py` carefully.

First proof should be the mocked provider path: seed a temp SQLite DB with one document and page text, return six valid fields from a fake provider, assert the pipeline persists six extraction rows plus one compliance record with computed risk. This proves model/repository/risk integration before spending effort on live Gemini.

## Implementation Landscape

### Existing files and purpose

- `src/extraction/models.py` — strict Pydantic v2 contract. `SDFExtractionRecord` currently has `risk_level` and `compliance_status`, but not `risk_reason` or `age_days`. `ExtractedField` requires source evidence for non-abstained fields and permits abstained fields with `abstention_reason`.
- `src/extraction/repository.py` — current persistence boundary. `upsert_extraction_record()` writes exactly six field rows and one compliance row. It already includes `risk_reason` and `age_days` in the SQL, but hardcodes both to `None`; this must change for S03.
- `src/db/schema.py` — already has nullable `compliance_records.risk_level`, `risk_reason`, `compliance_status`, and `age_days`, plus field-level review/abstention columns. Existing migration only covers extractions-table columns; compliance table is new from S02.
- `src/db/queries.py` — existing document/page CRUD for ingestion/dashboard. It lacks page-text listing helpers needed by extraction.
- `src/pipeline/ingest.py` — Typer ingestion flow. It stores Docling page text and page PNG blobs in SQLite using 0-indexed `pages.page_num`. It uses `@observe` opportunistically and never logs full page text.
- `src/pipeline/db_writer.py` — ingestion DB write orchestration with Langfuse fallback imports. Provides the pattern for non-fatal tracing wrappers.
- `src/config.py` — no Gemini settings yet. Add `gemini_api_key`, `gemini_model` (default from project context: `gemini-2.5-flash`), and probably extraction confidence threshold(s). Do not require keys at settings-import time.
- `src/tracing.py` — Langfuse v3 helper. It is non-fatal by intent, but imports `from langfuse import observe, get_client` after a failed import attempt; tests currently pass in the venv. New extraction code should follow ingestion’s local try/import no-op pattern or import from `src.tracing` only if verified safe.
- `src/app.py` — Compliance tab is still placeholder. S03 should not render UI, but it should populate rows S04 can consume via `list_compliance_records()`.
- `pyproject.toml` — missing `google-genai`. S03 needs to add it. Existing runtime deps include `tenacity` and `python-dateutil`, both useful here.
- `tests/fixtures/sample.pdf` — only PDF fixture found; size is 535 bytes and not a realistic SDF-style document. The milestone’s integrated proof will need a more realistic SDF-like PDF or a clearly documented demo asset.

### Current test coverage

Existing tests cover S02 model/schema/persistence well:

- `tests/test_extraction_models.py` — 9 validation tests for exact fields, confidence, evidence, abstention.
- `tests/test_extraction_schema.py` — 5 DB/migration/FK tests.
- `tests/test_extraction_persistence.py` — 7 upsert/listing/FK/metacharacter/abstention tests.
- `tests/test_ingest.py` — ingestion integration and safety tests.
- `tests/test_app.py` — Streamlit startup smoke.

New S03 tests should be additive: `tests/test_extraction_risk.py`, `tests/test_extraction_pipeline.py`, and probably `tests/test_extraction_provider_gemini.py` with provider calls mocked.

## Natural Seams / Work Units

### Work unit A: Risk model and repository persistence

Files: `src/extraction/models.py`, `src/extraction/repository.py`, `tests/test_extraction_risk.py`, update `tests/test_extraction_persistence.py`.

Tasks:

- Add document-level `risk_reason: str | None` and `age_days: int | None` to `SDFExtractionRecord`.
- Update `_upsert_compliance_record()` to persist `record.risk_reason` and `record.age_days` instead of `None`.
- Update `get_extraction_record()` to read/reconstruct those fields if the model carries them.
- Add `src/extraction/risk.py` pure functions:
  - expired expiry date -> red.
  - missing/ambiguous all relevant dates -> needs_review / unknown risk.
  - otherwise use oldest of manufacturing/effective/revision dates for age.
  - green under 2 years, amber at 2-3 years, red over 3 years.
- Keep `today` injectable for deterministic tests.

This is independent of Gemini and should be built first.

### Work unit B: Page/document read helpers

Files: `src/db/queries.py` or `src/extraction/repository.py`, `tests/test_extraction_pipeline.py`.

Tasks:

- Add a helper to fetch document metadata and ordered pages by `doc_id`.
- Return page text and optionally image bytes; page numbers must remain 0-indexed.
- Decide behavior when no pages/page text exist: pipeline should return a clear extraction failure or all-field abstention record, not crash.
- Do not log page text or image bytes.

### Work unit C: Provider contract and Gemini adapter

Files: `src/extraction/providers.py` or `src/extraction/gemini.py`, `src/config.py`, `pyproject.toml`, tests with mocks.

Tasks:

- Add `google-genai` dependency.
- Add settings: `gemini_api_key`, `gemini_model`, maybe `extraction_low_confidence_threshold`.
- Define a small provider protocol such as `extract_fields(document, pages) -> dict/list` so tests can inject a fake provider.
- Gemini adapter should use structured-output prompting/schema where possible, but pipeline must still validate with Pydantic. Do not trust provider JSON directly.
- Missing `GEMINI_API_KEY` should raise/return a typed, user-facing `ExtractionConfigurationError` caught by the pipeline/CLI. Routine tests should assert this path without requiring credentials.
- Use `tenacity` for transient 429/503 retries, but keep retry count low in CLI/tests.

### Work unit D: Pipeline orchestration and CLI

Files: `src/extraction/pipeline.py`, maybe `src/extraction/cli.py` or `src/pipeline/__main__.py`, tests.

Tasks:

- Orchestrate: load document/pages -> call provider -> normalize field payloads -> validate source spans against page text -> build `SDFExtractionRecord` -> compute risk -> upsert.
- Enforce source grounding: if a non-abstained field’s `verbatim_span` is absent from the cited page text after whitespace/case normalization, downgrade to `needs_review` or abstain with a reason. The roadmap says source-backed fields or explicit abstentions; do not persist invented values as valid facts.
- Low-confidence policy: set `ReviewState.NEEDS_REVIEW` for fields below threshold instead of hiding them. Recommend threshold as a named config default (e.g. `0.75`) rather than magic number.
- Malformed provider output: return/persist an explicit review/abstention state. A practical model-compatible fallback is six `ABSTAINED` fields with `confidence=0.0`, `page_num=0` if the document has pages, and abstention reason including non-secret error class/message. Avoid full provider response/page text in logs.
- Run metadata: generate `run_id` per extraction run; propagate `trace_id` if Langfuse exposes it, otherwise leave nullable.
- CLI should support at least `extract --doc-id DOC --db-path compliance.db` and ideally `extract-all --db-path compliance.db` over ingested documents.

## First Proof / Biggest Unblocker

The riskiest integration point is not Gemini itself; it is converting provider output into a strict six-field record while preserving source grounding and persisting computed compliance values. First proof should avoid live API:

1. Initialize a temp DB.
2. Insert a document and pages with realistic SDF-style text containing all six fields.
3. Inject a fake provider returning those six fields with raw values, normalized dates, confidences, page numbers, and spans.
4. Run the pipeline.
5. Assert:
   - exactly six `extractions` rows exist;
   - `compliance_records` has vendor/doc type/dates;
   - `risk_level`, `risk_reason`, `age_days`, and `compliance_status` are populated;
   - source page/span persisted;
   - retrieval through `list_compliance_records()` is dashboard-ready.

Once this passes, add failure tests for malformed output, missing credentials, missing spans, low confidence, and abstentions. Only after that should live Gemini smoke be attempted.

## Constraints and Gotchas

- **Windows venv command**: S02 found this shell rejects leading `./`; use `venv/Scripts/python.exe`, not `./venv/Scripts/python.exe`, for verification here.
- **Source page numbering**: database uses 0-indexed `pages.page_num`; UI may display 1-indexed later. Provider prompt should explicitly ask for 0-indexed page numbers or pipeline should convert if asking for human page numbers. To avoid ambiguity, use 0-indexed internally and validate against stored pages.
- **Model exactness**: `SDFExtractionRecord` rejects missing/extra fields. Pipeline must synthesize abstentions for any missing field before constructing the record.
- **Abstention still needs evidence object**: `ExtractedField` always requires `SourceEvidence`; abstained fields may omit `verbatim_span` but still need `page_num >= 0`. If a document has zero pages, the current model cannot represent abstentions without inventing a page. Prefer fail-fast typed result for zero-page documents or revisit model if needed.
- **Risk persistence gap**: schema has `risk_reason` and `age_days`, but repository writes `None`; fix this before claiming S03 risk persistence.
- **Date round-trip**: repository currently persists `value_for_dashboard` into `normalized_value`; `_field_from_row()` does not restore `normalized_date`. Risk should be computed before persistence from fresh pipeline records, or risk functions should parse ISO strings robustly when operating on retrieved records.
- **No Gemini dependency/config**: `google-genai` and `GEMINI_API_KEY` settings are absent. Add both; do not make import/config failure break tests or Streamlit startup.
- **No realistic PDF asset**: `tests/fixtures/sample.pdf` is tiny and not realistic. Final milestone acceptance needs at least one realistic SDF-style PDF end-to-end proof. S03 can add a fixture or document a live/demo-only asset path, but the planner should not assume the existing sample is sufficient.
- **No full page-text logging**: ingestion comments explicitly forbid logging page text. Extraction prompts necessarily send page text/images to Gemini, but logs/traces should record doc_id/page counts/error classes only, not full pages or secrets.
- **Langfuse optionality**: existing pattern is local no-op `observe` fallback. Extraction should follow that pattern and never require Langfuse credentials.

## Skill Discovery

Installed skills directly relevant from the prompt:

- `observability` — relevant because S03 introduces unattended pipeline behavior, provider failures, optional Langfuse, and explicit failure states. Applied guidance: keep failure modes typed and observable without logging secret/page-text payloads.
- `tdd` / `test` — relevant because first proof should be a fake-provider integration test before live Gemini.
- `security-review` may be useful before completion because this touches external API calls, file/page content handling, and logging.

External skill search results (not installed):

- `cnemri/google-genai-skills@google-genai-sdk-python` — 83 installs; directly relevant to the `google-genai` SDK adapter. Install command if desired: `npx skills add cnemri/google-genai-skills@google-genai-sdk-python`.
- `cnemri/google-genai-skills@google-adk-python` — 285 installs but less directly relevant; ADK is agent framework, not necessary for a small Gemini SDK adapter.
- Date-related results (`date-normalizer`, timezone tools) are not worth installing for S03 because the project already depends on `python-dateutil` and risk logic should remain small/pure.

## Verification Plan

Use the project Python 3.11 venv:

```bash
venv/Scripts/python.exe -m pytest tests/test_extraction_models.py tests/test_extraction_schema.py tests/test_extraction_persistence.py -q
venv/Scripts/python.exe -m pytest tests/test_extraction_risk.py tests/test_extraction_pipeline.py -q
venv/Scripts/python.exe -m pytest -q
```

Additional targeted checks after CLI exists:

```bash
venv/Scripts/python.exe -m src.extraction.cli extract --doc-id <doc_id> --db-path <tmp-or-demo-db>
venv/Scripts/python.exe -m src.extraction.cli extract-all --db-path <tmp-or-demo-db>
```

Live Gemini smoke should be opt-in and skipped without `GEMINI_API_KEY`; do not put it in default pytest. The smoke should use a realistic SDF-style PDF/page text, then verify `list_compliance_records()` contains source-backed fields or explicit abstentions and a non-null risk/review state.

## Suggested Task Decomposition for Planner

1. **T01 Risk computation and compliance persistence** — pure risk module, model/repository risk fields, risk tests.
2. **T02 Extraction page loader and pipeline contract** — DB page read helper, provider protocol, fake-provider happy path test proving persistence.
3. **T03 Gemini adapter and failure handling** — config/dependency, Gemini adapter, malformed/missing credential/low-confidence/span-mismatch tests.
4. **T04 CLI and smoke proof** — Typer command(s), run metadata/tracing integration, optional realistic PDF smoke path, full regression verification.

This order gives a deterministic proof before live provider work and leaves S04 with populated `compliance_records` rows.