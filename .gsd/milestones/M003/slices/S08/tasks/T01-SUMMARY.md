---
id: T01
parent: S08
milestone: M003
key_files:
  - scripts/seed_s08_uat_eval_db.py
  - tests/test_s08_uat_seed.py
key_decisions:
  - Seeded only synthetic run IDs, pipeline labels, params, metric names, and numeric metric values through existing schema/repository helpers rather than direct SQL writes.
duration: 
verification_result: passed
completed_at: 2026-05-27T21:31:53.433Z
blocker_discovered: false
---

# T01: Added a deterministic S08 synthetic Eval-tab SQLite seed helper with tests proving idempotent complete runs and sanitized metric-only data.

**Added a deterministic S08 synthetic Eval-tab SQLite seed helper with tests proving idempotent complete runs and sanitized metric-only data.**

## What Happened

Created `scripts/seed_s08_uat_eval_db.py`, a Windows-safe CLI/helper that accepts a SQLite DB path, initializes the canonical schema through `src.db.schema.init_db`, and uses `src.eval.repository` helpers to create two complete synthetic RAG/retrieval UAT runs. The helper upserts the required global metrics for retrieval recall, citation accuracy, RAG faithfulness/relevancy, latency, cost, and token totals without reading documents, calling providers, or persisting prompts, answers, snippets, payloads, file paths, source text, hashes, images, or secrets. Added `tests/test_s08_uat_seed.py`, which runs the helper twice against `tmp_path`, verifies exactly two complete synthetic runs, verifies the expected metric families for each run, verifies comparison-ready value deltas, confirms repeated execution does not duplicate metrics, and checks seeded eval text/columns for raw-content terms. During verification I refined the test thresholds and raw-content term guard so they match required metric naming such as `rag.answer_relevancy.avg` while still protecting against raw prompt/answer/payload fields.

## Verification

Ran the required Windows-safe pytest command via `gsd_exec` using Node to spawn `venv\Scripts\python.exe -m pytest -q tests/test_s08_uat_seed.py tests/test_dashboard_eval_tab.py`. Final run passed all 11 tests, covering the new seed helper and existing Eval dashboard tab behavior.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv\Scripts\python.exe -m pytest -q tests/test_s08_uat_seed.py tests/test_dashboard_eval_tab.py` | 0 | ✅ pass | 11674ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `scripts/seed_s08_uat_eval_db.py`
- `tests/test_s08_uat_seed.py`
