# S06: S06 — UAT

**Milestone:** M002
**Written:** 2026-05-21T00:41:26.811Z

## UAT Type
Documentation and validation-artifact UAT for requirement-scope traceability.

## Preconditions
- M002 S01-S05 are complete and S05 final proof exists for text retrieval, grounded answers, citations, abstention, Chat rendering, and operational failure paths.
- `.gsd/REQUIREMENTS.md`, `.gsd/milestones/M002/slices/S06/S06-ASSESSMENT.md`, and `.gsd/milestones/M002/M002-VALIDATION.md` are available.
- Reviewer uses the project-supported Python command `./venv/Scripts/python.exe` on Windows per R009 if running tests.

## Steps
1. Open `.gsd/REQUIREMENTS.md` and find R006.
2. Confirm R006 is visible as deferred/future visual retrieval work and is not listed as an active M002-owned deliverable.
3. Open `.gsd/milestones/M002/slices/S06/S06-ASSESSMENT.md` and confirm it cites D013, S05 final proof, R005, and the M002 boundary.
4. Confirm the S06 proof states that M002 validates text RAG and abstention under R005, while ColQwen/Qdrant visual retrieval remains future R006 work.
5. Open `.gsd/milestones/M002/M002-VALIDATION.md` and confirm validation records R006 as deferred/outside M002 rather than missing.
6. Optionally run `./venv/Scripts/python.exe -m pytest` to confirm runtime regressions are absent.

## Expected Outcomes
- R006 is not treated as an unvalidated M002 deliverable.
- M002 validation can pass with R005 text RAG evidence from S05 while explicitly preserving R006 as future visual retrieval scope.
- Reviewer A can rerun validation without reporting a missing R006 requirement.
- Optional regression passes with 148 tests under the Python 3.11 venv.

## Edge Cases
- If a reviewer searches only active requirements, R006 should not appear as active M002 scope.
- If a reviewer searches all requirements, R006 should still be discoverable and clearly deferred rather than deleted.
- If the global `python3` command fails on Windows, use `./venv/Scripts/python.exe` per R009; that command is the supported verification surface.

## Not Proven By This UAT
- ColQwen visual retrieval, Qdrant multivector indexing, and page-image retrieval quality are not implemented or validated by M002.
- Live Gemini generation quality is not revalidated by S06 beyond the already completed M002 service/provider seams and offline proofs.
- New production retrieval, RAG, Streamlit, tracing, or evaluation code is not introduced by this slice.
