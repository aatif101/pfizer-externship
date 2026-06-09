---
verdict: pass
remediation_round: 0
---

# Milestone Validation: M004

## Success Criteria Checklist
- [x] **Extraction and compliance runs are preserved by run id without breaking latest-write compatibility.**
  Evidence: S01 — `extraction_history` additive schema; `test_run_scoped_history_preserves_two_runs_while_latest_shows_newest` PASSED; 8+31+29 tests passed.

- [x] **Compliance dashboard can select and label extraction runs clearly.**
  Evidence: S02 — `Extraction run view` selector implemented in `src/dashboard/compliance.py`; 54 tests passed.

- [x] **Gemini extraction usage and estimated cost are captured as bounded metrics.**
  Evidence: S03 — `extraction_usage_observations` SQLite table; bounded cost estimation; aggregate eval metrics; all closeout pytest gates passed.

- [x] **Targeted visual fallback improves or honestly measures suspicious-field extraction without overwriting good grounded text values.**
  Evidence: S04 — `SDFVisualFallbackProvider` protocol; conservative merge arbitration; `--visual-fallback` CLI flag; 58 tests passed.

- [x] **A final real 5-document comparison is produced against existing baselines and candidates.**
  Evidence: S05 — `vf-candidate-20260607` (macro F1=0.100) and `text-baseline-20260607` (macro F1=0.178) persisted; Eval tab delta comparison verified by human UAT screenshots (2026-06-09).

- [x] **Confidential artifacts remain local and ignored.**
  Evidence: S05 — `git status --short` showed zero confidential tracked files.

- [x] **All verification uses Windows-native commands only.**
  Evidence: All five slices used `gsd_exec runtime=node` spawning `venv\Scripts\python.exe`; no `/bin/bash` used.

## Slice Delivery Audit
| Slice | SUMMARY.md | Assessment Verdict | Known Limitations |
|-------|------------|-------------------|-------------------|
| S01: Run scoped extraction history | Present | PASS | Creates run-history substrate only; no dashboard/usage/fallback (by design) |
| S02: Compliance dashboard run selector | Present | PASS | Real browser verification deferred to S05 (by design) |
| S03: Gemini extraction usage observations | Present | PASS | No live Gemini billing validation; visual fallback observations deferred to S04 |
| S04: Targeted visual fallback extraction | Present | PASS | None |
| S05: Real five document comparison and UAT | Present | PASS | 2/5 docs have pre-existing provider failures; human UAT screenshots taken 2026-06-09 closed Operational evidence gap |

All five slices have SUMMARY.md files and PASS assessments.

## Cross-Slice Integration
All five cross-slice boundary contracts verified end-to-end:
- S01→S02: run-scoped history and run summaries — PASS
- S01→S03: extraction run identity for usage observations — PASS
- S03→S04: bounded usage observation contract — PASS
- S01+S03→S04: run history + usage observations for visual fallback — PASS
- S02+S04→S05: dashboard run selection + visual fallback — PASS (human UAT screenshots confirmed Compliance tab selector surfaced vf-candidate-20260607)

## Requirement Coverage
All seven M004-scoped requirements are COVERED:
- R011: Run-scoped extraction history — COVERED (S01)
- R012: Compliance dashboard run selector — COVERED (S02)
- R013: Bounded Gemini extraction token/cost observations — COVERED (S03)
- R014: Targeted visual fallback — COVERED (S04)
- R015: Real 5-doc comparison against gold baseline — COVERED (S05, human UAT confirmed)
- R016: Confidential PDFs/DBs/images kept local and gitignored — COVERED (S05)
- R017: Windows-native verification only — COVERED (all slices)

## Verification Class Compliance
| Class | Check | Evidence | Verdict |
|-------|-------|----------|---------|
| Contract | Schema migration tests (additive, idempotent, FK-enforced) | S01: 8 tests; S03: usage observation table tests. All passed. | PASS |
| Contract | Repository and provider tests | S01: 31 tests; S03: usage parsing; S04: fake-part factory, eligibility, arbitration. All passed. | PASS |
| Contract | Dashboard tests (run selector, labels, empty states) | S02: 54 tests covering all label states. All passed. | PASS |
| Contract | Eval runner tests (macro+field metrics, idempotency) | S05: 6 tests. All passed. | PASS |
| Integration | SQLite migrations on real compliance.db | S05-T02: vf-candidate-20260607 written; no prior run data corrupted. | PASS |
| Integration | Extraction run history writes (idempotent, latest-write compat preserved) | S01 closeout: two scoped runs preserved simultaneously. | PASS |
| Integration | Dashboard run selection on real compliance.db data | S05-T03 + human UAT: Compliance tab surfaced vf-candidate-20260607. | PASS |
| Integration | Final eval comparison (vf-candidate vs baseline in Eval tab) | Human UAT screenshots (2026-06-09): extraction.macro.f1/precision/recall delta rows confirmed. | PASS |
| Operational | Streamlit dashboard in browser, no console errors | Human UAT screenshots (2026-06-09): Compliance tab run selector and Eval tab metric deltas visually confirmed. | PASS |
| Operational | No confidential data committed | S05-T04: git status --short confirmed zero confidential tracked files. | PASS |
| Operational | Windows-native verification only | All slices: gsd_exec runtime=node, venv\Scripts\python.exe throughout. | PASS |
| UAT | Visual-fallback candidate run from real compliance.db | S05-T02: vf-candidate-20260607 via --visual-fallback; 3/5 docs succeeded. | PASS |
| UAT | Candidate run compared against baseline in Eval tab | Human UAT screenshots (2026-06-09): extraction.macro.f1 delta -7.8%, precision -6.7%, recall -8.0% confirmed. | PASS |


## Verdict Rationale
All five slices PASS, all seven requirements (R011–R017) covered, all five cross-slice boundaries verified, 303 tests green. Human UAT screenshots taken 2026-06-09 closed the final Operational evidence gap: Compliance tab "Extraction run view" dropdown and Eval tab metric comparison table (extraction.macro.f1/precision/recall delta rows) were visually confirmed in a live Streamlit session. All verification classes (Contract, Integration, Operational, UAT) are PASS. Milestone is complete.
