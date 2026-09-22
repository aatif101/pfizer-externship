# Phase 04: Dashboard & Evaluation Integrity — Context

Captured 2026-09-22 from the submission-planning request; technical planning is delegated. No implementation is claimed complete.

## Required reading

- `.planning/SUBMISSION-READINESS.md` — shared scope, this phase's detailed contract and evidence gates.
- `.planning/ROADMAP.md` and `.planning/REQUIREMENTS.md` — dependencies and traceability.
- Earlier phase SUMMARY/VERIFICATION/UAT artifacts and the current source, not only historical roadmap checkboxes.
- `.planning/phases/03-retrieval-rag-chatbot/03-CONTEXT.md` and `03-AI-SPEC.md` — locked architecture, frozen benchmark and release gates.

## Boundary and decisions

First tracer: two evaluations of the same index remain isolated and display their own metrics. Include >100 observations, live timing/usage boundaries, classification and per-field/per-type scores, annotation provenance, source previews and empty/error UAT. Fix integrity before reporting quality. Freeze additional classification/extraction acceptance targets before scoring; retain existing Phase 3 gates.

Preserve locked stack and existing working modules. Use the exact phase section in SUBMISSION-READINESS.md as acceptance criteria. Create small tracer-first plans with explicit dependencies, files, must-haves and verification. Research current compatibility at plan time. Do not broaden scope into production hosting or a UI rewrite. No `/bin/bash` verification.

## Completion

Exit only when this phase's observable criteria have evidence, required tests pass and human/runtime UAT is recorded where applicable. Missing API/GPU/human evidence is pending, not success. Update requirement states against evidence. Plan counts and implementation details are intentionally left to `/gsd-plan-phase 04`.
