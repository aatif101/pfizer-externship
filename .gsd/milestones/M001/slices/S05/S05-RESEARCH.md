# S05 Research: Validation remediation boundary and end to end proof

## Summary

S05 is a remediation slice, not a feature slice. M001 validation already found the implementation mostly complete, but blocked milestone completion on three evidence/documentation gaps:

1. `M001-ROADMAP.md` has `## Boundary Map` with `Not provided.` even though slice summaries imply clear producer/consumer contracts.
2. There is no durable proof that an actual realistic PDF went through ingestion -> extraction -> risk persistence -> dashboard display. Existing S03/S04 evidence covers realistic page text, fake/mocked providers, SQLite persistence, and dashboard rendering separately.
3. Requirement coverage needs milestone-scoped clarification: R005/R006/R007 are future requirements owned by M002/M003, not M001 failures; R008 is only partially covered in M001 and remains active for later tracing coverage.

Key surprise: `tests/fixtures/sample.pdf` is not suitable for the final proof. A probe using `ingest_document()` produced one page/image but persisted empty page text (`LEN 0`), so extraction would fail with `NoPageTextError` unless the proof uses a better PDF fixture.

## Active requirements this slice owns/supports

- **R008**: S05 should clarify that M001 covers non-fatal Langfuse/Gemini credential behavior and safe diagnostics, while full tracing across retrieval/generation/evaluation remains later scope. Current code supports this: `src/app.py` starts without provider credentials, `src/tracing.py` returns `False` instead of raising on missing/bad Langfuse, and `src/extraction/cli.py`/`src/extraction/gemini.py` sanitize provider errors.
- **R009**: All proof and verification commands should use `venv/Scripts/python.exe` on this Windows repo. Memory note MEM012 says the leading `./venv/...` form is rejected by this shell.
- **R010**: The proof must not require or record local provider tokens. Use fake/mocked provider for durable automated proof; live Gemini can remain optional/manual if credentials exist.
- **R002/R003/R004**: Already validated by S02-S04, but S05 should tie them together with one integrated proof artifact.
- **R005/R006/R007**: Active future requirements, not M001 scope. They need explicit out-of-scope/planned-future coverage in the M001 validation/summary boundary so milestone validation does not treat them as missing M001 deliverables.

## Relevant prior memories

- MEM011: `src.extraction.repository` is the SQLite persistence boundary; validated `SDFExtractionRecord` upserts exactly six `extractions` rows and one `compliance_records` row with FK/placeholder safety.
- MEM016: The extraction pipeline keeps VLM dependencies behind a provider protocol; offline orchestration normalizes to exactly six fields, abstains on unsupported facts, computes risk, and persists without logging raw page text/provider responses.
- MEM017/MEM019: Live extraction providers are lazy/offline-safe; CLI provider construction defaults to lazy Gemini but tests can monkeypatch `build_provider()` to inject fake providers.
- MEM012: Use `venv/Scripts/python.exe` for closeout commands.

## Implementation landscape

### Existing files and purpose

- `src/pipeline/ingest.py`
  - Typer ingestion CLI plus `ingest_document(pdf_path, db_path)`.
  - Performs path/size checks, Docling conversion, pypdfium2 rasterization, `_extract_page_texts()`, and DB writes.
  - Decorated with Langfuse `@observe` when available, but import fallback is non-fatal.

- `src/extraction/cli.py`
  - Typer extraction CLI: `extract` and `extract-all`.
  - Lazy `build_provider("gemini")` seam; tests can monkeypatch fake provider.
  - Safe operator output: doc/run/trace/review diagnostics only; no page text/provider raw output/secrets.

- `src/extraction/pipeline.py`
  - Main integration seam: `extract_document(db_path, doc_id, provider, today=None, run_id=None)`.
  - Loads ingested pages, calls provider protocol, validates spans against page text, normalizes required fields, computes risk, and persists.
  - Throws typed non-secret errors for missing docs/pages/no page text.

- `src/extraction/gemini.py`
  - Gemini provider adapter, lazy/offline-safe import behavior.
  - Missing `GEMINI_API_KEY` raises `ExtractionConfigurationError` only when constructing the provider.
  - Malformed JSON becomes abstained fields, not crash/hidden facts.

- `src/extraction/repository.py`
  - `upsert_extraction_record()`, `get_extraction_record()`, `list_compliance_records()`.
  - Best proof target for rows: six `extractions` rows plus one `compliance_records` row.

- `src/dashboard/compliance.py`
  - Credential-free dashboard adapter/renderer.
  - `load_compliance_rows()` treats missing DB/table as empty state.
  - `format_compliance_rows()` creates display labels; `_render_source_detail()` lazily loads page images.

- `src/app.py`
  - Streamlit shell. Compliance tab delegates to `render_compliance_tab(get_settings().db_path)`.
  - Sidebar Langfuse connection check is intentionally non-fatal.

- `src/db/schema.py` / `src/db/queries.py`
  - Schema/init/migration and DB helper boundaries.
  - `pages.page_num` is 0-indexed; UI displays 1-indexed source pages.

- `tests/test_ingest.py`
  - Uses `tests/fixtures/sample.pdf`, but that fixture produced empty page text in the research probe. Do not rely on it for S05 end-to-end proof.

- `tests/test_extraction_pipeline.py`, `tests/test_extraction_cli.py`, `tests/test_extraction_provider_gemini.py`, `tests/test_compliance_dashboard.py`, `tests/test_app.py`
  - Existing coverage already proves most contract/operational pieces separately.

- `.gsd/milestones/M001/M001-VALIDATION.md`
  - Existing validation verdict is `needs-remediation` and explicitly lists S05 remediation duties.

### Current proof feasibility

Research probe `gsd_exec` run `67700d49-c6ea-4d5b-9ad7-72ae56718349` generated a temporary one-page realistic SDF-style PDF using raw PDF syntax, ingested it with Docling/pypdfium2, ran `extract_document()` with a fake provider grounded in the ingested page text, persisted risk, and formatted dashboard rows. It passed:

```text
doc_id bdf82f8d94c7668f
ingested_pages 1 images 1
risk amber Oldest relevant date 2024-01-05 is 732 days old, between 2 and 3 years. age_days 732
dashboard Acme Pharma Ltd. Page 1 2027-01-31 90%
```

A separate probe `1ceac37d-cb78-4ea5-9628-6c61f4674c64` showed the generated PDF persisted non-empty page text containing all required spans. This makes an automated durable proof practical without live Gemini credentials.

## Recommendation

Implement S05 as documentation/evidence plus a small durable test/proof harness:

1. **Add a deterministic realistic SDF PDF fixture generator** rather than depending on `tests/fixtures/sample.pdf`.
   - Best location: `tests/fixtures/` for the generated fixture file if committed, or a test helper in a new S05/e2e test if generated at runtime.
   - Avoid adding new dependencies; reportlab/fpdf/pypdf are not installed. A minimal text PDF can be produced with raw PDF syntax and works with current Docling ingestion.

2. **Add an automated end-to-end proof test** that exercises the full offline chain:
   - Create/generate realistic PDF.
   - `init_db()` + `ingest_document()`.
   - Assert persisted page text contains the spans.
   - Run `extract_document()` with a fake provider implementing `SDFExtractionProvider`, using the actual ingested `doc_id` and spans.
   - Assert six extraction rows, one compliance row, risk fields, source page/span, run_id/trace_id.
   - Assert `format_compliance_rows()` exposes dashboard-facing values (`vendor_name`, `Page 1`, `source_verbatim_span`, confidence display).
   - Optionally call `render_compliance_tab()` with fake Streamlit if planner wants a renderer-level proof; existing S04 tests already cover renderer behavior, so adapter formatting may be enough for integrated proof.

3. **Record the proof as a durable artifact** under S05, likely `S05-UAT.md` or in the S05 summary when completing the slice.
   - Include command, exit code, gsd_exec id/stdout path, generated PDF properties, persisted row counts, risk output, and dashboard adapter output.
   - Do not include secrets or full page text beyond allowed field evidence spans.

4. **Fill the M001 boundary map** with explicit S01-S04 contracts.
   - Boundary map should mention producer, consumer, contract, status, and watch-outs.
   - Be careful: `M001-ROADMAP.md` may be generated from GSD DB. If there is a GSD-supported roadmap reassessment/update path, prefer it over manual edits. If not, make a minimal targeted edit to replace the `Not provided.` body and note it in S05 summary.

5. **Clarify requirement coverage** in validation/summary artifacts, not by marking future requirements as globally completed/failed.
   - R005: Out of M001; owned by M002.
   - R006: Out of M001; owned by M002.
   - R007: Out of M001; owned by M003.
   - R008: M001 covers non-fatal credential behavior/safe metadata; full tracing remains active for M002/M003.
   - If using GSD requirement tools, update notes/validation text carefully so future active status remains intact.

## Natural seams / suggested task decomposition

### Task A: Boundary and requirement-scope remediation

Files/artifacts:
- `.gsd/milestones/M001/M001-ROADMAP.md` boundary map section or equivalent GSD-rendered roadmap source.
- `.gsd/milestones/M001/M001-VALIDATION.md` or S05 closeout/summary to record remediation.
- `.gsd/REQUIREMENTS.md` only through `gsd_requirement_update` if requirement notes need durable register updates.

Work:
- Replace the empty boundary map with explicit contracts:
  - S01 -> S02/S03/S04: Python 3.11 venv, migrated repo, local-secret hygiene.
  - S02 -> S03: strict six-field models, schema/repository, compliance row shape.
  - S03 -> S04: persisted compliance rows via `list_compliance_records`, page image lookup via `get_page_image`, run/trace/risk metadata.
  - S04 -> M001 validation: offline Compliance tab rendering, friendly no-credential/no-DB states.
- Add M001 scope matrix: R001-R004/R009/R010 covered; R008 partial/advanced; R005-R007 future out-of-scope.

Independent of Task B except final summary should cite both.

### Task B: Durable realistic PDF end-to-end proof

Files likely touched:
- New `tests/test_m001_end_to_end_proof.py` or `tests/test_s05_end_to_end_proof.py`.
- Optionally new helper fixture under `tests/fixtures/` or in `tests/conftest.py`.
- S05 proof artifact (`.gsd/milestones/M001/slices/S05/S05-UAT.md` during completion, or task summary via GSD tools).

Work:
- Generate/use a realistic one-page SDF-style PDF with these exact spans:
  - `Supplier Declaration Form`
  - `Vendor Name: Acme Pharma Ltd.`
  - `Manufacturing Date: 2024-01-05`
  - `Effective Date: 2024-02-01`
  - `Revision Date: 2024-03-15`
  - `Expiry Date: 2027-01-31`
- Run ingestion and assert page text is non-empty and grounded spans are present.
- Use fake provider payloads citing the ingested page and exact spans. Use real `extract_document()` and repository/dashboard adapter code.
- Assert risk is amber for `today=date(2026, 1, 6)` and `age_days == 732`.

This is the highest-risk/first-proof seam because it closes the validator’s explicit blocker.

### Task C: Closeout verification and evidence packaging

Files/artifacts:
- S05 task summaries / S05 summary / S05 UAT.
- Potential requirement updates via GSD tools.

Work:
- Run targeted S05 test and full regression.
- Save proof details with command outputs and exit codes.
- Ensure no generated DB/PDF temp artifacts are left untracked unless intentionally committed.

## First proof to run

Start with an executable proof before spending time on prose:

```bash
venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py -q
```

Expected assertions:
- `ingest_document()` returns `page_count == 1`, `image_count == 1`.
- SQLite `pages.page_text` contains all required spans.
- `extract_document()` persists exactly six field rows and one compliance row.
- Compliance row has `vendor_name == "Acme Pharma Ltd."`, `risk_level == "amber"`, `age_days == 732`, `source_page == 0`, `source_verbatim_span == "2027-01-31"`, `run_id` and `trace_id` populated.
- `format_compliance_rows()` displays `source_page_label == "Page 1"` and `aggregate_confidence_display == "90%"`.

Then run:

```bash
venv/Scripts/python.exe -m pytest -q
```

Prior full S04 closeout was `71 passed, 19 warnings in 111.50s` via gsd_exec `1c1054ab-1c3a-4ff9-a247-d39977fbbb57`. Expect the new full run to take ~2 minutes or more because Docling tests are slow.

## Verification strategy

- Targeted proof test for S05 integrated chain.
- Existing extraction/dashboard tests for regression:
  - `venv/Scripts/python.exe -m pytest tests/test_ingest.py tests/test_extraction_pipeline.py tests/test_compliance_dashboard.py -q`
- Full suite:
  - `venv/Scripts/python.exe -m pytest -q`
- Optional app smoke if changed:
  - `venv/Scripts/python.exe -m pytest tests/test_app.py -q`
- Record proof command(s) via `gsd_exec` so stdout/stderr paths can be cited in S05 completion artifacts.

## Risks and constraints

- `tests/fixtures/sample.pdf` persists empty page text and should not be used for S05 proof.
- Docling ingestion is slow and emits warnings/noisy logs; use `gsd_exec` for proof commands and save compact evidence.
- Live Gemini proof would require secrets and network; it is not necessary for a durable automated proof because the acceptance gap is the integrated PDF-to-dashboard chain, not model accuracy. Keep Gemini optional.
- Raw page text and provider responses should not appear in CLI/test failure output except explicit source evidence spans.
- `.env.example` currently documents Langfuse but not Gemini variables. If S05 touches operator docs, consider adding `GEMINI_API_KEY=` and `GEMINI_MODEL=gemini-2.5-flash`, but this is not required to close validation unless docs are in scope.
- Existing git status contains many GSD-generated/untracked artifacts from prior slices. Do not treat them as S05 code changes unless needed; avoid broad cleanup.

## Skill discovery

Installed skills relevant by role:
- `write-docs`: useful for boundary map and requirement-scope prose; reader-test the milestone artifacts for a fresh validator.
- `observability`: relevant to R008 wording; keep claims limited to current non-fatal/sanitized diagnostics unless adding deeper Langfuse tracing.
- `verify-before-complete`: use before S05 closeout; evidence must be fresh in the completion message.

External skill search results (not installed; user decides):
- Streamlit: `npx skills add streamlit/agent-skills@developing-with-streamlit` (1.3K installs) and `npx skills add streamlit/streamlit@debugging-streamlit` (352 installs). Relevant only if changing dashboard behavior; S05 likely does not need it.
- SQLite: `npx skills add martinholovsky/claude-skills-generator@sqlite database expert` (1.6K installs). Not necessary for the small proof because existing repository patterns are clear.
- pytest: `npx skills add github/awesome-copilot@pytest-coverage` (10.4K installs). Not necessary; existing tests are conventional.
- Docling: `npx skills add existential-birds/beagle@docling` (410 installs). Potentially useful if deeper Docling fixture generation issues appear.
- Gemini: `npx skills add google-gemini/gemini-skills@gemini-interactions-api` (3.7K installs). Not needed for offline S05 proof; live provider is already implemented and mocked tests cover it.

## Sources / evidence gathered

- Memory query: S05/extraction/dashboard prior architecture memories MEM011, MEM016, MEM017, MEM019, MEM012.
- Code reads: `src/pipeline/ingest.py`, `src/extraction/cli.py`, `src/extraction/pipeline.py`, `src/extraction/gemini.py`, `src/extraction/providers.py`, `src/extraction/repository.py`, `src/dashboard/compliance.py`, `src/db/schema.py`, `src/db/queries.py`, `src/app.py`, `src/config.py`, `src/tracing.py`, key tests.
- Validation blocker: `.gsd/milestones/M001/M001-VALIDATION.md`.
- Probe: `tests/fixtures/sample.pdf` ingestion produced empty page text (`gsd_exec` `51d070d9-70a7-4159-b222-9fdf6f140d28`).
- Probe: minimal text PDF produced non-empty Docling page text (`gsd_exec` `1ceac37d-cb78-4ea5-9628-6c61f4674c64`).
- Probe: temporary realistic PDF -> ingestion -> fake-provider extraction -> risk -> dashboard formatting passed (`gsd_exec` `67700d49-c6ea-4d5b-9ad7-72ae56718349`).