# S05: Validation remediation boundary and end to end proof

**Goal:** Close M001 validation remediation by proving a realistic offline PDF ingestion to extraction to risk persistence to dashboard adapter chain, documenting producer and consumer boundaries, and clarifying which requirements are complete, partial, or future scope for this milestone.
**Demo:** After this: M001 has an explicit boundary map, a recorded realistic PDF ingestion to extraction to dashboard verification artifact, and clarified requirement coverage for out of scope future requirements.

## Must-Haves

- A deterministic S05 end-to-end pytest creates or uses a realistic one-page SDF PDF, ingests it through Docling, verifies non-empty grounded page text, runs the real extraction pipeline with a fake provider citing exact spans, persists six extraction rows plus one compliance row, and verifies dashboard-facing formatted values.
- The M001 boundary map no longer says `Not provided`; it documents S01-S04 producer/consumer contracts, known watch-outs, and the S05 validation seam.
- M001 validation or S05 closeout artifacts clarify requirement coverage: R001-R004/R009/R010 are M001-covered, R008 is M001-partial with broader tracing later, and R005-R007 are future M002/M003 scope rather than M001 failures.
- Targeted S05 proof and full regression pass using `venv/Scripts/python.exe` without live Gemini/Langfuse credentials or committed local tokens.

## Proof Level

- This slice proves: Final-assembly proof for M001 baseline: real runtime ingestion, SQLite persistence, extraction orchestration, compliance risk computation, and dashboard adapter formatting are exercised in one offline test. Human UAT is not required; live Gemini is intentionally optional/out of scope for this remediation proof.

## Integration Closure

Consumes the completed S01 Python 3.11/secret hygiene baseline, S02 schema/repository contract, S03 extraction persistence pipeline, and S04 SQLite-backed dashboard adapter. Introduces no new runtime entrypoint; closure is the validation boundary map plus one executable chain spanning the existing entrypoints. After this slice, M001 should be ready for milestone validation/completion except for any fresh regression failures discovered during verification.

## Verification

- S05 does not expand Langfuse tracing implementation. It verifies and documents current observability surfaces: sanitized run_id/trace_id metadata persisted in compliance rows, non-fatal startup without Langfuse/Gemini credentials, safe provider abstraction for offline proof, and gsd_exec/pytest artifacts suitable for future validator inspection without secrets or raw provider payloads.

## Tasks

- [x] **T01: Add realistic offline end to end proof test** `est:2h`
  ---
  estimated_steps: 8
  estimated_files: 1
  skills_used:
    - tdd
    - verify-before-complete
  ---
  - Files: `tests/test_s05_end_to_end_proof.py`
  - Verify: venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py -q

- [x] **T02: Document M001 boundary map and requirement scope** `est:1h`
  ---
  estimated_steps: 7
  estimated_files: 2
  skills_used:
    - write-docs
    - observability
  ---
  - Files: `.gsd/milestones/M001/M001-ROADMAP.md`, `.gsd/milestones/M001/M001-VALIDATION.md`, `.gsd/REQUIREMENTS.md`
  - Verify: Manual review — boundary map and requirement-scope sections exist and are non-empty; do not run tests against .gsd paths.

- [x] **T03: Run closeout verification and package evidence** `est:1h`
  ---
  estimated_steps: 6
  estimated_files: 0
  skills_used:
    - verify-before-complete
  ---
  - Verify: venv/Scripts/python.exe -m pytest -q

## Files Likely Touched

- tests/test_s05_end_to_end_proof.py
- .gsd/milestones/M001/M001-ROADMAP.md
- .gsd/milestones/M001/M001-VALIDATION.md
- .gsd/REQUIREMENTS.md
