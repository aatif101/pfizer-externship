# S04: Targeted visual fallback extraction — UAT

**Milestone:** M004
**Written:** 2026-06-07T23:07:44.750Z

# S04 UAT: Targeted Visual Fallback Extraction

**UAT Type:** Contract + Integration (provider-free pipeline tests and Gemini adapter tests with fake SDK client; live Gemini API and real five-document UAT deferred to S05)

---

## Preconditions

- Python venv with all S04 dependencies installed (`venv/Scripts/python.exe`).
- `compliance.db` schema includes page image blobs accessible by page index (used by integration tests with in-memory SQLite and fake blobs).
- S01 run-scoped history and S03 bounded usage observation surfaces are present (`src/extraction/repository.py`, `src/eval/repository.py`).
- No live Gemini API key required for these tests — fake SDK client and fake part factory are injected.

---

## Scenario 1: Eligibility filtering — only abstained or needs-review fields are eligible

**Steps:**
1. Run `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py -k eligib`.
2. Inspect eligibility helper output for a record with mixed PENDING / ABSTAINED / NEEDS_REVIEW fields.

**Expected outcome:**
- PENDING (grounded) fields produce a skip reason code and are excluded from the visual fallback request.
- ABSTAINED and NEEDS_REVIEW fields produce `field_abstained` or `field_needs_review` reason codes and are included.
- No field values, spans, page text, or local paths appear in reason codes.

---

## Scenario 2: Conservative merge arbitration — PENDING text values are never replaced

**Steps:**
1. Run `venv/Scripts/python.exe -m pytest -q tests/test_visual_fallback_pipeline.py -k merge`.
2. Construct a fake pipeline run where a PENDING text field and an ABSTAINED field coexist; visual fallback returns a candidate for both.

**Expected outcome:**
- The PENDING text field value is unchanged after merge arbitration.
- The ABSTAINED field is upgraded to the visual candidate.
- NEEDS_REVIEW fields are upgraded only if the visual candidate is PENDING; a NEEDS_REVIEW visual candidate does not replace a NEEDS_REVIEW text result.

---

## Scenario 3: Visual fallback usage observations — bounded telemetry only

**Steps:**
1. Run `venv/Scripts/python.exe -m pytest -q tests/test_extraction_usage_observations.py`.
2. Query `list_extraction_usage_observations()` for a run that exercised the visual stage.

**Expected outcome:**
- Observations with `stage='visual_fallback'` are persisted for complete, skipped, and error paths.
- No raw prompts, page text, provider payloads, image bytes, PDF content, secrets, or local file paths appear in any observation row.
- Sanitized reason codes (e.g., `not_configured`, `no_eligible_fields`, `missing_page_images`, provider error class) are present for non-complete paths.

---

## Scenario 4: Gemini visual provider — image parts sent correctly, malformed responses abstain safely

**Steps:**
1. Run `venv/Scripts/python.exe -m pytest -q tests/test_extraction_gemini_visual.py`.

**Expected outcome:**
- Image bytes are passed as SDK image parts to the Gemini client (verified via fake part factory injection).
- Provider output is filtered to the eligible request allowlist; extra fields returned by the model are discarded.
- Malformed or empty provider responses produce safe abstentions rather than raising exceptions.
- No local paths, secrets, or raw prompts appear in any assertion.

---

## Scenario 5: CLI opt-in — `--visual-fallback` activates fallback; default runs are unchanged

**Steps:**
1. Run `venv/Scripts/python.exe -m pytest -q tests/test_extraction_cli.py`.
2. Verify that tests covering default `extract` and `extract-all` commands assert no visual provider is constructed.
3. Verify that tests covering `--visual-fallback` assert the visual provider is composed using the same provider name as the text provider.

**Expected outcome:**
- Default text-only extraction behavior is unaffected by S04 changes.
- `--visual-fallback` flag constructs and injects the `GeminiVisualFallbackProvider` into the pipeline.
- Run history and usage observations persist correctly under both modes.

---

## Edge Cases

| Case | Expected |
|------|----------|
| No eligible fields (all PENDING) | Visual stage is skipped; `no_eligible_fields` observation persisted |
| Visual provider not configured | Visual stage is skipped; `not_configured` observation persisted |
| Page images missing from DB for eligible fields | Visual stage skipped/errors per field; `missing_page_images` reason code persisted |
| Gemini returns fields not in the eligible request | Extra fields silently discarded; only requested eligible fields used in merge |
| Gemini client raises exception | Safe abstention returned; error class code persisted in observation; pipeline continues |
| NEEDS_REVIEW text field + NEEDS_REVIEW visual candidate | Text result preserved; visual candidate does not upgrade a NEEDS_REVIEW result |
