---
phase: quick-260610-o8z
plan: 01
subsystem: extraction
tags: [gemini, pydantic, sqlite, extraction-grounding, visual-evidence, compliance, ragas-free-eval]

requires:
  - phase: M004 S04 (visual fallback)
    provides: visual fallback planner + normalization path that this tier extends
provides:
  - Shared SDF field rulebook (docs/field-definitions.md) governing prompts AND gold labels
  - effective_date synonym support (Approved On / Issue Date / Date of Issue)
  - Literal "N/A" expiry handling (not abstained)
  - Visual evidence tier (evidence_type='visual') for empty-page-text scanned pages, needs_review forced on
  - Additive evidence_type / source_evidence_type schema columns with idempotent migration
  - Idempotent gold relabel script (CPC -> Colder Products Company)
  - D027 decision superseding D026
affects: [dashboard, extraction-eval, compliance-verdict]

tech-stack:
  added: []
  patterns:
    - "Tiered evidence grounding: text (verbatim-verified) vs visual (page-cited + review-flagged)"
    - "Single shared rulebook governing both extraction prompts and gold labels"
    - "Additive nullable column migration coalescing NULL to a safe default on read"

key-files:
  created:
    - docs/field-definitions.md
    - scripts/relabel_gold_field_rules.py
  modified:
    - src/extraction/models.py
    - src/extraction/pipeline.py
    - src/db/schema.py
    - src/extraction/repository.py
    - src/extraction/gemini.py
    - .gsd/DECISIONS.md
    - tests/test_visual_fallback_pipeline.py
    - tests/test_extraction_schema.py
    - tests/test_extraction_persistence.py

key-decisions:
  - "D027: visual evidence tier supersedes D026 — empty stored page text accepts image-grounded value as evidence_type='visual' + needs_review; non-empty failed match still abstains"
  - "One shared rulebook (docs/field-definitions.md) is the single source of truth for prompts and gold labels"

patterns-established:
  - "Pattern 1: evidence_type tags every SourceEvidence ('text' default | 'visual'), persisted and round-tripped"
  - "Pattern 2: visual-prompt labeling rules phrased generically to avoid leaking non-requested field names into the allowlist"

requirements-completed: []

duration: ~55min
completed: 2026-06-10
---

# Phase quick-260610-o8z Plan 01: Compliance Verdict Fix — Shared Field Rulebook + Visual Evidence Tier Summary

**Shared SDF field rulebook (effective_date synonyms, literal "N/A" expiry, full legal vendor names) plus an additive `evidence_type` visual-evidence tier that accepts image-grounded values only when the cited page's stored text is empty — lifting macro extraction F1 from 0.228 to 0.46 on the 5 real docs, with effective_date going 0.0 -> 1.0.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3
- **Files modified:** 9 (2 created, 7 modified)
- **Tests:** 308 passed (full suite green)

## Accomplishments

- **Shared rulebook** (`docs/field-definitions.md`) is the single source of truth for both Gemini prompts and gold labels: effective_date synonyms ("Approved On" / "Issue Date" / "Date of Issue"), literal "N/A" expiry, full legal vendor names, with all trap-date exclusions preserved.
- **Visual evidence tier (D027, supersedes D026):** when a cited page's stored text is EMPTY, an image-grounded value is accepted with `evidence_type='visual'`, page citation preserved, and `needs_review` forced on. Stored-text pages keep the verbatim `evidence_type='text'` contract unchanged; a failed match against non-empty text still abstains. Trap/placeholder guard runs for both tiers.
- **Additive schema:** `evidence_type` on `extractions`/`extraction_history`, `source_evidence_type` on `compliance_records`/`compliance_record_history`, with an idempotent migration; NULL-at-rest coalesces to "text" on read. Round-trips through persistence.
- **Idempotent gold relabel script** (`scripts/relabel_gold_field_rules.py`): 144fc1ed `vendor_name` "CPC" -> "Colder Products Company"; second run changes 0 rows.
- **Validation run** over the 5 real docs with the new rulebook + visual fallback: macro F1 0.228 -> 0.46; effective_date F1 0.0 -> 1.0.

## Task Commits

1. **Task 1: Field rulebook, prompt updates, gold relabel script** — `bb6945a` (feat) + `0f54d77` (fix: doc_id prefix match in relabel script)
2. **Task 2: Visual evidence tier (schema + model + pipeline + persistence)** — `0be1c20` (test, RED) -> `cf6313a` (feat, GREEN)
3. **Task 3: D027 supersession + visual-prompt allowlist fix** — `7077ae2` (feat)

_Plan metadata commit handled by the orchestrator._

## Files Created/Modified

- `docs/field-definitions.md` (created) — shared labeling rulebook for the six SDF fields.
- `scripts/relabel_gold_field_rules.py` (created) — idempotent gold relabel; prints only doc_id/field_name/row counts; never commits any .db.
- `src/extraction/models.py` — `SourceEvidence.evidence_type` (default "text", validated to {text, visual}).
- `src/extraction/pipeline.py` — tiered `_normalize_field`: text-match / abstain / empty-text visual accept.
- `src/db/schema.py` — additive `evidence_type` / `source_evidence_type` columns + `_migrate_evidence_type_columns`.
- `src/extraction/repository.py` — thread `evidence_type` through extractions, history, and compliance persistence.
- `src/extraction/gemini.py` — both prompts follow the rulebook; visual prompt rules reworded to avoid allowlist leakage.
- `.gsd/DECISIONS.md` — append-only D027 superseding D026.
- `tests/test_visual_fallback_pipeline.py`, `tests/test_extraction_schema.py`, `tests/test_extraction_persistence.py` — new visual-tier + schema tests and additive column expectations.

## Validation Results (5 real docs, honest)

Gold relabel applied to `compliance.db` first (1 row changed, idempotent on rerun). New extraction run `o8z-rulebook-visual-20260610` (`extract-all --visual-fallback`), all 5 docs succeeded.

**Per-field F1 (extraction eval vs gold):**

| Field | BEFORE (text-baseline-20260607) | AFTER (o8z-rulebook-visual-20260610) |
|-------|-------------------------------|--------------------------------------|
| doc_type | 0.889 | 0.600 |
| effective_date | 0.000 | **1.000** |
| expiry_date | 0.000 | **0.500** |
| manufacturing_date | 0.000 | 0.000 |
| vendor_name | 0.250 | 0.200 |
| **macro F1** | **0.228** | **0.460** |

**New compliance risk levels (AFTER):**

| doc_id | vendor_name | effective_date | expiry_date | risk_level | status |
|--------|-------------|----------------|-------------|------------|--------|
| 144fc1ed | Colder Products Company | 2025-12-19 | (none) | green | compliant |
| 5543408c (Cytiva) | STERIS | (abstained) | (abstained) | unknown | needs_review |
| 8652295b | Thermo Fisher Scientific, Inc | 2023-04-26 | **N/A** (literal) | unknown | needs_review |
| e61aa905 (Innophos) | Innophos Inc. | **2025-05-22** | (none) | green | compliant |
| e89fa720 | DFE Pharma GmbH & Co. KG | 2024-10-29 | (none) | green | compliant |

**Plan-predicted outcomes vs actual (honest):**

- **e61aa905 (Innophos) effective_date 2025-05-22** — CONFIRMED. The "Approved On: 22MAY2025" synonym is now extracted via the text tier. effective_date F1 0.0 -> 1.0.
- **8652295b expiry literal "N/A"** — CONFIRMED. Stored as the literal value "N/A", not abstained.
- **144fc1ed stays unknown (no gold dates)** — PARTIAL DIVERGENCE. The model now extracts an effective_date (2025-12-19) that the gold set does not label, so the doc reads "green/compliant" rather than staying date-free. This is honest model behavior, not a fudge; gold has no date label for this doc so it does not score.
- **5543408c (Cytiva) expiry_date 2023-01-26 via visual on empty page -> red** — NOT REALIZED. The model classified the doc as a "Certificate of Processing" and abstained on both expiry and effective_date; the visual fallback did not surface the expiry. The Cytiva doc DOES have empty-text image pages (pages 0,1,2,7 have page_text length 0 with images), so the visual tier code path was reachable, but the live model chose to abstain rather than cite an image-grounded expiry. All extracted fields this run were `evidence_type='text'` — the visual tier did not fire on live data.

**Important:** the visual tier is fully correct and deterministically tested (empty-page-text accept, non-empty failed-match abstain, text-tier evidence_type, persistence round-trip), but on this particular live run the model did not produce an image-grounded value, so no `evidence_type='visual'` row was persisted. The deterministic parts (schema, guard logic, prompts, gold script, tests) are fully correct regardless.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Relabel script matched short doc_id against stored full-hash id**
- **Found during:** Task 3 validation (gold relabel run)
- **Issue:** Gold labels store full doc-id hashes (`144fc1ed53c972f0`), but the rulebook uses the short id `144fc1ed`; an exact `WHERE doc_id = '144fc1ed'` matched 0 rows.
- **Fix:** Match by prefix (`WHERE doc_id LIKE '144fc1ed%'`), still guarded on `expected_value` for idempotency.
- **Files modified:** scripts/relabel_gold_field_rules.py
- **Verification:** First run changed 1 row, second run changed 0 rows.
- **Committed in:** `0f54d77`

**2. [Rule 1 - Bug] Visual prompt labeling rules leaked non-requested field names**
- **Found during:** Task 3 (full suite)
- **Issue:** `test_visual_prompt_contains_only_requested_field_allowlist` asserts the visual prompt does not contain non-requested field names; my Task 1 addition hardcoded "vendor_name"/"effective_date"/"expiry_date" into the visual prompt's rules block, breaking the allowlist guarantee (a correctness/security boundary).
- **Fix:** Reworded the three visual-prompt rules generically ("a vendor", "an effective date", "an expiry") so no bare field-name tokens appear; the text prompt is unaffected since it lists all six fields anyway.
- **Files modified:** src/extraction/gemini.py
- **Verification:** test_extraction_gemini_visual.py green; "Approved On" still present.
- **Committed in:** `7077ae2`

**3. [Rule 3 - Blocking] Live compliance.db needed migration before extraction**
- **Found during:** Task 3 validation (first extract-all attempt)
- **Issue:** `extract-all` does not call `init_db()`; the pre-existing live `compliance.db` lacked the new `evidence_type` column, so persistence failed with "table extractions has no column named evidence_type".
- **Fix:** Ran `init_db('compliance.db')` once to apply the idempotent additive migration (local DB only — gitignored, not committed).
- **Verification:** All four new columns present; extraction of all 5 docs then succeeded.
- **Committed in:** N/A (local DB mutation only; migration code committed in `cf6313a`).

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness/validation. No scope creep. Additive schema and rulebook contract preserved.

## Issues Encountered

- The visual evidence tier did not fire on the live run: the model abstained on the Cytiva doc rather than citing an image-grounded expiry. This is a live-model outcome, not a code defect — the empty-page-text path is reachable and deterministically tested. Documented honestly above; not retried endlessly.
- Langfuse "Authentication error" / "Context error" warnings appeared during extraction (no LANGFUSE keys in this env). These are non-fatal tracing warnings; extraction and persistence completed.

## Next Phase Readiness

- Compliance verdict materially improved: 3 of 5 docs now resolve to green/compliant with real dates; effective_date extraction is reliable.
- Open follow-ups (not in scope here): manufacturing_date still F1 0.0; vendor_name F1 dropped slightly (model now returns differently-cased/legal-form names that diverge from gold — a future gold-rulebook reconciliation candidate); the visual tier is unexercised on live data and would benefit from a doc where the model is steered to cite a scanned-page value.

## Self-Check: PASSED

- Created files exist: docs/field-definitions.md, scripts/relabel_gold_field_rules.py, SUMMARY.md
- Commits exist: bb6945a, 0be1c20, cf6313a, 7077ae2, 0f54d77
- Full suite: 308 passed
- No .db committed (compliance.db gitignored)

---

## Follow-up (continuation: risk N/A handling + Cytiva visual diagnosis)

Continued committed work bb6945a..0f54d77, run directly in the main repo (no worktree).

### Item 1 — risk.py printed-"N/A" expiry handling (deterministic fix, DONE)

Per `docs/field-definitions.md`, a printed "N/A" expiry is extracted as the literal
value `"N/A"` (a real "no expiry" assertion). `risk._field_date` previously treated
`"N/A"` as an ambiguous/invalid date and returned an error, parking doc `8652295b`
at `risk_level='unknown'` with reason `expiry_date has an ambiguous or invalid date
value: 'N/A'`.

- **Fix:** `_field_date` now treats not-applicable markers (`N/A`, `N.A.`, `NA`,
  `Not Applicable`, case- and whitespace-insensitive) on a date field as
  "no date present" (`_ParsedDate(None, False, "")`) instead of an error. Risk then
  falls through to age-based scoring on manufacturing/effective/revision dates.
  Convention documented in the module docstring and a focused comment referencing
  the field-definitions rulebook.
- **Tests added** (`tests/test_extraction_risk.py`): (a) N/A expiry + effective_date
  2023-04-26 with today=2026-06-10 → `red` (age 1141 days, over 3-year threshold);
  (b) N/A expiry alone with no other dates → `unknown`/`needs_review`; (c) N/A marker
  variants treated as no-date. Risk suite: 11 passed. Full suite: **311 passed**.
- **Recompute:** added `scripts/recompute_compliance_risk.py` (no provider/network
  calls — re-derives risk from the latest stored field values via
  `compute_record_risk` and re-persists). Ran with `--today 2026-06-10`.

**Final risk_level per doc (today=2026-06-10), persisted in compliance_records:**

| doc_id | vendor | expiry | effective | risk_level | status |
| --- | --- | --- | --- | --- | --- |
| 144fc1ed | Colder Products Company | None | 2025-12-19 | green | compliant |
| 5543408c | STERIS | None | None | unknown | needs_review |
| 8652295b | Thermo Fisher Scientific | N/A | 2023-04-26 | **red** | at_risk |
| e61aa905 | Innophos Inc. | None | 2025-05-22 | green | compliant |
| e89fa720 | DFE Pharma GmbH & Co. KG | None | 2024-10-29 | green | compliant |

Doc `8652295b` moved `unknown → red` as expected (effective 2023-04-26, age 1141
days, over the 3-year threshold). The printed-N/A expiry no longer errors.

Commits: `76ca7b5` (fix risk N/A), `f2ef4e4` (recompute script).

### Item 2 — Cytiva/STERIS doc 5543408c visual abstention (diagnosis only, NO bug)

(Note: the doc_id `5543408c` resolves to vendor **STERIS** in the DB, on a
"Certificate Of Processing" primary sub-document — not Cytiva.)

**What the validation run persisted (`o8z-rulebook-visual-20260610`):**
- Text extraction picked the primary cert on page 3 (STERIS, Certificate Of
  Processing) and abstained on all four date fields ("...does not contain a
  [date] for the product/material").
- `visual_fallback` usage observation: `status=abstained`, `reason=no_fields_improved`,
  4527 tokens, ~$0.0007 — i.e. the visual provider **was** called.

**Candidate selection is NOT the bug.** All 11 pages have an `image_blob`, including
the scanned page 2 (text_len=0). `build_visual_fallback_request_plan` selects pages
purely by `image_blob is not None` (no text-relevance filter), and
`_build_visual_contents` sends every selected page image. So **page 2 was included**
in the visual request — empty-text scanned pages are eligible candidates.

**Single bounded visual re-run (1 API call, ~$0.0008)** on the eligible date fields
returned the money-shot:
- `expiry_date = 20230126 → 2023-01-26`, **page 2**, confidence 1.0, span `20230126`
- `manufacturing_date = 20210126 → 2021-01-26`, page 2, confidence 1.0
- effective_date / revision_date: abstained

So the model **does** see page 2 and **does** return expiry 2023-01-26. Feeding that
visual result through the real pipeline (`_normalize_fields` → `_merge_visual_fallback_fields`
→ `compute_record_risk`) produces: expiry `needs_review`, `evidence_type=visual`,
page 2 → **risk_level=red** ("Expiry date 2023-01-26 is before 2026-06-10"). The code
path is correct end-to-end; the merge gate accepts visual values on empty-text pages.

**Conclusion: the validation-run abstention was model non-determinism, not a code
bug.** Different Gemini calls return different things for the same scanned pages: the
validation run abstained on the dates, an earlier run (`vf-candidate-20260607`) got
this doc to **red**, and the diagnostic re-run returned the correct page-2 expiry. Per
instructions, retries were not looped. No deterministic fix exists short of attacking
model non-determinism (out of scope). No code change committed for Item 2.

DB state was restored after diagnosis: the latest `compliance_records` row and
history for 5543408c were reset to the `o8z-rulebook-visual-20260610` validation-run
values, and the transient diagnostic re-run rows were deleted from history/usage/runs.
Never staged compliance.db or .env.

---
*Phase: quick-260610-o8z*
*Completed: 2026-06-10*

## Final orchestrator re-run (2026-06-10)

After the diagnosis confirmed the pipeline was correct and the abstention was model
non-determinism, the orchestrator ran the production CLI once more for the STERIS doc:

`venv\Scripts\python.exe -m src.extraction.cli extract --doc-id 5543408c4dacc48b --db-path compliance.db --visual-fallback --run-id verdict-fix-rerun-20260610`

Result persisted: expiry_date=2023-01-26 (page 2, confidence 1.0, evidence_type='visual'),
manufacturing_date=2021-01-26, doc_type='Certificate of Quality', vendor='Global Life
Sciences Solutions USA LLC' — verdict **red / at_risk** ("Expiry date 2023-01-26 is
before 2026-06-10"), needs_review=1 per the visual-evidence tier (D027).

Final dashboard state on the real 5-doc corpus: **3 green, 2 red, 0 unknown** (5543408c red via visual-evidence expiry; 8652295b red via N/A-expiry + 3-year age rule; 144fc1ed/e61aa905/e89fa720 green; no doc remains in the old all-unknown state). Known caveat: visual fallback outcomes
are non-deterministic run to run; deterministic decoding (temperature/seed) is a
candidate future hardening task.
