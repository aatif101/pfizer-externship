# M004: Real SDF Extraction Evaluation Hardening

**Gathered:** 2026-06-03
**Status:** Ready for planning

## Project Description

The Pfizer SDF Intelligence System already ingests pharmaceutical supplier PDFs, extracts six structured SDF fields, computes compliance risk, supports grounded text RAG, and displays Compliance, Chat, and Eval dashboards. A local confidential 5-document SDF baseline has been built from already-ingested supplier PDFs in `compliance.db`, with human-approved gold extraction labels and measured extraction/retrieval baselines.

M004 hardens that real SDF extraction evaluation workflow so baseline and candidate runs can coexist, be inspected, costed, and compared without latest-write ambiguity. It also adds targeted visual extraction fallback for fields where text-only extraction abstains or is suspicious, using stored page images from local SQLite only.

## Why This Milestone

The real text-only baseline exposed a text-layer ceiling: visually present certificate values are sometimes missing or poorly represented in Docling page text. Prompt-only packet policy improved `doc_type` but reduced overall macro F1, and the Compliance tab currently reflects latest persisted rows rather than a selected extraction run. M004 is needed now so the next visual candidate can be measured honestly against the real baseline without overwriting or confusing previous run meaning.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Select and inspect a specific extraction run in the Compliance dashboard instead of relying on ambiguous latest-write state.
- Run a targeted visual-fallback extraction candidate over the existing 5 local SDFs and compare it against the real text baseline and packet-aware candidates.
- See token and estimated cost metrics for Gemini extraction work alongside quality metrics.
- Confirm confidential PDFs, local DBs, page images, and snapshots remain ignored and uncommitted.

### Entry point / environment

- Entry point: Streamlit dashboard plus extraction and evaluation CLI/test workflows.
- Environment: Local Windows development environment using the project Python 3.11 virtualenv.
- Live dependencies involved: local SQLite `compliance.db`, local stored page image blobs, Gemini API through `google-genai`, Streamlit browser verification.

## Completion Class

- Contract complete means: schema migration, repository, provider, pipeline, dashboard, eval, and visual fallback contracts have deterministic tests with fake or mocked providers.
- Integration complete means: the existing 5-document local `compliance.db` can produce a final visual-fallback candidate run and comparison metrics without corrupting previous baseline/candidate meaning.
- Operational complete means: dashboard browser verification passes, no confidential local artifacts are tracked, and Windows-native verification evidence exists.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Two or more extraction runs for the same document can be stored and queried independently while latest-write compatibility remains intact.
- The Compliance dashboard can select and label a specific extraction run, and the Eval tab can compare final candidate metrics against known baseline/candidate runs.
- Targeted visual fallback uses stored page images only for eligible suspicious/missing fields and does not overwrite good grounded text values.
- Gemini usage/cost observations are bounded, aggregate into eval metrics, and do not store raw prompts, page text, provider payloads, image bytes, or secrets.
- The final real 5-document candidate comparison is produced from local `compliance.db` with confidential artifacts ignored.

## Architectural Decisions

### Additive run-scoped extraction history

**Decision:** Add run-scoped extraction and compliance history alongside the existing latest-write `extractions` and `compliance_records` tables.

**Rationale:** This avoids a risky canonical rewrite while solving the core problem: candidate runs must not overwrite the meaning of baseline results. Existing tests and dashboard code can keep using compatibility/latest-write rows until run-aware surfaces are added.

**Alternatives Considered:**
- Full canonical rewrite — cleaner long-term but too risky for one milestone and likely to break existing repository/dashboard assumptions.
- Dashboard-only selector — faster but does not truly preserve per-run compliance rows.

### Targeted visual fallback

**Decision:** Run visual fallback only for abstained, placeholder-blocked, ungrounded, low-confidence, or missing key fields.

**Rationale:** The real baseline showed specific text-layer gaps. Running vision for every field would increase cost and false-positive risk. Targeting suspicious fields makes visual fallback a measured extraction improvement, not a wholesale replacement.

**Alternatives Considered:**
- All-field visual pass — simpler as a candidate but higher cost and more arbitration risk.
- Manual page-only visual pass — cheap but less repeatable and less suitable for auto-mode.

### Bounded Gemini usage observations

**Decision:** Persist bounded extraction usage observations keyed by extraction run, document, stage, model, status, token counts, estimated cost, and sanitized error reason.

**Rationale:** The project already uses bounded RAG observations and eval metrics. Mirroring that pattern gives local cost visibility without leaking prompts, page text, provider payloads, image blobs, or secrets.

**Alternatives Considered:**
- Eval metrics only — simpler but loses per-document and per-stage debug value.
- Langfuse traces only — less reliable because Langfuse is optional and currently disabled without keys.

## Error Handling Strategy

M004 applies sensible defaults now and defers deeper failure-mode design. Schema migration must be additive and idempotent. Partial extraction runs preserve successful document results and record sanitized failed-call status without deleting prior history. Missing image blobs skip visual fallback for that page/field and retain the text result or abstention. Gemini visual failures record bounded failure observations and do not crash the whole batch. Missing usage metadata persists null token/cost values rather than misleading zeros. Cost is labeled estimated unless authoritative billing data exists. Visual candidates must not overwrite good grounded text values. Dashboard empty states must not crash when run history is absent or a selected run has no rows.

Deferred deeper handling includes retry/circuit-breaker tuning, resumable checkpoints, richer failure taxonomy, cost budget enforcement, provider fallback across Gemini/Claude, and run archive/cleanup flows.

## Risks and Unknowns

- Gemini usage metadata shape may vary — parsing must be defensive and null-safe.
- Visual fallback may introduce false positives — arbitration must protect good grounded text values.
- Existing tests assume latest-write tables — additive history must not break them.
- Some page images may be missing — fallback must skip and record bounded status.
- Confidential artifacts can leak through careless observations or traces — storage and diagnostics must remain bounded.

## Existing Codebase / Prior Art

- `src/db/schema.py` — owns SQLite schema and idempotent migrations.
- `src/extraction/repository.py` — persists current six-field extraction records and dashboard-ready compliance rows.
- `src/extraction/pipeline.py` — orchestrates extraction normalization, grounding, guards, risk computation, and persistence.
- `src/extraction/gemini.py` — lazy Gemini provider adapter and structured output prompt.
- `src/eval/repository.py` — eval run, eval metric, gold label, and bounded RAG observation repository patterns.
- `src/eval/operational_metrics.py` — aggregate token/cost metrics pattern.
- `src/dashboard/compliance.py` — Compliance tab rendering and current latest-write run-state warning.
- `src/dashboard/eval.py` — Eval tab run selection and comparison patterns.

## Relevant Requirements

- R011 — Preserve extraction and compliance results by run.
- R012 — Let the Compliance dashboard select and label extraction runs.
- R013 — Capture bounded Gemini extraction token and cost observations.
- R014 — Run targeted visual extraction fallback for suspicious or missing fields.
- R015 — Compare real extraction candidates against the human-approved 5-document baseline.
- R016 — Keep confidential SDF artifacts local and ignored during real evaluation work.
- R017 — Verify M004 with Windows-native commands only.

## Scope

### In Scope

- Additive run-scoped extraction and compliance history.
- Dashboard run selector and labels for extraction runs.
- Bounded Gemini usage and estimated-cost observations for extraction calls.
- Targeted visual fallback using stored page images from local `compliance.db`.
- Final real 5-document candidate comparison against existing real baseline and packet-aware candidates.
- Windows-native verification and ignored-artifact checks.

### Out of Scope / Non-Goals

- Full ColQwen/Qdrant visual retrieval.
- Full canonical rewrite of extraction persistence.
- Production multi-user run management.
- Expanding beyond the existing 5 local SDFs.
- Committing or exposing `compliance.db`, `.env`, `local_data/`, PDFs, images, snapshots, or provider payloads.

## Technical Constraints

- Use Python 3.11 project virtualenv.
- Never invoke `/bin/bash` or `gsd_exec` runtime `bash` for verification.
- Routine tests must use fake or mocked providers and not require Gemini credentials.
- Live Gemini calls may only happen in explicit real-run verification contexts.
- Observation and trace metadata must stay allowlisted and bounded.

## Integration Points

- SQLite schema and repositories — add run-scoped history and bounded usage observations.
- Extraction pipeline and Gemini provider — capture usage, visual fallback, and arbitration.
- Streamlit Compliance dashboard — select and label extraction runs.
- Eval repository and dashboard — compare final candidate against existing runs.
- Local ignored confidential artifacts — real SDF database, images, and snapshots.

## Testing Requirements

- Schema migration and repository tests for run-scoped history.
- Extraction pipeline tests proving compatibility latest-write rows plus history writes.
- Provider tests proving usage metadata parsing is null-safe and bounded.
- Visual fallback tests proving targeted invocation, image-missing behavior, and arbitration.
- Dashboard tests proving run selection, labels, and empty states.
- Eval tests proving candidate comparison and token/cost aggregates.
- Browser verification for Compliance and Eval tabs.
- Git ignored-artifact check for confidential local files.

## Acceptance Criteria

- S01: Multiple runs for the same document can be persisted and queried independently without breaking existing latest-write rows.
- S02: Compliance tab selects a run and labels it clearly, with safe fallback to latest state when no history exists.
- S03: Gemini usage metadata is extracted defensively and persisted as bounded observations with aggregate eval metrics.
- S04: Visual fallback fills or improves only eligible suspicious/missing fields using stored page images and records bounded failures.
- S05: A final real candidate eval run is persisted, compared to known baselines, browser-verified, and confidential artifacts remain ignored.

## Open Questions

- Exact visual prompt shape — should be refined during implementation after reading the existing Gemini provider contract.
- Exact Gemini price constants — should be stored as explicit estimated pricing metadata and adjusted if current pricing is verified during implementation.
