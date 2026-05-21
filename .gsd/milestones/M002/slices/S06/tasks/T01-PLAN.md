---
estimated_steps: 4
estimated_files: 1
skills_used: []
---

# T01: Align R006 requirement ownership outside M002

Expected executor skills: write-docs, verify-before-complete.

Why: The validation blocker is not failed retrieval code; it is the requirement register saying R006 visual ColQwen/Qdrant retrieval is active and primarily owned by M002 while D013 and the M002 roadmap explicitly defer visual retrieval. This task fixes the canonical requirement metadata first so later proof artifacts are not compensating for a contradictory source of truth.

Do: Use the GSD requirement update tool for R006 rather than manually editing `.gsd/REQUIREMENTS.md`. Prefer setting R006 status to `deferred` and changing/removing the M002 primary owner in favor of a future visual retrieval milestone/TBD owner. Preserve the requirement description and validation standard for future implementation. Update notes to state that M002 intentionally defers visual retrieval under D013, validates the text-RAG R005 loop only, and keeps retriever DTO/citation boundaries compatible with future visual retrieval. If the requirement tool rejects a `deferred` status or future/TBD owner, use the closest supported metadata shape and make the deferral unambiguous in notes.

Done when: R006 remains present as future work, but neither the R006 detail block nor the traceability table represents it as an active M002-owned deliverable; R005 and R007 ownership/validation text are not diluted.

## Inputs

- `.gsd/REQUIREMENTS.md`
- `.gsd/DECISIONS.md`
- `.gsd/milestones/M002/M002-CONTEXT.md`
- `.gsd/milestones/M002/M002-ROADMAP.md`
- `.gsd/milestones/M002/slices/S05/S05-SUMMARY.md`
- `.gsd/milestones/M002/slices/S06/S06-RESEARCH.md`

## Expected Output

- `.gsd/REQUIREMENTS.md`

## Verification

rg -n "R006|Status: deferred|Primary owning slice|D013|M002|future" .gsd/REQUIREMENTS.md

## Observability Impact

Improves review diagnostics by making requirement ownership and deferral visible in the canonical requirement register instead of scattered slice notes.
