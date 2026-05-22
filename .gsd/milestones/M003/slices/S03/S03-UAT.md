# S03: S03 — UAT

**Milestone:** M003
**Written:** 2026-05-22T17:37:28.907Z

# UAT: Retrieval evaluation metrics persisted to SQLite (S03)

## UAT Type
Manual developer/operator UAT (offline, deterministic; no live providers required).

## Preconditions
1. Python venv exists and dependencies installed.
2. A test or dev SQLite DB exists that includes:
   - Gold retrieval queries and target pages (gold_retrieval_* tables per schema from S01).
   - A retrieval index run and indexed pages (retrieval_index_* tables).
3. (Optional) No RAGAS install and no trace tables are fine; optional metrics must skip without crashing.

## Steps
1. Run the retrieval eval runner entrypoint used by the codebase (e.g., call `run_retrieval_eval(...)` against the DB path).
2. Confirm a new `eval_runs` row is created with eval_type indicating retrieval evaluation (and status transitions to completed).
3. Query `eval_metrics` for that run_id.
4. Verify both summary metrics and per-query scoped metrics exist:
   - Summary recall@5 and recall@10.
   - Per-query recall@k metrics (scoped by query_id).
   - Citation accuracy metrics at page level.
5. Re-run the same eval again with the same inputs.
6. Confirm the run does not crash and metric upserts behave idempotently (no runaway duplicates; stable metric names/scope rows remain consistent).
7. Enable optional flags (latency/cost and ragas) while using a DB that does NOT have trace tables and while `ragas` is not installed.
8. Confirm the eval still completes successfully and core retrieval metrics are still persisted.

## Expected Outcomes
- The eval run completes and persists numeric retrieval metrics into `eval_runs`/`eval_metrics`.
- Missing prerequisites are handled gracefully:
  - No gold queries or no retrieval index run => no crash; run completes with no metrics.
  - Optional metric prerequisites missing => no crash; optional metrics are skipped; core retrieval metrics still computed/persisted.
- Re-running does not create unbounded duplicate metric rows.

## Edge Cases to Exercise
- Gold set is empty: eval completes with zero/no metrics.
- Retrieval hits include duplicates: recall/citation computations de-duplicate correctly.
- Top-k cutoff behavior: recall@5 differs from recall@10 when relevant targets appear beyond k.

## Not Proven By This UAT
- True RAG evaluation (answer faithfulness/relevancy) with a defined gold answer/context schema.
- Span-level citation grounding (this slice is page-level correctness only).
- Real latency/cost rollups from a finalized trace schema (current hook is best-effort and expected to skip until schema exists).
