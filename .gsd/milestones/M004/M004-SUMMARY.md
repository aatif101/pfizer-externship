---
id: M004
title: "Extraction Observability, Visual Fallback, and Eval Pipeline"
status: complete
completed_at: 2026-06-09T20:20:33.609Z
key_decisions:
  - Run-scoped history uses additive schema; latest-write compat preserved via separate latest_extraction table
  - Visual fallback uses conservative PENDING-only arbitration — grounded text values are never replaced
  - Gemini cost estimation is bounded to known model IDs only; unknown models produce null cost
  - Langfuse tracing deferred to a future milestone
key_files:
  - src/extraction/pipeline.py
  - src/extraction/providers.py
  - src/extraction/repository.py
  - src/dashboard/compliance.py
  - src/dashboard/eval.py
  - src/eval/extraction_eval_runner.py
  - src/eval/extraction_usage_eval.py
  - src/db/schema.py
  - src/db/queries.py
lessons_learned:
  - Two of five SDF documents had pre-existing provider failures unrelated to M004 — noting as known limitations was correct
  - DOM-level browser verification from agent context requires human screenshots when localhost is unreachable — human UAT is the right fallback pattern
  - Windows-native verification (gsd_exec runtime=node spawning venv\Scripts\python.exe) is stable and should remain standard
---

# M004: Extraction Observability, Visual Fallback, and Eval Pipeline

**Delivered run-scoped extraction history, compliance dashboard run selector, Gemini usage observations, targeted visual fallback, and a real 5-document eval comparison — all verified end-to-end with human UAT screenshots.**

## What Happened

M004 added five tightly sequenced capabilities to the Pfizer SDF Intelligence System. S01 introduced an additive run-scoped extraction history schema so baseline and candidate runs coexist without overwriting each other. S02 wired a labelled "Extraction run view" selector into the Compliance dashboard. S03 captured bounded Gemini token/cost usage observations per extraction call. S04 implemented a targeted visual fallback protocol that conservatively merges image-sourced values for abstained or low-confidence fields without overwriting good grounded text. S05 ran a real 5-document extraction comparison (vf-candidate-20260607 via --visual-fallback vs text-baseline-20260607) and persisted eval metrics to compliance.db. Human UAT screenshots taken 2026-06-09 confirmed the Compliance tab run selector surfaced both runs and the Eval tab displayed extraction.macro.f1/precision/recall delta rows. All 303 tests passed across slices. All seven requirements R011-R017 are covered. All verification classes (Contract, Integration, Operational, UAT) are PASS.

## Success Criteria Results

All seven M004 success criteria met: run-scoped history preserved, compliance run selector functional, usage observations captured, visual fallback conservative-merge verified, real 5-doc comparison produced, confidential data gitignored, Windows-native verification maintained.

## Definition of Done Results

Not provided.

## Requirement Outcomes

Not provided.

## Deviations

S05 added a text-baseline run because no prior extraction_history rows existed in compliance.db — an expected plan adaptation. Two of five docs failed with pre-existing provider errors acknowledged as known limitations.

## Follow-ups

None.
