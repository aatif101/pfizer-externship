---
estimated_steps: 7
estimated_files: 4
skills_used: []
---

# T03: Expose extraction usage aggregate eval metrics

Expected executor skills: tdd, verify-before-complete.

Why: S03 is complete only when usage observations are inspectable as aggregate eval metrics, not merely stored as raw rows. Downstream S05 comparisons need run-level token and cost metrics that can be rendered through the existing Eval/dashboard metric surface.

Do: Add provider-free aggregation helpers for extraction usage observations, reusing the deterministic absent-safe numeric behavior established by `src/eval/operational_metrics.py`. Introduce a small eval runner/helper, for example `src/eval/extraction_usage_eval.py`, that creates or updates an eval run for a selected extraction source run and persists global `eval_metrics` such as `extraction.latency_ms.avg`, `extraction.latency_ms.p50`, `extraction.latency_ms.p95`, `extraction.cost_usd.total`, `extraction.cost_usd.avg`, `extraction.tokens.input`, `extraction.tokens.output`, and `extraction.tokens.total`. Scope optional per-document metrics only if the implementation can keep names deterministic and tests simple. The helper must import no provider SDKs, no RAGAS, and no Streamlit, and must degrade gracefully by completing with no metrics when no usage observations exist.

Failure Modes (Q5): Missing observation table in older DBs may either be handled as an empty observation set or be covered by `init_db()` migration tests; malformed non-null numerics should raise visibly and mark the eval run error with a sanitized reason if the runner owns eval run lifecycle. Eval metric upsert failures should not be swallowed.

Load Profile (Q6): Shared resources are SQLite reads from observation rows and writes to `eval_metrics`. At 10x run size, aggregation is O(number of observations) and should remain bounded by run_id filtering plus repository limit/explicit max; avoid loading unrelated runs.

Negative Tests (Q7): empty observations emit no metrics, null fields emit no zero metrics, unrelated run observations are ignored, unsorted latencies produce deterministic p50/p95, and malformed values fail visibly without raw content in `eval_runs.error_reason`.

Done when: tests prove aggregate metrics are persisted for a selected extraction run from bounded observations, absent data emits no misleading metrics, and the helper remains provider-free/offline-safe.

## Inputs

- `src/eval/operational_metrics.py`
- `src/eval/repository.py`
- `tests/test_retrieval_eval_optional_metrics.py`
- `tests/test_eval_repository.py`

## Expected Output

- `src/eval/operational_metrics.py`
- `src/eval/extraction_usage_eval.py`
- `src/eval/repository.py`
- `tests/test_extraction_usage_eval_metrics.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_usage_eval_metrics.py tests/test_retrieval_eval_optional_metrics.py tests/test_eval_repository.py

## Observability Impact

Publishes run-level cost/token/latency summaries through `eval_metrics`, the existing dashboard-readable operational metric surface.
