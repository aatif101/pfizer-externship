---
phase: 02
slug: extraction-compliance
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-11
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pytest.ini`, `pyproject.toml` |
| **Quick run command** | `venv\Scripts\python.exe -m pytest tests\test_extraction_provider_gemini.py tests\test_extraction_gemini_usage.py tests\test_extraction_models.py -q` |
| **Full suite command** | `venv\Scripts\python.exe -m pytest tests\test_extraction_*.py -q` |
| **Estimated runtime** | ~25 seconds targeted; ~2 minutes full repository |

---

## Sampling Rate

- **After every task commit:** Run the task's focused test module(s).
- **After every plan wave:** Run `venv\Scripts\python.exe -m pytest tests\test_extraction_*.py -q`.
- **Before phase verification:** Run the full repository suite plus `venv\Scripts\python.exe -m pip check`.
- **Max feedback latency:** 30 seconds for focused tests.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | EXTRACT-01, D-02-01..04 | T-02-01-01, T-02-01-04 | Schema rejects unexpected/missing fields; provider payload remains unlogged | unit | `venv\Scripts\python.exe -m pytest tests\test_extraction_provider_gemini.py tests\test_extraction_gemini_visual.py -q` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | D-02-09..11 | T-02-01-02..05 | Pricing is model-keyed; secrets and raw responses never appear in errors | unit | `venv\Scripts\python.exe -m pytest tests\test_extraction_gemini_usage.py tests\test_extraction_usage_eval_metrics.py -q` | ✅ | ✅ green |
| 02-02-01 | 02 | 1 | EXTRACT-01, D-02-07 | T-02-02-01..07 | Run/document state is durable, idempotent, and manifest-bound | migration/integration | `venv\Scripts\python.exe -m pytest tests\test_extraction_run_history_schema.py tests\test_extraction_persistence.py -q` | ✅ | ✅ green |
| 02-02-02 | 02 | 1 | EXTRACT-01, D-02-07 | T-02-02-03 | Interrupted/partial/failed batches resume without false completion | CLI/integration | `venv\Scripts\python.exe -m pytest tests\test_extraction_cli.py -q` | ✅ | ✅ green |
| 02-03-01 | 03 | 2 | EXTRACT-01, EXTRACT-02, D-02-02..06 | T-02-03-01..03 | Only literal source-grounded fields influence compliance; uncertain scans route review | unit/integration | `venv\Scripts\python.exe -m pytest tests\test_extraction_pipeline.py tests\test_extraction_risk.py tests\test_visual_fallback_pipeline.py -q` | ✅ | ✅ green |
| 02-03-02 | 03 | 2 | EXTRACT-01, D-02-07..11 | T-02-03-04, T-02-03-07 | Usage provenance is bounded and incomplete extraction runs cannot produce metrics | integration | `venv\Scripts\python.exe -m pytest tests\test_extraction_usage_observations.py tests\test_extraction_usage_eval_metrics.py tests\test_extraction_eval_runner.py -q` | ✅ | ✅ green |
| 02-03-03 | 03 | 2 | EXTRACT-01, EXTRACT-02 | T-02-03-01..07 | Focused, dependency, and full offline Windows gates all pass | regression | `venv\Scripts\python.exe -m pytest tests -q --tb=short` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] Add strict-response-schema request/parsed-response tests to `tests/test_extraction_provider_gemini.py` and `tests/test_extraction_gemini_visual.py`.
- [x] Add model-price and thinking-token cases to `tests/test_extraction_gemini_usage.py`.
- [x] Add legacy migration plus per-document lifecycle tests to `tests/test_extraction_run_history_schema.py` and `tests/test_extraction_persistence.py`.
- [x] Add all-success, partial, failed, interrupted, resume, and manifest-mismatch CLI cases to `tests/test_extraction_cli.py`.
- [x] Add text-empty/image-backed conservative fallback coverage to `tests/test_extraction_pipeline.py` or `tests/test_visual_fallback_pipeline.py`.
- [x] Add completed-source-run refusal and bounded model/token/cost provenance coverage to `tests/test_extraction_eval_runner.py` and usage-observation modules.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live strict-schema compatibility on both Gemini profiles | D-02-09, D-02-11 | Provider endpoint behavior and quotas require credentials | Run one sanitized fixture through `gemini-2.5-flash` and `gemini-3.5-flash`; record model, token counters, cost, run status, and validate all six fields locally. |

---

## Validation Sign-Off

- [x] All planned behavior has an automated test seam or an explicit live-provider check.
- [x] Sampling continuity: no three consecutive tasks without automated verification.
- [x] Wave 0 lists every missing regression class.
- [x] No watch-mode flags.
- [x] Focused feedback latency target is under 30 seconds.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-07-11 (autonomous user delegation)
