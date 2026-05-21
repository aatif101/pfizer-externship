---
estimated_steps: 4
estimated_files: 1
skills_used: []
---

# T03: Generate milestone validation evidence

Expected executor skills: verify-before-complete.

Why: The original failure mode was that M002 could not be validated cleanly because `.gsd/milestones/M002/M002-VALIDATION.md` was absent and R006 looked unfulfilled. This task turns the requirement update and S06 proof into the actual validation artifact the milestone closeout needs.

Do: First run a traceability check over `.gsd/REQUIREMENTS.md` and S06 artifacts to confirm R006 is deferred/future and not active M002-owned. Then run the M002 validation tool with a pass verdict if the requirement register and S06 proof are coherent: R005 is validated by S05's 66-test offline proof, R008/R010 remain supported by S05 tracing/redaction evidence, R007 is future M003 evaluation work, and R006 is deferred outside M002 under D013. If the validation tool refuses because S06 is not yet marked complete, record that as a process ordering blocker in the task summary, complete the slice via the normal GSD flow, and rerun validation immediately afterward before milestone completion. Do not touch production code or rerun the full 66-test suite unless a source/test file changed; if any source/test file did change, rerun the S05 regression command from the project virtual environment.

Done when: `.gsd/milestones/M002/M002-VALIDATION.md` exists and explicitly treats R006 as deferred/future scope rather than a missing M002 requirement; the validation rationale points to S06 and S05 evidence.

## Inputs

- `.gsd/REQUIREMENTS.md`
- `.gsd/DECISIONS.md`
- `.gsd/milestones/M002/M002-ROADMAP.md`
- `.gsd/milestones/M002/slices/S05/S05-SUMMARY.md`
- `.gsd/milestones/M002/slices/S06/S06-SUMMARY.md`
- `.gsd/milestones/M002/slices/S06/S06-ASSESSMENT.md`

## Expected Output

- `.gsd/milestones/M002/M002-VALIDATION.md`

## Verification

rg -n "R006|deferred|future|D013|R005|S05|pass" .gsd/milestones/M002/M002-VALIDATION.md

## Observability Impact

Adds the milestone-level validation artifact that future agents and reviewers inspect to understand pass/fail rationale and remaining future scope.
