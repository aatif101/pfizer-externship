---
estimated_steps: 19
estimated_files: 3
skills_used: []
---

# T02: Document M001 boundary map and requirement scope

---
estimated_steps: 7
estimated_files: 2
skills_used:
  - write-docs
  - observability
---

Why: M001 validation is blocked by documentation gaps, not just code. The roadmap boundary map currently says `Not provided`, and the validator needs explicit distinction between M001 deliverables and future M002/M003 requirements.

Do:
1. Replace the empty `## Boundary Map` body in `.gsd/milestones/M001/M001-ROADMAP.md` with a concise producer/consumer contract map for S01 through S05.
2. Cover these contracts: S01 provides Python 3.11 venv and secret hygiene to all later slices; S02 provides strict six-field extraction schema/repository shape to S03/S04; S03 provides persisted extraction/compliance rows and source evidence to S04; S04 provides credential-free SQLite dashboard display and friendly empty states to validation; S05 provides final proof and scope clarification.
3. Include watch-outs from research: `tests/fixtures/sample.pdf` is not proof-suitable because it has empty page text; live Gemini is optional/manual; use `venv/Scripts/python.exe`; do not expose raw provider responses or secrets.
4. Update `.gsd/milestones/M001/M001-VALIDATION.md` or an adjacent S05 remediation section if appropriate to explain requirement scope: R001-R004 are validated/covered in M001, R009/R010 are M001 constraints to preserve, R008 is covered only for non-fatal credential behavior and sanitized metadata in M001 with broader tracing later, and R005-R007 remain active future M002/M003 work.
5. Do not globally mark R005/R006/R007 complete or failed. Use requirement update tools only if a durable note is needed, preserving their future active status.
6. Keep prose validator-readable: no implementation internals unless they clarify a boundary or proof path.

Threat Surface: Documentation references provider credentials and trace metadata; do not include secrets, token-like values, local machine-specific paths outside the repo, or raw model/page dumps. The docs should describe redaction boundaries rather than reveal sensitive state.

Requirement Impact: Touches R001-R010 traceability language. Re-verify that R005-R007 remain future/out-of-scope rather than invalidated, and that R008 is not overclaimed beyond current non-fatal/sanitized behavior.

Failure Modes: If the roadmap is DB-rendered later, manual edits may be overwritten. If that happens, preserve the boundary text in the S05 summary/validation artifact and use the appropriate GSD roadmap/validation tool during closeout if available.

Done when: A fresh validator can read M001 artifacts and understand which slice owns each integration boundary and why future RAG/visual/eval requirements are not M001 blockers.

## Inputs

- `.gsd/milestones/M001/M001-ROADMAP.md`
- `.gsd/milestones/M001/M001-VALIDATION.md`
- `.gsd/REQUIREMENTS.md`
- `.gsd/milestones/M001/slices/S05/S05-RESEARCH.md`
- `.gsd/milestones/M001/slices/S04/S04-SUMMARY.md`
- `tests/test_s05_end_to_end_proof.py`
- `src/app.py`
- `src/tracing.py`
- `src/extraction/cli.py`
- `src/extraction/gemini.py`

## Expected Output

- `.gsd/milestones/M001/M001-ROADMAP.md`
- `.gsd/milestones/M001/M001-VALIDATION.md`

## Verification

Manual review — boundary map and requirement-scope sections exist and are non-empty; do not run tests against .gsd paths.

## Observability Impact

Clarifies current diagnostic boundaries for future agents: offline proof artifacts, run_id/trace_id metadata, missing-credential non-fatal behavior, and redaction constraints.
