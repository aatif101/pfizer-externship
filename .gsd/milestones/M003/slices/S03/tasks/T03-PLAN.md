---
estimated_steps: 10
estimated_files: 2
skills_used: []
---

# T03: Optional hooks for latency/cost and RAGAS metric placeholders that degrade gracefully (no secrets, no crashes)

Why: R007 requires latency/cost and faithfulness/relevancy metrics, but they must be optional and must not require live providers in deterministic test runs.

Do:
- In `src/eval/retrieval_eval_runner.py`, add optional parameters/flags (default off) for:
  - `include_latency_cost` which attempts to read latency/cost metadata from existing run/trace tables/columns if present. If missing, skip.
  - `include_ragas` which attempts to import RAGAS and compute metrics only if installed and if gold answers / contexts are available; otherwise skip without raising.
- Implement the skip logic explicitly with narrow exception handling (ImportError, sqlite3.OperationalError for missing tables/columns) and unit tests asserting that enabling flags on a DB without those prerequisites does not crash and still produces the core retrieval metrics.
- Preserve R010 redaction: do not log or persist raw contexts or tokens; only persist numeric aggregates.

Done-when:
- Runner can be invoked with flags enabled against a minimal DB and still completes, with core metrics present.
- Tests cover both: flags off (baseline), flags on (skips gracefully) using a temp DB.

## Inputs

- `src/eval/retrieval_eval_runner.py`

## Expected Output

- `tests/test_retrieval_eval_optional_metrics.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_retrieval_eval_optional_metrics.py -q

## Observability Impact

Improves operability by making optional metric pathways explicitly non-fatal and test-covered, preventing dashboard crashes when optional deps aren’t configured.
