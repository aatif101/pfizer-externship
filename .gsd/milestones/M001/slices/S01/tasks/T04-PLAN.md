---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T04: Normalize GSD artifacts

Seed current GSD artifacts from the old .planning state: project summary, requirements register, roadmap, slice plan, and decisions.

## Inputs

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`

## Expected Output

- `.gsd/PROJECT.md`
- `.gsd/REQUIREMENTS.md`
- `.gsd/ROADMAP.md`
- `.gsd/DECISIONS.md`
- `.gsd/milestones/M001/slices/S01/S01-PLAN.md`

## Verification

test -f .gsd/PROJECT.md && test -f .gsd/REQUIREMENTS.md && test -f .gsd/ROADMAP.md && test -f .gsd/DECISIONS.md

## Observability Impact

Makes the current GSD state parseable by current workflow tooling.
