# S06 Research: Resolve Requirement Coverage Scope Gap

## Summary

S06 is a documentation/requirements-scope remediation slice, not a retrieval implementation slice. M002 text RAG is already complete and verified by S05, but milestone validation failed because `.gsd/REQUIREMENTS.md` still maps active requirement R006 (visual ColQwen/Qdrant retrieval) to primary owner `M002`, while every M002 planning decision says visual retrieval is deferred. The coherent fix is to align the requirement register and validation artifacts with the existing M002 scope decision: M002 validates R005 text RAG; R006 remains unvalidated and explicitly deferred to a future visual retrieval milestone or later roadmap reassessment.

## Active Requirements This Slice Owns/Supports

- **R006** — currently `active` with `Primary owning slice: M002`; validation requires visual retrieval improving/complementing recall on scanned/table-heavy gold-set pages. This is the blocking mismatch.
- **R005** — already validated by M002 S05; S06 must not reopen or dilute it.
- **R007** — primary owner M003; relevant because R006 validation depends on gold-set recall metrics, which are not yet present and belong near evaluation work.
- **R008/R010** — already supported by S05 tracing/redaction proof; no new implementation needed.

## Recommendation

Prefer **defer R006 outside M002** rather than implement visual retrieval in S06. Implementing ColQwen/Qdrant now would violate D013, add GPU/Qdrant/model complexity, and require a gold-set recall proof that M003 has not built yet. S06 should produce an explicit scope-coverage artifact and update requirement metadata so the M002 validation gate no longer treats R006 as an unfulfilled M002 deliverable.

Concrete expected executor outcome:

1. Update R006 in `.gsd/REQUIREMENTS.md` through the GSD requirement update mechanism, not by manual editing, so generated requirement sections/traceability remain consistent.
2. Set R006 to a deferred/future-owner state, or at minimum remove `M002` as the primary owner and state that M002 only prepares compatible text-RAG interfaces.
3. Add a durable S06 summary/assessment that cites D013 and M002/S05 evidence and states why implementation is intentionally out of scope.
4. Rerun milestone validation so `.gsd/milestones/M002/M002-VALIDATION.md` exists and references the resolved R006 scope.

## Implementation Landscape

### Existing artifacts proving deferment

- `.gsd/DECISIONS.md` — D013: “M002 will deliver CPU-friendly text RAG only and defer visual retrieval implementation.” Choice explicitly treats ColQwen/Qdrant as out of scope for M002 while preserving retriever DTO compatibility.
- `.gsd/milestones/M002/M002-CONTEXT.md` — architecture section says text RAG baseline comes before visual retrieval; relevant requirements section says R006 is prepared for but not fully validated by M002.
- `.gsd/milestones/M002/M002-ROADMAP.md` — Boundary Map states: “R005 drives the user loop; R006 visual retrieval is deferred; R007 is limited to retrieval and citation proof.”
- `.gsd/milestones/M002/slices/S05/S05-SUMMARY.md` — final proof explicitly excludes visual ColQwen/Qdrant retrieval and recommends future milestones cover R006.
- `.gsd/milestones/M002/slices/S05/S05-ASSESSMENT.md` — records validation round 0 remediation: R006 visual retrieval is missing from M002 coverage while planning artifacts defer it.

### Current mismatch

- `.gsd/REQUIREMENTS.md` currently lists R006 under **Active** with `Primary owning slice: M002` and traceability row `| R006 | differentiator | active | M002 | none | ... |`.
- That mapping makes the milestone validator correctly expect M002 to implement/validate visual retrieval, despite D013 and the roadmap saying it is deferred.
- M003 exists only as `.gsd/milestones/M003/M003-ROADMAP.md` with “Vision: Not yet planned.” It owns R007 evaluation, but no visual retrieval milestone exists yet.

### Codebase constraints

No production source code appears necessary for S06. The completed M002 runtime proof already covers:

- CLI indexing and metadata: `src/retrieval/indexer.py`, retrieval CLI tests.
- Hybrid text retrieval/evidence gate: `src/retrieval/retriever.py`, `tests/test_retriever.py`.
- RAG service/provider seam: `src/rag/service.py`, `tests/test_answer_service.py`, `tests/test_answer_provider_gemini.py`.
- Chat rendering: `src/dashboard/chat.py`, `tests/test_chat_dashboard.py`, `tests/test_app.py`.
- Final offline proof: `tests/test_s05_end_to_end_proof.py`.

S06 should avoid touching these unless the validation gate unexpectedly requires additional evidence references.

## Natural Seams / Suggested Tasks

1. **Requirement register alignment**
   - Target: `.gsd/REQUIREMENTS.md` via `gsd_requirement_update` if available to the executor.
   - Change: R006 should no longer be an active M002-owned requirement. Suggested wording: status `deferred`; primary owner `future visual retrieval milestone`/`TBD`; notes mention D013 and M002 S06 scope resolution.
   - Rationale: This is the root validation blocker.

2. **Scope proof artifact**
   - Target: S06 summary/assessment artifact under `.gsd/milestones/M002/slices/S06/` through GSD summary tooling.
   - Content: cite D013, M002 context/roadmap boundary map, S05 final proof, and explicit R006 validation criteria. State that M002 implemented R005 text RAG and intentionally did not claim R006 validation.
   - Rationale: Reviewer A needs a single artifact to point at during milestone validation.

3. **Milestone validation rerun**
   - Target: use `gsd_validate_milestone` after S06 completion, producing `.gsd/milestones/M002/M002-VALIDATION.md`.
   - Expected verdict: pass for M002 if R005/R008/R010 evidence remains accepted and R006 is not treated as M002-owned; otherwise needs-remediation with only future-scope notes.
   - Rationale: The triggering failure was missing `M002-VALIDATION.md` after unit execution.

## First Proof / Highest-Risk Unblocker

The first proof should be a requirement traceability check, not a pytest run:

- After updating R006, inspect `.gsd/REQUIREMENTS.md` and confirm the R006 traceability row no longer says `active | M002 | none`.
- Confirm the R006 notes mention that M002 deferred visual retrieval under D013 and that R006 remains future work rather than validated.
- Confirm M002 validation can be generated and includes R006 as deferred/outside M002, not missing.

If this still fails, the fallback is to add a new explicit decision superseding/clarifying D013 and then rerun requirement update/validation.

## Verification

Recommended verification sequence for executors:

1. Documentation/traceability grep:
   - `rg -n "R006|visual retrieval|ColQwen|Qdrant|M002-VALIDATION" .gsd/REQUIREMENTS.md .gsd/DECISIONS.md .gsd/milestones/M002`
2. Optional no-code regression sanity check from supported runtime if any source/test files are touched:
   - `venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py tests/test_retrieval_cli.py tests/test_retriever.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_chat_dashboard.py tests/test_app.py tests/test_tracing.py`
   - Expected prior baseline: 66 passed in S05.
3. GSD validation artifact check:
   - `.gsd/milestones/M002/M002-VALIDATION.md` exists after `gsd_validate_milestone`.
   - Validation rationale explicitly says R006 is deferred/future and not a failed M002 requirement.

## Skill Discovery

Installed relevant skills from the available list:

- **write-docs** — useful because S06 is primarily a reader-facing scope/requirement artifact problem.
- **decompose-into-slices** — conceptually relevant if the planner decides to create a future visual retrieval milestone/slice, but not needed to close S06.
- **observability** — not needed for this doc-only remediation; S05 already covered R008 trace metadata.

No external professional skill search is necessary for core implementation because this slice does not depend on new libraries or services. It depends on GSD requirement/validation artifacts and existing project decisions.

## Open Questions / Planner Decisions

- Should R006 become `deferred`, or stay `active` but move primary owner to a not-yet-planned future milestone? The cleanest validation semantics appear to be `deferred` until a visual retrieval milestone is planned.
- Should M003 own R006? Current M003 is “Dashboard Evaluation and Polish” and owns R007, but visual ColQwen/Qdrant retrieval may be large enough to need its own future milestone rather than being hidden inside M003.
- If GSD requirement tooling rejects a future/TBD primary owner, prefer status `deferred` with notes explaining future roadmap reassessment.

## Research Evidence

- Memory MEM025 confirms the prior architecture decision: M002 delivers CPU-friendly text RAG and defers visual retrieval while keeping DTOs compatible with later visual retrievers.
- Search run `.gsd/exec/b9d0fa1d-0e99-4028-b8ef-844c83a1e48a.stdout` found all R006/visual references in M002 and requirements artifacts.
- Search run `.gsd/exec/08697659-8c8b-47a3-a96f-b73f043945bb.stdout` confirmed D013, M002 roadmap deferment, and the current R006 traceability mismatch.
