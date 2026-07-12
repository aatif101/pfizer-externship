# Phase 2: Extraction & Compliance - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Mode:** Autonomous smart discuss (recommendations auto-accepted under the user's explicit decision delegation)

<domain>
## Phase Boundary

Deliver a reliable baseline extraction and compliance subsystem for every ingested supplier PDF: extract the six required SDF fields into validated models, ground each accepted value in an exact source span and page, abstain when support is missing, calculate the deterministic green/amber/red compliance band, and persist auditable run-scoped results. This phase hardens and verifies the substantial extraction code already present; the multi-pass critic/confidence ensemble remains Phase 5 scope.

</domain>

<decisions>
## Implementation Decisions

### Structured extraction contract
- [D-02-01] Gemini requests use a strict response schema for exactly `doc_type`, `vendor_name`, `manufacturing_date`, `effective_date`, `revision_date`, and `expiry_date`; provider JSON is still treated as untrusted and revalidated with Pydantic.
- [D-02-02] A non-abstained field is accepted only when its page number is valid and its short verbatim span is present on that source page; unsupported, placeholder, or cross-packet values abstain instead of being guessed.
- [D-02-03] Dates normalize to ISO `YYYY-MM-DD` when parseable while preserving the raw printed value and evidence; printed `N/A` expiry remains an explicit supported no-expiry value.
- [D-02-04] The primary product/material certificate controls packet extraction; email, delivery, retest, handwritten, and unrelated attachment dates cannot silently populate compliance fields.

### Compliance and review behavior
- [D-02-05] Compliance risk is deterministic: expired expiry is red; otherwise age is based on the oldest usable manufacturing/effective/revision date, with green under 2 years, amber from 2 through 3 years, red over 3 years, and unknown evidence routed to review.
- [D-02-06] Fields below the configurable confidence threshold (default `0.75`) or any abstained field surface as `needs_review`; the baseline provider confidence is not presented as a calibrated probability.
- [D-02-07] Extraction writes are run-scoped and resumable: a batch has a terminal status, provider failures are counted safely, reruns are idempotent for the same run/document, and one failed document cannot leave the run falsely reported as complete.
- [D-02-08] Raw page text, images, provider payloads, filesystem paths, and secrets never enter logs or Langfuse metadata; traces carry only bounded identifiers, status, counts, model, latency, tokens, and cost.

### July 2026 runtime truth
- [D-02-09] The Gemini model remains environment-configurable. The project documents `gemini-2.5-flash` as the low-cost benchmark model through its announced October 16, 2026 shutdown and supports the stable `gemini-3.5-flash` quality profile without code changes.
- [D-02-10] Cost estimation uses a model-keyed July 2026 pricing table and returns unknown for unrecognized models rather than silently applying stale prices.
- [D-02-11] Provider response schemas, pricing metadata, retry bounds, and model IDs are covered by offline tests; live benchmark results must record model, date, corpus version, run ID, and actual provider usage.

### the agent's Discretion
- Exact Pydantic schema adapter shape for the Google GenAI SDK, as long as fake-client seams remain offline-safe.
- Whether resumability is implemented as document-level status rows or derived from run history, provided the behavior and audit trail are deterministic.
- Internal helper/module boundaries and migration mechanics that preserve compatibility with existing databases.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/extraction/models.py` already defines the six-field Pydantic contract, evidence, review states, and aggregate helpers.
- `src/extraction/gemini.py` already provides lazy/offline-safe Gemini text and image adapters, bounded retry, prompt policy, parsing, usage metadata, and cost estimation seams.
- `src/extraction/pipeline.py`, `repository.py`, and `risk.py` already enforce grounding, abstention, persistence, run history, and deterministic risk behavior.
- `tests/test_extraction_*.py` provides broad unit/integration coverage and fake-provider seams.

### Established Patterns
- Heavy/provider dependencies import lazily; tests run without credentials or network access.
- SQLite migrations are idempotent and repository functions use parameterized SQL.
- Trace metadata follows explicit allowlists and never contains document content.
- Public DTOs are narrow, immutable where practical, and reason-coded for safe failure.

### Integration Points
- `src/extraction/cli.py` owns single-document and batch orchestration.
- `src/db/schema.py` and `src/extraction/repository.py` own extraction/compliance history.
- `src/dashboard/compliance.py` consumes persisted review/risk fields.
- `src/eval/extraction_eval_runner.py` consumes run-scoped predictions and must receive terminal, reproducible runs.

</code_context>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` — Phase 2 goal and success criteria.
- `.planning/REQUIREMENTS.md` — `EXTRACT-01` and `EXTRACT-02` contracts.
- `docs/field-definitions.md` — canonical field semantics and exclusions.
- `src/extraction/models.py` — existing extraction schema.
- `src/extraction/gemini.py` — provider boundary and prompt.
- `src/extraction/pipeline.py` — validation/grounding orchestration.
- `src/extraction/risk.py` — compliance rules.
- `src/extraction/repository.py` and `src/db/schema.py` — persistence/migrations.
- `tests/test_extraction_*.py` — existing behavioral contracts.

</canonical_refs>

<specifics>
## Specific Ideas

- Preserve the current safety posture: a missing or questionable field is visibly abstained and reviewed, never filled to improve a headline metric.
- Separate benchmark quality profiles from cost profiles so the same frozen corpus can compare `gemini-2.5-flash` and `gemini-3.5-flash` honestly.
- Fix quality measurement rather than optimizing against its current blind spots; null gold cells and provider failures must be explicitly accounted for in the later evaluation phase.

</specifics>

<deferred>
## Deferred Ideas

- Extraction critic, self-consistency, confidence ensemble, and reconciliation: Phase 5.
- Human correction UI and audit workflow: Phase 6.
- Held-out public/private benchmark reporting and model comparison: Phase 7.

</deferred>

---

*Phase: 02-extraction-compliance*
*Context gathered: 2026-07-11 via autonomous smart discuss*
