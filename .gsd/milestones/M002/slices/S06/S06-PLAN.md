# S06: Resolve Requirement Coverage Scope Gap

**Goal:** Resolve the M002 requirement coverage scope gap by making R006 visual retrieval explicitly deferred outside M002, adding a reviewer-facing S06 scope proof, and producing milestone validation evidence that no longer treats R006 as a missing M002 deliverable.
**Demo:** After this, the M002 validation can point to a coherent requirement-scope artifact showing whether R006 is explicitly deferred outside M002 or implemented and verified, and Reviewer A can rerun without reporting a missing requirement.

## Must-Haves

- R006 no longer appears in the requirement register as an active M002-owned deliverable while remaining visible as future visual retrieval work.
- The S06 scope proof cites D013, the M002 roadmap/context boundary, and S05 final proof, and clearly states that M002 validates R005 text RAG but does not claim R006 visual retrieval validation.
- M002 validation can be rerun and produces `.gsd/milestones/M002/M002-VALIDATION.md` with R006 documented as deferred/outside M002 rather than missing.
- No production retrieval, RAG, Streamlit, tracing, or test code is changed unless validation unexpectedly reveals stale evidence.

## Proof Level

- This slice proves: Requirement traceability and validation-artifact proof. Real runtime is not required because S06 is a documentation/requirements-scope remediation slice; source-code regression is only required if production or test files are touched.

## Integration Closure

Consumes completed S01-S05 evidence, D013, M002 context/roadmap, and the requirement register. Introduces no runtime wiring. The milestone is ready for validation/completion when the requirement register, S06 proof artifact, and M002 validation artifact all agree that R006 is future/deferred while R005/R008/R010 remain supported by S05 evidence.

## Verification

- No runtime observability changes. Diagnostic/inspection surfaces are `.gsd/REQUIREMENTS.md`, `.gsd/milestones/M002/slices/S06/S06-SUMMARY.md`, optional S06 assessment notes, and `.gsd/milestones/M002/M002-VALIDATION.md`; these give future reviewers an auditable explanation for the requirement-scope decision.

## Tasks

- [x] **T01: Align R006 requirement ownership outside M002** `est:30m`
  Expected executor skills: write-docs, verify-before-complete.
  - Files: `.gsd/REQUIREMENTS.md`
  - Verify: rg -n "R006|Status: deferred|Primary owning slice|D013|M002|future" .gsd/REQUIREMENTS.md

- [x] **T02: Write S06 scope proof artifact** `est:45m`
  Expected executor skills: write-docs, verify-before-complete.
  - Files: `.gsd/milestones/M002/slices/S06/S06-SUMMARY.md`, `.gsd/milestones/M002/slices/S06/S06-ASSESSMENT.md`
  - Verify: rg -n "R006|D013|deferred|visual retrieval|ColQwen|Qdrant|S05|R005" .gsd/milestones/M002/slices/S06/S06-SUMMARY.md .gsd/milestones/M002/slices/S06/S06-ASSESSMENT.md

- [x] **T03: Generate milestone validation evidence** `est:30m`
  Expected executor skills: verify-before-complete.
  - Files: `.gsd/milestones/M002/M002-VALIDATION.md`
  - Verify: rg -n "R006|deferred|future|D013|R005|S05|pass" .gsd/milestones/M002/M002-VALIDATION.md

## Files Likely Touched

- .gsd/REQUIREMENTS.md
- .gsd/milestones/M002/slices/S06/S06-SUMMARY.md
- .gsd/milestones/M002/slices/S06/S06-ASSESSMENT.md
- .gsd/milestones/M002/M002-VALIDATION.md
