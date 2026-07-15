---
phase: "02-extraction-compliance"
plan: "03"
slug: grounded-compliance-integration-gate
status: complete
completed: 2026-07-15
requirements:
  - EXTRACT-01
  - EXTRACT-02
---

# Phase 2 Plan 03 — Grounded Compliance Integration Summary

## Outcome

Extraction is now a conservative compliance boundary rather than a schema-only
model call. Accepted text values are literal persisted-page slices, image-only
claims remain visibly reviewable, packet sections cannot mix across certificates,
and uncertain evidence cannot produce a false-safe compliant verdict. Evaluation
and cost metrics accept only complete manifest-bound source runs with bounded,
internally consistent provenance.

## Grounding and packet rules

- Every accepted text field cites an existing page and an exact, case-sensitive,
  whitespace-preserving source span no longer than 500 characters. Fuzzy matches,
  invalid pages, repeated value-only ambiguity, placeholders, and unsupported
  provider normalization abstain.
- Raw printed values are retained independently from locally normalized dates.
  Supported full dates include ISO/year-first forms, unambiguous numeric forms,
  `01-JAN-2024`, `01JAN2024`, `Jan 1, 2024`, and `YYYYMMDD`. Supported month-only
  forms normalize to `YYYY-MM` without inventing a day and remain review-required.
  Ambiguous numeric dates abstain. A literal not-applicable marker is valid only
  for expiry.
- Strong primary/nonprimary headings are scanned in page order. Headingless
  continuation pages inherit scope, while email/SDS/processing/dosimetry,
  calibration, template, invoice, packing/shipping, certificate-of-other-type,
  and other strong attachment headings close it. Each primary heading starts a
  new stable block; post-merge consistency binds all accepted fields to the
  selected doc-type block and abstains cross-certificate claims.
- Template/draft/example/sample/reference/change headings never masquerade as a
  primary certificate. Specification headings accept no suffix or a bounded
  identifier-like suffix, preventing section prose such as “Specification
  Changes” from reopening scope.
- Date values bind to the target label on their own claim line, or to an
  immediately preceding bare target-label row plus a bare value row. Delivery,
  retest, shipping, competing labels, negated labels, and provisional/currentness
  modifiers cannot borrow target semantics.
- Vendor values require an explicit supplier/vendor/manufacturer/Issued By label,
  a complete relation-bound legal entity, a bounded header with address/contact
  context, or the narrow visual-logo path. Product/material/item/trade names,
  signatories, customer/distributor/laboratory/holder roles, attribute rows, and
  truncated legal entities abstain.
- Text-empty documents never reach the text provider. Image-backed visual claims
  are forced to `needs_review`. The sole mixed-content exception is a vendor logo
  omitted by OCR on an image-backed primary page with a finite positive bounding
  box; it remains visual evidence and cannot become silently trusted. Unmatched
  visual dates still abstain.

## Risk and review behavior

- Expired expiry remains red and can never be weakened by uncertainty elsewhere.
- Otherwise the oldest usable manufacturing/effective/revision date is green
  below two calendar years, amber from the exact two-year through exact
  three-year boundaries, and red beyond three years. Leap-day replacement is
  deterministic and conservative.
- Missing, abstained, malformed, future, partial-month, low-confidence, or visual
  evidence keeps aggregate review visible. A nominal green result with uncertain
  evidence is `needs_review`, never `compliant`; dashboard `needs_review` now agrees
  with the persisted compliance status.

## Usage and evaluation provenance

- Text and visual usage rows persist bounded provider, requested/resolved/pricing
  model identity, candidate/thought/total tokens, latency, estimated cost, trace,
  run, document, stage, status, and stable reason codes only.
- Resolved model identity is immutable within an extraction run. A conflicting
  non-null response fails with `extraction_run_model_mismatch` rather than
  overwriting audit truth.
- Extraction and usage evaluation require a strict complete source run with a
  manifest, corpus version, timestamps, actual resolved model, expected=succeeded,
  and zero failures. Running, partial, failed, missing, count-mismatched, truncated,
  or provenance-inconsistent sources publish no metrics.
- Eval reuse is atomic: type is validated, lifecycle resets to running, stale
  metrics are cleared in the same transaction, and current source params replace
  old provenance.
- Latency and average cost are document-level sums across attempted stages;
  skipped rows do not make metrics look faster. Missing billable usage makes cost
  unknown and lowers the explicit cost-coverage metric rather than silently
  understating spend.
- Params, rows, traces, exceptions, and DTO representations are covered by
  forbidden-sentinel tests for page/field text, spans, images/PDFs, paths, raw
  provider payloads, raw errors, and secrets.

## Adversarial review resolution

An independent HIGH-only audit repeatedly probed the stabilized production path.
Regressions now cover cross-page and same-page certificate mixing, repeated-title
certificates, bare and mixed-case attachment headings, flattened multi-column
vendor tables, relation-prefix truncation, non-vendor organization roles,
attribute tails, competing/multi-line date labels, provisional dates, template
false-safe records, and Specification section aliases. The final six-field matrix
found no reproducible HIGH false-safe and cleared Phase 2 grounding/risk for
commit.

## Verification evidence

- Grounding, visual fallback, and risk:
  `venv\Scripts\python.exe -m pytest tests\test_extraction_pipeline.py tests\test_extraction_risk.py tests\test_visual_fallback_pipeline.py -x -q --tb=short`
  — **163 passed** in 43.84s.
- Usage and completed-source-run evaluation:
  `venv\Scripts\python.exe -m pytest tests\test_extraction_usage_observations.py tests\test_extraction_usage_eval_metrics.py tests\test_extraction_eval_runner.py -x -q --tb=short`
  — **54 passed** in 15.81s.
- Complete Phase 2 Windows gate (PowerShell-expanded `test_extraction_*.py` plus
  visual fallback and eval schema): **342 passed** in 76.94s.
- Dependency integrity:
  `venv\Scripts\python.exe -m pip check` — **No broken requirements found**.
- Full offline Windows repository regression:
  `venv\Scripts\python.exe -m pytest tests -q --tb=short`
  — **635 passed, 8 skipped, 14 warnings** in 181.37s.
- Runtime: **Python 3.11.9**. The skips are explicit optional/GPU integration
  cases; warnings are upstream Torch JIT deprecations exercised by ingestion.
- `compileall` and `git diff --check`: passed.

## Remaining external evidence

No paid-provider or private-corpus number was fabricated during this offline
phase. Live model-profile checks and frozen public holdout results belong to the
benchmark/release work that follows; they must use the completed run/provenance
contract above.
